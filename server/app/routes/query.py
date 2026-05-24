from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.auth import require_admin
from app.deepseek import stream_analysis, DeepSeekError

router = APIRouter()

class QueryBody(BaseModel):
    category: Literal["vocab", "grammar", "structure"]
    selectedText: str = Field(min_length=1, max_length=2000)
    paraContext: str = Field(min_length=1, max_length=10000)

async def _sse(body: QueryBody):
    try:
        async for token in stream_analysis(body.category, body.selectedText, body.paraContext):
            # SSE: escape newlines per spec
            safe = token.replace("\r", "").replace("\n", "\\n")
            yield f"data: {safe}\n\n"
        yield "data: [DONE]\n\n"
    except DeepSeekError as e:
        yield f"event: error\ndata: {str(e)[:200]}\n\n"

@router.post("/api/query")
async def query(body: QueryBody, _: None = Depends(require_admin)):
    return StreamingResponse(_sse(body), media_type="text/event-stream")
