from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel, Field
from app.auth import require_admin_user
from app.notes import read_notes, append_note, Note, NoteValidationError

router = APIRouter()

class NoteIn(BaseModel):
    paraId: str = Field(min_length=1, max_length=64)
    category: str
    selectedText: str = Field(min_length=1, max_length=2000)
    responseMarkdown: str = Field(min_length=1, max_length=8000)

@router.get("/api/notes/{slug}")
def get_notes(slug: str):
    try:
        return [n.__dict__ for n in read_notes(slug)]
    except NoteValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/notes/{slug}", status_code=http_status.HTTP_201_CREATED)
def post_note(slug: str, body: NoteIn, _: dict = Depends(require_admin_user)):
    note = Note(**body.model_dump())
    try:
        append_note(slug, note)
    except NoteValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "createdAt": note.createdAt}
