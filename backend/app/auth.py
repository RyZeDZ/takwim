"""Logins for admin and professors. Students never log in.

Passwords are hashed with PBKDF2 (Python standard library). Logging in returns a random
token that the frontend sends back as `Authorization: Bearer <token>`. The database only
keeps a SHA-256 hash of each token.
"""
import hashlib
import hmac
import re
import secrets
import unicodedata
from datetime import timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session as DB

from .config import settings
from .db import get_db
from .models import ActionLog, AuthToken, User, now

_ITER = 100_000
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITER).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITER).hex()
    return hmac.compare_digest(test, digest)


def new_password() -> str:
    return secrets.token_urlsafe(6)


def username_from_name(name: str) -> str:
    """'Karim Benali' -> 'karim.benali' (ASCII, lowercase)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", ".", ascii_name.lower()).strip(".")
    return slug or f"prof{secrets.randbelow(10000)}"


def unique_username(db: DB, name: str) -> str:
    base = username_from_name(name)
    candidate, n = base, 1
    while db.scalar(select(User).where(User.username == candidate)):
        n += 1
        candidate = f"{base}{n}"
    return candidate


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(db: DB, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthToken(token_hash=token_hash(token), user_id=user.id,
                     expires_at=now() + timedelta(hours=settings.login_expires_hours)))
    db.commit()
    return token


class MissingAdminConfig(RuntimeError):
    pass


def ensure_admin(db: DB) -> None:
    """Create the first admin from ADMIN_USERNAME / ADMIN_PASSWORD (.env) if there is none."""
    if db.scalar(select(User).where(User.role == "admin")):
        return
    if not settings.admin_username or len(settings.admin_password) < 8:
        raise MissingAdminConfig(
            "No admin account yet: set ADMIN_USERNAME and ADMIN_PASSWORD (8+ characters) "
            "in the .env file, then start again. See .env.example."
        )
    db.add(User(username=settings.admin_username,
                password_hash=hash_password(settings.admin_password), role="admin"))
    db.commit()


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: DB = Depends(get_db)
) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    tok = db.get(AuthToken, token_hash(creds.credentials))
    if not tok or tok.expires_at < now():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, tok.user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def require_prof(user: User = Depends(current_user)) -> User:
    if user.role != "prof" or not user.professor_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Professor account required")
    return user


def log(db: DB, user: User | str, action: str, detail: str = "") -> None:
    name = user if isinstance(user, str) else user.username
    db.add(ActionLog(username=name, action=action, detail=detail[:400]))
