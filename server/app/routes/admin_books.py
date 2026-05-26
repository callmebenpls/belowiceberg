import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status as hs
from pydantic import BaseModel
from typing import Literal
from app.auth import require_admin_user
from app import books as bk

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_user)])


class BookPatch(BaseModel):
    status: Literal["draft", "published"] | None = None
    cover_css: str | None = None


@router.get("/books")
def list_books():
    return bk.list_books()


@router.patch("/books/{book_id}")
def patch_book(book_id: int, body: BookPatch):
    try:
        bk.update_book(book_id, status=body.status, cover_css=body.cover_css)
    except ValueError as e:
        raise HTTPException(status_code=hs.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except bk.BookNotFoundError:
        raise HTTPException(status_code=hs.HTTP_404_NOT_FOUND)
    return {"ok": True}


@router.delete("/books/{book_id}")
def delete_book(book_id: int):
    try:
        bk.delete_book(book_id)
    except bk.BookNotFoundError:
        raise HTTPException(status_code=hs.HTTP_404_NOT_FOUND)
    return {"ok": True}


@router.get("/books/{book_id}/chapters")
def get_chapters(book_id: int):
    return bk.get_chapters_for_book(book_id)


@router.get("/books/{book_id}/paragraphs")
def get_paragraphs(book_id: int):
    return bk.get_paragraphs_for_book(book_id)


@router.get("/books/{book_id}/annotations")
def get_annotations(book_id: int):
    return bk.get_annotations_for_book(book_id)


@router.post("/books/upload")
async def upload_epub(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".epub"):
        raise HTTPException(status_code=hs.HTTP_400_BAD_REQUEST,
                            detail="File must be a .epub")
    data = await file.read()
    try:
        from app.epub_parser import parse_epub_to_db
        book_id = parse_epub_to_db(io.BytesIO(data))
    except Exception as e:
        raise HTTPException(status_code=hs.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"EPUB parse error: {str(e)[:200]}")
    return {"book_id": book_id}
