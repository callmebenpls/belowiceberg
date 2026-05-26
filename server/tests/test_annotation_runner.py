import asyncio
import json
import pytest
from app.db import migrate, get_conn, reset_conn
from app import books as bk


@pytest.fixture
def db(env):
    reset_conn()
    migrate()
    book_id = bk.create_book("test-book", "Test Book", "测试书", "Author")
    ch_id = bk.add_chapter(book_id, 1, "第一章", "Chapter one full text.")
    sec_id = bk.add_section(ch_id, 1, "第一节")
    bk.add_paragraph(sec_id, 1, "In my younger years.")
    bk.add_paragraph(sec_id, 2, "He.")  # trivial
    yield get_conn(), book_id
    reset_conn()


def _make_job(book_id: int) -> int:
    return bk.get_or_create_job(
        book_id=book_id,
        scope_json=json.dumps([1]),
        dimensions_csv="vocab,grammar",
        prompts_json=json.dumps({"vocab": "Find vocabulary.", "grammar": "Find grammar."}),
        depth="standard",
        language="zh",
        extra_instructions=None,
        prompt_version_hash="abc123",
    )


@pytest.mark.asyncio
async def test_run_job_produces_annotations(db, monkeypatch):
    conn, book_id = db
    job_id = _make_job(book_id)
    queue = asyncio.Queue()

    paras = bk.get_paragraphs_for_book(book_id)
    worthy_id = paras[0]["id"]

    call_count = 0

    async def fake_call_once(system, user, temperature=0.3):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return json.dumps([worthy_id])  # pre-pass filter
        return json.dumps({
            "vocab": [{"term": "younger", "body_markdown": "Explanation of younger."}],
            "grammar": []
        })

    monkeypatch.setattr("app.annotation_runner.call_once", fake_call_once)

    from app.annotation_runner import run_job
    await run_job(job_id, queue)

    events = []
    while not queue.empty():
        events.append(await queue.get())

    types = [e["type"] for e in events]
    assert "annotation" in types
    assert types[-1] == "done"

    anns = bk.get_annotations_for_book(book_id)
    assert len(anns) == 1
    assert anns[0]["term"] == "younger"
    assert anns[0]["dimension"] == "vocab"


@pytest.mark.asyncio
async def test_run_job_idempotent(db, monkeypatch):
    conn, book_id = db
    paras = bk.get_paragraphs_for_book(book_id)
    p_id = paras[0]["id"]
    bk.upsert_annotation(p_id, "vocab", "younger", "Old body.", "abc123")

    job_id = _make_job(book_id)
    queue = asyncio.Queue()

    async def fake_call_once(system, user, temperature=0.3):
        if "filtering" in system.lower() or "filter" in system.lower():
            return json.dumps([p_id])
        return json.dumps({"vocab": [{"term": "younger", "body_markdown": "New body."}]})

    monkeypatch.setattr("app.annotation_runner.call_once", fake_call_once)
    from app.annotation_runner import run_job
    await run_job(job_id, queue)

    anns = bk.get_annotations_for_book(book_id)
    assert len(anns) == 1
    assert anns[0]["body_markdown"] == "New body."


@pytest.mark.asyncio
async def test_run_job_error_handling(db, monkeypatch):
    conn, book_id = db
    job_id = _make_job(book_id)
    queue = asyncio.Queue()

    from app.deepseek import DeepSeekError

    async def fake_call_once(system, user, temperature=0.3):
        raise DeepSeekError("rate limit")

    monkeypatch.setattr("app.annotation_runner.call_once", fake_call_once)
    from app.annotation_runner import run_job
    await run_job(job_id, queue)

    events = []
    while not queue.empty():
        events.append(await queue.get())

    assert events[-1]["type"] == "error"
    job = bk.get_job(job_id)
    assert job["status"] == "error"
    assert "rate limit" in job["error_message"]


def test_compute_prompt_hash_deterministic():
    from app.annotation_runner import compute_prompt_hash
    h1 = compute_prompt_hash("hello world")
    h2 = compute_prompt_hash("hello world")
    assert h1 == h2
    assert len(h1) == 16


def test_build_system_prompt_includes_dimensions():
    from app.annotation_runner import build_system_prompt
    prompt = build_system_prompt(["vocab", "grammar"], {}, "standard", "zh", None)
    assert "VOCAB" in prompt
    assert "GRAMMAR" in prompt
    assert "standard" in prompt.lower() or "thorough" in prompt.lower()
