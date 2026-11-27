from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DB

from ..auth import current_user, issue_token, verify_password
from ..db import get_db
from ..models import AuthToken, User
from ..schemas import LoginIn, LoginOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: DB = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong username or password")
    return LoginOut(token=issue_token(db, user), role=user.role, username=user.username,
                    professor_id=user.professor_id)


@router.get("/me", response_model=LoginOut)
def me(user: User = Depends(current_user)):
    return LoginOut(token="", role=user.role, username=user.username,
                    professor_id=user.professor_id)


@router.post("/logout")
def logout(user: User = Depends(current_user), db: DB = Depends(get_db)):
    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    db.commit()
    return {"ok": True}
