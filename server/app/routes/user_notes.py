from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel, Field
from app.auth import require_user
from app import user_notes as un

router = APIRouter()

class NoteIn(BaseModel):
    paraId: str = Field(min_length=1, max_length=64)
    category: Literal["vocab", "grammar", "structure"]
    selectedText: str = Field(min_length=1, max_length=2000)
    responseMarkdown: str = Field(min_length=1, max_length=8000)

def _row_to_json(r: dict) -> dict:
    return {
        "id": r["id"], "book_slug": r["book_slug"],
        "paraId": r["para_id"], "category": r["category"],
        "selectedText": r["selected_text"],
        "responseMarkdown": r["response_markdown"],
        "createdAt": r["created_at"],
    }

@router.get("/api/user-notes/{slug}")
def get_user_notes(slug: str, user: dict = Depends(require_user)):
    try:
        return [_row_to_json(r) for r in un.list_for_user_book(user["id"], slug)]
    except un.UserNoteError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/api/user-notes/{slug}", status_code=http_status.HTTP_201_CREATED)
def post_user_note(slug: str, body: NoteIn, user: dict = Depends(require_user)):
    try:
        nid = un.append_note(user["id"], slug, body.paraId, body.category,
                             body.selectedText, body.responseMarkdown)
    except un.UserNoteError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"ok": True, "id": nid}
