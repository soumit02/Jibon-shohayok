import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_token, hash_password, verify_password
from app.db.models import User, UserProfile
from app.db.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=72)
    full_name: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


def _token_response(user: User) -> dict:
    return {"access_token": create_token(user.id), "token_type": "bearer",
            "user": {"id": user.id, "email": user.email}}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Please enter a valid email.")
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This email is already registered.")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id, full_name=body.full_name))
    db.commit()
    return _token_response(user)


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email.strip().lower())).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    return _token_response(user)


@router.post("/token", include_in_schema=True)
def token_for_swagger(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Used by the Authorize button in /docs (type your email in the 'username' box)."""
    user = db.execute(select(User).where(User.email == form.username.strip().lower())).scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    return _token_response(user)


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(UserProfile, user.id)
    return {"id": user.id, "email": user.email, "full_name": profile.full_name if profile else None}
