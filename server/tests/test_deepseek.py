import pytest
from app.deepseek import load_prompt, stream_analysis, DeepSeekError

def test_load_prompt_vocab(env):
    p = load_prompt("vocab")
    assert "词汇" in p or "学习者" in p

def test_load_prompt_invalid_category(env):
    with pytest.raises(ValueError):
        load_prompt("bogus")

async def test_stream_analysis_yields_tokens(env, httpx_mock):
    httpx_mock.add_response(
        url="https://api.deepseek.com/chat/completions",
        method="POST",
        text=(
            'data: {"choices":[{"delta":{"content":"hello "}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"world"}}]}\n\n'
            'data: [DONE]\n\n'
        ),
        headers={"Content-Type": "text/event-stream"},
    )
    tokens = []
    async for tok in stream_analysis("vocab", "advice", "He gave me some advice."):
        tokens.append(tok)
    assert "".join(tokens) == "hello world"

async def test_stream_analysis_http_error(env, httpx_mock):
    httpx_mock.add_response(
        url="https://api.deepseek.com/chat/completions",
        method="POST",
        status_code=500,
        text="server error",
    )
    with pytest.raises(DeepSeekError):
        async for _ in stream_analysis("vocab", "x", "y"):
            pass
