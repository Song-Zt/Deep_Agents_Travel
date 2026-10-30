import pytest
from types import SimpleNamespace

from llm.client import LLMClient


@pytest.mark.asyncio
async def test_chat_with_metadata(monkeypatch):
    client = LLMClient.__new__(LLMClient)

    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="测试生成内容"
                ),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            model_dump=lambda: {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            }
        ),
    )

    async def fake_chat_completion(**kwargs):
        assert kwargs["max_tokens"] == 4096
        return fake_response

    monkeypatch.setattr(
        client,
        "chat_completion",
        fake_chat_completion,
    )

    result = await client.chat_with_metadata(
        messages=[
            {"role": "user", "content": "测试"}
        ]
    )

    assert result["content"] == "测试生成内容"
    assert result["finish_reason"] == "stop"
    assert result["usage"]["total_tokens"] == 120