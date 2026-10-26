"""
JobIntel - Account endpoints: register, sign in, current user, change password, delete account.
Sessions are signed expiring bearer tokens (see backend/app/core/security.py); the UI never shows them to the user.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.api.v1.endpoints.users import _format_user_response
from backend.app.core.config import settings
from backend.app.core.security import (MIN_PASSWORD_LENGTH, create_access_token, current_user_id, hash_password,
                                       login_throttle, verify_password)
from backend.app.models.user import User
from backend.app.schemas.user import UserCreate, UserResponse
from backend.app.services.user_service import UserService

router = APIRouter()


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


class PasswordConfirm(BaseModel):
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(access_token=create_access_token(user.id), expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                        user=_format_user_response(user))


def _me(db: Session, user_id: int) -> User:
    user = UserService.get_user_by_id(db, user_id)
    if not user:   # account was deleted while the session was still valid
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This account no longer exists.")
    return user


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Create an account (email + password) and sign in. The profile (skills, roles, locations) is filled in afterwards."""
    email = body.email.lower()
    if UserService.get_user_by_email(db, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists. Try signing in.")
    user = UserService.create_user(db, UserCreate(email=email, full_name=body.full_name.strip()))
    user.password_hash = hash_password(body.password)
    db.commit()
    return _auth_response(UserService.get_user_by_id(db, user.id))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = body.email.lower()
    key = f"{email}|{request.client.host if request.client else '-'}"
    if login_throttle.blocked(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Too many failed sign-in attempts. Please wait 15 minutes and try again.")
    user = UserService.get_user_by_email(db, email)
    if not user or not verify_password(body.password, user.password_hash):
        login_throttle.fail(key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")
    login_throttle.reset(key)
    return _auth_response(user)


@router.get("/me", response_model=UserResponse)
def me(user_id: int = Depends(current_user_id), db: Session = Depends(get_db)):
    """The signed-in user's profile (also used by the UI to validate a stored session)."""
    return _format_user_response(_me(db, user_id))


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)):
    user = _me(db, user_id)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(body: PasswordConfirm, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)):
    """Permanently delete the account with its skills and interaction history (password required)."""
    user = _me(db, user_id)
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password is incorrect.")
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
