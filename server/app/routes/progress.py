from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel, Field
from app.auth import require_user
from app import progress as prog

router = APIRouter()

class ProgressBody(BaseModel):
    book_slug: str
    chapter: int
    section: int

@router.post("/api/progress")
def post_progress(body: ProgressBody, user: dict = Depends(require_user)):
    try:
        prog.upsert_progress(user["id"], body.book_slug, body.chapter, body.section)
    except prog.ProgressError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"ok": True}

@router.get("/api/library")
def get_library(user: dict = Depends(require_user)):
    return prog.get_library_for(user["id"])
