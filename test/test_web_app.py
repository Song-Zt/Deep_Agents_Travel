import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
import pytest

from conversation.conversation_manager import ConversationManager
from tools.events import emit_tool_event
from web.app import create_app


class FakeAgent:
    """模拟 Supervisor，验证 SSE 事件与工具调用展示。"""

    async def run_stream(self, user_input, history=None):
        emit_tool_event({
            "event": "tool",
            "data": {
                "tool": "search_places",
                "status": "start",
                "arguments": '{"keywords": "北京"}',
            },
        })

        yield {
            "event": "stage",
            "data": {"stage": "summary", "label": "汇总生成回答"},
        }

        emit_tool_event({
            "event": "tool",
            "data": {
                "tool": "search_places",
                "status": "end",
                "success": True,
                "duration_ms": 42,
                "summary": "返回 3 个地点",
            },
        })

        yield {"event": "delta", "data": {"text": "北京"}}
        yield {"event": "delta", "data": {"text": "值得一去"}}

        yield {
            "event": "done",
            "data": {
                "success": True,
                "task_type": "general",
                "classification": {
                    "task_type": "general",
                    "sub_tasks": [],
                    "reason": "测试",
                },
                "resolved_input": user_input,
                "execution_results": [],
                "answer": "北京值得一去",
                "error": None,
            },
        }

    async def close(self):
        pass


class FailingAgent:
    async def run_stream(self, user_input, history=None):
        raise RuntimeError("模型不可用")
        yield {}  # pragma: no cover

    async def close(self):
        pass


def _app(tmp_path, agent=None):
    manager = ConversationManager(
        database_path=tmp_path / "chat.db"
    )

    return create_app(
        agent=agent or FakeAgent(),
        manager=manager,
    )


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_health(tmp_path):
    async with _client(_app(tmp_path)) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


@pytest.mark.asyncio
async def test_index_and_static(tmp_path):
    async with _client(_app(tmp_path)) as client:
        page = await client.get("/")
        script = await client.get("/static/app.js")
        style = await client.get("/static/style.css")

    assert page.status_code == 200
    assert "旅行助手" in page.text

    assert script.status_code == 200
    assert "sendMessage" in script.text

    assert style.status_code == 200


@pytest.mark.asyncio
async def test_session_lifecycle(tmp_path):
    async with _client(_app(tmp_path)) as client:
        created = await client.post("/api/sessions")

        assert created.status_code == 201

        session_id = created.json()["data"]["session_id"]

        listed = await client.get("/api/sessions")

        assert [item["session_id"] for item in listed.json()["data"]] == [
            session_id
        ]

        removed = await client.delete(f"/api/sessions/{session_id}")
        assert removed.status_code == 200

        missing = await client.get(f"/api/sessions/{session_id}")
        assert missing.status_code == 404

        again = await client.delete(f"/api/sessions/{session_id}")
        assert again.status_code == 404


@pytest.mark.asyncio
async def test_chat_streams_events_and_persists(tmp_path):
    async with _client(_app(tmp_path)) as client:
        response = await client.post(
            "/api/chat",
            json={"message": "推荐北京景点"},
            timeout=30,
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "text/event-stream"
        )

        body = response.text

        assert "event: session" in body
        assert "event: tool" in body
        assert '"status": "start"' in body
        assert '"duration_ms": 42' in body
        assert "event: delta" in body
        assert "event: done" in body

        session_id = _session_id_from(body)

        detail = await client.get(f"/api/sessions/{session_id}")

        messages = detail.json()["data"]["messages"]

        assert [item["role"] for item in messages] == ["user", "assistant"]
        assert messages[0]["content"] == "推荐北京景点"
        assert messages[1]["content"] == "北京值得一去"


@pytest.mark.asyncio
async def test_chat_reuses_existing_session(tmp_path):
    async with _client(_app(tmp_path)) as client:
        created = await client.post("/api/sessions")
        session_id = created.json()["data"]["session_id"]

        response = await client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "你好"},
            timeout=30,
        )

        assert response.status_code == 200

        detail = await client.get(f"/api/sessions/{session_id}")
        messages = detail.json()["data"]["messages"]

    assert len(messages) == 2


@pytest.mark.asyncio
async def test_chat_validates_input(tmp_path):
    async with _client(_app(tmp_path)) as client:
        empty = await client.post("/api/chat", json={"message": "  "})
        bad_id = await client.post(
            "/api/chat",
            json={"session_id": "../x", "message": "你好"},
        )

    assert empty.status_code == 400
    assert bad_id.status_code == 400


@pytest.mark.asyncio
async def test_chat_reports_agent_error(tmp_path):
    async with _client(_app(tmp_path, agent=FailingAgent())) as client:
        response = await client.post(
            "/api/chat",
            json={"message": "你好"},
            timeout=30,
        )

        body = response.text
        session_id = _session_id_from(body)

        detail = await client.get(f"/api/sessions/{session_id}")

    assert "event: error" in body
    assert "模型不可用" in body

    # 失败的一轮不写入历史
    assert detail.json()["data"]["messages"] == []


def _session_id_from(body):
    for block in body.split("\n\n"):
        if block.startswith("event: session"):
            for line in block.split("\n"):
                if line.startswith("data: "):
                    import json

                    return json.loads(line[6:])["session_id"]

    raise AssertionError("SSE 中没有 session 事件")
