"""
JobIntel - User Profile Service
Handles candidate profiles, target roles, preferred locations, and skill proficiencies.
"""

from typing import Optional
from sqlalchemy.orm import Session, joinedload
from backend.app.models.user import User
from backend.app.models.skill import Skill, UserSkill
from backend.app.schemas.user import UserCreate, UserUpdate


_extractor = None


def _canonical(name: str):
    """(canonical name, display name, category) via the skills taxonomy so aliases ('ml') resolve to the
    same skill the job extractor uses. Unknown skills keep the user's own wording."""
    global _extractor
    if _extractor is None:
        from nlp.skill_extractor import SkillExtractor
        _extractor = SkillExtractor()
    entry = _extractor.skills_lookup.get(name.strip().lower())
    if entry:
        return entry["name"], entry["display_name"], entry["category"]
    return name.strip().lower(), name.strip(), "General"


def _attach_skills(db: Session, user: User, items) -> None:
    seen = set()
    for item in items:
        skill = None
        if item.skill_id:
            skill = db.query(Skill).filter(Skill.id == item.skill_id).first()
        elif item.skill_name and item.skill_name.strip():
            name, display, category = _canonical(item.skill_name)
            skill = db.query(Skill).filter(Skill.name == name).first()
            if not skill:
                skill = Skill(name=name, display_name=display, category=category)
                db.add(skill)
                db.flush()
        if skill and skill.id not in seen:
            seen.add(skill.id)
            db.add(UserSkill(user_id=user.id, skill_id=skill.id, proficiency_level=item.proficiency_level,
                             years_of_experience=item.years_of_experience))


class UserService:
    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        """Fetch a user profile by ID with skills eagerly loaded."""
        return (
            db.query(User)
            .options(joinedload(User.skills_rel).joinedload(UserSkill.skill_rel))
            .filter(User.id == user_id)
            .first()
        )

    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        """Fetch a user profile by email."""
        return (
            db.query(User)
            .options(joinedload(User.skills_rel).joinedload(UserSkill.skill_rel))
            .filter(User.email == email)
            .first()
        )

    @staticmethod
    def create_user(db: Session, user_in: UserCreate) -> User:
        """Create a new user profile along with their skills."""
        user_data = user_in.model_dump(exclude={"skills"})
        user = User(**user_data)
        db.add(user)
        db.flush()

        _attach_skills(db, user, user_in.skills)

        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update_user(db: Session, user_id: int, user_in: UserUpdate) -> Optional[User]:
        """Update an existing user profile."""
        user = UserService.get_user_by_id(db, user_id)
        if not user:
            return None

        update_data = user_in.model_dump(exclude_unset=True, exclude={"skills"})
        for field, value in update_data.items():
            setattr(user, field, value)

        if user_in.skills is not None:
            # Replace skills
            db.query(UserSkill).filter(UserSkill.user_id == user.id).delete()
            _attach_skills(db, user, user_in.skills)

        db.commit()
        db.refresh(user)
        return user
