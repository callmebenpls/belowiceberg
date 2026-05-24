# server/tests/test_notes.py
import json
import pytest
from pathlib import Path
from app.notes import read_notes, append_note, NoteValidationError, Note

def test_read_notes_returns_empty_when_no_file(env):
    assert read_notes("gatsby") == []

def test_append_then_read(env):
    note = Note(
        paraId="para3",
        category="vocab",
        selectedText="advantages",
        responseMarkdown="**advantages** — 优势",
    )
    append_note("gatsby", note)
    notes = read_notes("gatsby")
    assert len(notes) == 1
    assert notes[0].selectedText == "advantages"
    assert notes[0].createdAt  # auto-set

def test_append_multiple_preserves_order(env):
    for s in ["a", "b", "c"]:
        append_note("gatsby", Note(paraId="p1", category="vocab",
                                   selectedText=s, responseMarkdown=s))
    notes = read_notes("gatsby")
    assert [n.selectedText for n in notes] == ["a", "b", "c"]

def test_slug_traversal_rejected(env):
    with pytest.raises(NoteValidationError):
        read_notes("../etc/passwd")
    with pytest.raises(NoteValidationError):
        append_note("../x", Note(paraId="p", category="vocab",
                                  selectedText="t", responseMarkdown="r"))

def test_bad_category_rejected(env):
    with pytest.raises(NoteValidationError):
        append_note("gatsby", Note(paraId="p1", category="bogus",
                                    selectedText="x", responseMarkdown="y"))

def test_atomic_write_no_tmp_leftover(env):
    append_note("gatsby", Note(paraId="p", category="vocab",
                                selectedText="x", responseMarkdown="y"))
    leftovers = list(env.glob("notes/*.tmp"))
    assert leftovers == []
