from fastapi import APIRouter, Depends, HTTPException, Response, status as http_status
from pydantic import BaseModel
from app.auth import (
    verify_password, issue_session, require_admin,
    SESSION_COOKIE, SESSION_MAX_AGE,
)

router = APIRouter()

class LoginBody(BaseModel):
    password: str

@router.post("/admin/login")
def login(body: LoginBody, response: Response):
    if not verify_password(body.password):
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED,
                            detail="bad password")
    token = issue_session()
    response.set_cookie(
        key=SESSION_COOKIE, value=token,
        max_age=SESSION_MAX_AGE, httponly=True,
        samesite="lax", secure=False,  # nginx terminates TLS later; flip to True then
        path="/",
    )
    return {"ok": True}

@router.post("/admin/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}

@router.get("/admin")
def status(_: None = Depends(require_admin)):
    return {"role": "admin"}
