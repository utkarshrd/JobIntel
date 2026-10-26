"""Authentication: email + password accounts, signed sessions, throttling, account management, per-user access."""
import time

import pytest

from backend.app.core import security
from backend.app.core.config import settings

PW = "correct horse battery"


@pytest.fixture
def secured(client, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_USER_TOKEN", True)
    security.login_throttle._fails.clear()
    return client


def register(client, email="ana@example.com", password=PW, name="Ana Rao"):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": name})


def bearer(res):
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ----------------------------------------------------------------------------- password + token primitives
def test_password_hash_is_salted_scrypt_and_verifies():
    a, b = security.hash_password(PW), security.hash_password(PW)
    assert a != b and a.startswith("scrypt$") and PW not in a
    assert security.verify_password(PW, a) and not security.verify_password("wrong", a)
    assert not security.verify_password(PW, None) and not security.verify_password(PW, "garbage")


def test_token_roundtrip_expiry_and_tamper():
    t = security.create_access_token(42)
    assert security.decode_access_token(t) == 42
    assert security.decode_access_token(security.create_access_token(42, ttl_seconds=-1)) is None     # expired
    payload, sig = t.split(".")
    assert security.decode_access_token(f"{payload}.{sig[:-2]}xx") is None                            # bad signature
    forged = security.create_access_token(43).split(".")[0]
    assert security.decode_access_token(f"{forged}.{sig}") is None                                    # payload swapped
    assert security.decode_access_token("not-a-token") is None


# ----------------------------------------------------------------------------- register / login
def test_register_signs_in_and_never_leaks_credentials(secured):
    r = register(secured)
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "ana@example.com" and body["expires_in"] == 7 * 24 * 3600 and body["token_type"] == "bearer"
    assert "password_hash" not in body["user"] and "scrypt" not in str(body)
    me = secured.get("/api/v1/auth/me", headers=bearer(r))
    assert me.status_code == 200 and me.json()["id"] == body["user"]["id"]


def test_register_validation_and_duplicates(secured):
    assert register(secured, password="short").status_code == 422
    assert register(secured, email="not-an-email").status_code == 422
    assert register(secured, name="").status_code == 422
    assert register(secured).status_code == 201
    dup = register(secured, email="ANA@Example.com")
    assert dup.status_code == 409 and "already exists" in dup.json()["detail"]


def test_login_success_and_uniform_failure_message(secured):
    register(secured)
    ok = secured.post("/api/v1/auth/login", json={"email": "Ana@Example.com", "password": PW})
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad_pw = secured.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "nope-nope-nope"})
    no_user = secured.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": PW})
    assert bad_pw.status_code == no_user.status_code == 401
    assert bad_pw.json()["detail"] == no_user.json()["detail"] == "Incorrect email or password."   # no account enumeration


def test_login_is_throttled_after_repeated_failures(secured):
    register(secured)
    for _ in range(5):
        assert secured.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "wrong-wrong"}).status_code == 401
    locked = secured.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": PW})   # even the right password
    assert locked.status_code == 429 and "15 minutes" in locked.json()["detail"]
    assert secured.post("/api/v1/auth/login", json={"email": "other@example.com", "password": "x"}).status_code == 401  # others unaffected


