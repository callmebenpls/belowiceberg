from fastapi import APIRouter, Depends, HTTPException, Response, status as http_status
from pydantic import BaseModel, EmailStr, Field
from app.auth import (
    SESSION_COOKIE, SESSION_MAX_AGE,
    issue_user_session, require_user,
)
from app import users as users_mod

router = APIRouter()

class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=64)

class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)

class ChangePasswordBody(BaseModel):
    current: str = Field(min_length=1, max_length=200)
    new: str = Field(min_length=8, max_length=200)

class PatchMeBody(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    cards_open_default: bool | None = None

def _set_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE, value=issue_user_session(user_id),
        max_age=SESSION_MAX_AGE, httponly=True,
        samesite="lax", secure=False, path="/",
    )

def _user_to_json(u: dict) -> dict:
    return {
        "id": u["id"], "email": u["email"], "display_name": u["display_name"],
        "is_admin": bool(u["is_admin"]),
        "cards_open_default": bool(u["cards_open_default"]),
    }

@router.post("/api/auth/signup")
def signup(body: SignupBody, response: Response):
    try:
        uid = users_mod.create_user(body.email, body.password, body.display_name)
    except users_mod.UserExistsError:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="email already registered")
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    _set_cookie(response, uid)
    return {"ok": True}

@router.post("/api/auth/login")
def login(body: LoginBody, response: Response):
    uid = users_mod.verify_credentials(body.email, body.password)
    if uid is None:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="bad credentials")
    _set_cookie(response, uid)
    return {"ok": True}

@router.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}

@router.get("/api/me")
def me(user: dict = Depends(require_user)):
    return _user_to_json(user)

@router.patch("/api/me")
def patch_me(body: PatchMeBody, user: dict = Depends(require_user)):
    if body.display_name is not None:
        users_mod.update_display_name(user["id"], body.display_name)
    if body.cards_open_default is not None:
        users_mod.update_cards_open_default(user["id"], body.cards_open_default)
    return {"ok": True}

@router.post("/api/me/change-password")
def change_password_route(body: ChangePasswordBody, user: dict = Depends(require_user)):
    try:
        users_mod.change_password(user["id"], body.current, body.new)
    except users_mod.WrongPasswordError:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="wrong current password")
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"ok": True}

@router.post("/api/me/clear-progress")
def clear_progress_route(user: dict = Depends(require_user)):
    users_mod.clear_progress(user["id"])
    return {"ok": True}
