# server/app/notes.py
import json
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from app.config import load_config

VALID_CATEGORIES = {"vocab", "grammar", "structure"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

class NoteValidationError(ValueError):
    pass

@dataclass
class Note:
    paraId: str
    category: str
    selectedText: str
    responseMarkdown: str
    createdAt: str = ""

def _validate_slug(slug: str) -> None:
    if not SLUG_RE.match(slug):
        raise NoteValidationError(f"Invalid book slug: {slug!r}")

def _validate_note(n: Note) -> None:
    if n.category not in VALID_CATEGORIES:
        raise NoteValidationError(f"Invalid category: {n.category!r}")
    if not n.paraId or not n.selectedText or not n.responseMarkdown:
        raise NoteValidationError("paraId, selectedText, responseMarkdown required")
    if len(n.selectedText) > 2000 or len(n.responseMarkdown) > 8000:
        raise NoteValidationError("field too long")

def _path_for(slug: str) -> Path:
    _validate_slug(slug)
    cfg = load_config()
    cfg.notes_dir.mkdir(parents=True, exist_ok=True)
    return cfg.notes_dir / f"{slug}.json"

def read_notes(slug: str) -> list[Note]:
    p = _path_for(slug)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [Note(**n) for n in data]

def append_note(slug: str, note: Note) -> None:
    _validate_note(note)
    if not note.createdAt:
        note.createdAt = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p = _path_for(slug)
    existing = read_notes(slug)
    existing.append(note)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps([asdict(n) for n in existing], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, p)
