import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, status as hs
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.auth import require_admin_user
from app import books as bk
from app.annotation_runner import build_system_prompt, compute_prompt_hash, run_job

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_user)])

# job_id → asyncio.Queue for SSE consumers
_job_queues: dict[int, asyncio.Queue] = {}


class JobBody(BaseModel):
    book_id: int
    scope_chapter_nums: list[int]
    dimensions: list[str]
    prompts: dict[str, str]
    depth: str = "standard"
    language: str = "zh"
    extra_instructions: str | None = None


@router.post("/jobs")
async def create_job(body: JobBody):
    system_prompt = build_system_prompt(
        body.dimensions, body.prompts, body.depth, body.language, body.extra_instructions
    )
    prompt_hash = compute_prompt_hash(system_prompt)
    job_id = bk.get_or_create_job(
        book_id=body.book_id,
        scope_json=json.dumps(body.scope_chapter_nums),
        dimensions_csv=",".join(body.dimensions),
        prompts_json=json.dumps(body.prompts),
        depth=body.depth,
        language=body.language,
        extra_instructions=body.extra_instructions,
        prompt_version_hash=prompt_hash,
    )
    queue: asyncio.Queue = asyncio.Queue()
    _job_queues[job_id] = queue
    asyncio.create_task(run_job(job_id, queue))
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    try:
        return bk.get_job(job_id)
    except LookupError:
        raise HTTPException(status_code=hs.HTTP_404_NOT_FOUND)


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: int):
    queue = _job_queues.get(job_id)
    if queue is None:
        try:
            bk.get_job(job_id)
        except LookupError:
            raise HTTPException(status_code=hs.HTTP_404_NOT_FOUND)

        async def done_stream():
            yield f"data: {json.dumps({'type': 'done', 'job_id': job_id})}\n\n"

        return StreamingResponse(done_stream(), media_type="text/event-stream")

    async def generate():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") in ("done", "error"):
                _job_queues.pop(job_id, None)
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: int):
    _job_queues.pop(job_id, None)
    try:
        bk.update_job(job_id, status="error", error_message="cancelled by admin")
    except LookupError:
        raise HTTPException(status_code=hs.HTTP_404_NOT_FOUND)
    return {"ok": True}