def test_passwordless_records_cannot_sign_in(client, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_USER_TOKEN", False)
    client.post("/api/v1/users/", json={"email": "legacy@example.com", "full_name": "L"})
    monkeypatch.setattr(settings, "REQUIRE_USER_TOKEN", True)
    assert client.post("/api/v1/auth/login", json={"email": "legacy@example.com", "password": PW}).status_code == 401


def test_open_profile_creation_is_closed_when_auth_is_enforced(secured):
    r = secured.post("/api/v1/users/", json={"email": "x@example.com", "full_name": "X"})
    assert r.status_code == 403 and "auth/register" in r.json()["detail"]


# ----------------------------------------------------------------------------- per-user access
def test_each_user_can_only_reach_their_own_data(secured):
    a, b = register(secured, "a@example.com"), register(secured, "b@example.com")
    ida, idb = a.json()["user"]["id"], b.json()["user"]["id"]
    for path in (f"/api/v1/users/{ida}", f"/api/v1/recommendations/{ida}", f"/api/v1/users/{ida}/interactions",
                 f"/api/v1/users/{ida}/personalization", f"/api/v1/skill-gap/analyze?user_id={ida}&target_role=Data"):
        assert secured.get(path).status_code == 401, path
        assert secured.get(path, headers=bearer(b)).status_code == 401, path
        assert secured.get(path, headers=bearer(a)).status_code in (200, 404), path
    assert secured.put(f"/api/v1/users/{ida}", json={"headline": "x"}, headers=bearer(b)).status_code == 401
    assert secured.put(f"/api/v1/users/{ida}", json={"headline": "x"}, headers=bearer(a)).status_code == 200
    j = secured.post("/api/v1/jobs/", json={"job_id": "ac_j", "title": "T", "company_name": "C", "description": "d"}).json()
    body = {"user_id": ida, "job_id": j["id"], "interaction_type": "save"}
    assert secured.post("/api/v1/users/interactions", json=body).status_code == 401
    assert secured.post("/api/v1/users/interactions", json=body, headers=bearer(b)).status_code == 401
    assert secured.post("/api/v1/users/interactions", json=body, headers=bearer(a)).status_code == 201
    assert idb != ida


def test_expired_or_forged_session_is_rejected(secured):
    uid = register(secured).json()["user"]["id"]
    expired = {"Authorization": "Bearer " + security.create_access_token(uid, ttl_seconds=-5)}
    assert secured.get("/api/v1/auth/me", headers=expired).status_code == 401
    assert secured.get("/api/v1/auth/me", headers={"Authorization": "Bearer abc.def"}).status_code == 401
    assert secured.get("/api/v1/auth/me").status_code == 401


def test_public_endpoints_stay_open(secured):
    for path in ("/api/v1/health", "/api/v1/jobs/", "/api/v1/analytics/twsma", "/api/v1/analytics/summary", "/ui/"):
        assert secured.get(path).status_code == 200, path


# ----------------------------------------------------------------------------- account management
def test_change_password(secured):
    r = register(secured)
    wrong = secured.put("/api/v1/auth/password", json={"current_password": "bad", "new_password": "a brand new one"}, headers=bearer(r))
    assert wrong.status_code == 400
    assert secured.put("/api/v1/auth/password", json={"current_password": PW, "new_password": "short"}, headers=bearer(r)).status_code == 422
    assert secured.put("/api/v1/auth/password", json={"current_password": PW, "new_password": "a brand new one"}, headers=bearer(r)).status_code == 204
    assert secured.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": PW}).status_code == 401
    assert secured.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "a brand new one"}).status_code == 200


def test_delete_account_removes_user_and_history(secured, db_session):
    from backend.app.models import Interaction, User
    r = register(secured)
    uid = r.json()["user"]["id"]
    j = secured.post("/api/v1/jobs/", json={"job_id": "del_j", "title": "T", "company_name": "C", "description": "d"}).json()
    secured.post("/api/v1/users/interactions", json={"user_id": uid, "job_id": j["id"], "interaction_type": "save"}, headers=bearer(r))
    assert secured.request("DELETE", "/api/v1/auth/me", json={"password": "wrong"}, headers=bearer(r)).status_code == 400
    assert secured.request("DELETE", "/api/v1/auth/me", json={"password": PW}, headers=bearer(r)).status_code == 204
    assert db_session.query(User).filter(User.id == uid).count() == 0
    assert db_session.query(Interaction).filter(Interaction.user_id == uid).count() == 0
    gone = secured.get("/api/v1/auth/me", headers=bearer(r))
    assert gone.status_code == 401 and "no longer exists" in gone.json()["detail"]
    assert secured.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": PW}).status_code == 401


def test_session_expiry_setting_is_applied(secured, monkeypatch):
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 1)
    r = register(secured)
    assert r.json()["expires_in"] == 60
    assert time.time() < 1e12   # sanity: clock is sane for the expiry arithmetic
