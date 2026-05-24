import json
from pathlib import Path
from typing import AsyncIterator
import httpx
from app.config import load_config

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
VALID_CATEGORIES = {"vocab", "grammar", "structure"}
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

class DeepSeekError(RuntimeError):
    pass

def load_prompt(category: str) -> str:
    if category not in VALID_CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    return (PROMPTS_DIR / f"{category}.txt").read_text(encoding="utf-8")

async def stream_analysis(
    category: str,
    selected_text: str,
    para_context: str,
) -> AsyncIterator[str]:
    """Yields response content tokens from DeepSeek."""
    system_prompt = load_prompt(category)
    user_msg = (
        f"选中文本：{selected_text}\n\n"
        f"完整段落上下文：\n{para_context}"
    )
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": True,
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {load_config().deepseek_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", DEEPSEEK_URL, json=body, headers=headers) as r:
            if r.status_code >= 400:
                body_text = await r.aread()
                raise DeepSeekError(f"DeepSeek {r.status_code}: {body_text[:200]!r}")
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    return
                try:
                    obj = json.loads(payload)
                    delta = obj["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
