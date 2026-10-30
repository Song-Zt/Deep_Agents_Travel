"""
旅行助手 Web 服务。

提供：
1. 静态前端页面
2. 会话管理接口（SQLite 持久化）
3. SSE 流式对话接口，实时推送生成内容和工具调用事件

启动方式：
    python -m web
或：
    uvicorn web.app:app --reload --port 8000
"""

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from agents.supervisor_agent import SupervisorAgent
from conversation.conversation_manager import (
    ConversationManager,
    ConversationRunner,
)
from conversation.session import validate_session_id
from tools.events import (
    reset_tool_event_listener,
    set_tool_event_listener,
)

STATIC_DIR = Path(__file__).parent / "static"

DEFAULT_DATABASE_PATH = Path("agent_files") / "conversations.db"

# SSE 心跳间隔，避免代理在长时间工具调用时断开连接
SSE_PING_SECONDS = 15


def _default_database_path() -> Path:
    return Path(
        os.getenv("CONVERSATION_DB", str(DEFAULT_DATABASE_PATH))
    )


def _sse(event: dict[str, Any]) -> str:
    """把事件序列化成 SSE 数据块。"""

    name = event.get("event") or "message"
    data = json.dumps(
        event.get("data") or {},
        ensure_ascii=False,
        default=str,
    )

    return f"event: {name}\ndata: {data}\n\n"


def _error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"success": False, "error": message},
        status_code=status_code,
    )


def create_app(
    agent: SupervisorAgent | None = None,
    manager: ConversationManager | None = None,
    database_path: str | Path | None = None,
) -> Starlette:
    """
    创建 Web 应用。

    agent / manager 可注入，方便测试时替换掉真实模型和数据库。
    """

    state: dict[str, Any] = {
        "agent": agent,
        "manager": manager,
        "database_path": database_path,
        "lock": None,
        "lock_loop": None,
    }

    def get_manager() -> ConversationManager:
        if state["manager"] is None:
            state["manager"] = ConversationManager(
                database_path=(
                    Path(state["database_path"])
                    if state["database_path"] is not None
                    else _default_database_path()
                )
            )

        return state["manager"]

    def get_agent() -> SupervisorAgent:
        if state["agent"] is None:
            state["agent"] = SupervisorAgent()

        return state["agent"]

    async def get_lock() -> asyncio.Lock:
        # 本地单用户场景：同一时间只跑一个对话，
        # 避免共享的模型/高德客户端被并发压垮。
        loop = asyncio.get_running_loop()

        if state["lock"] is None or state["lock_loop"] is not loop:
            state["lock"] = asyncio.Lock()
            state["lock_loop"] = loop

        return state["lock"]

    async def index(request: Request) -> Response:
        return HTMLResponse(
            (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        )

    async def health(request: Request) -> Response:
        return JSONResponse({"success": True, "data": {"status": "ok"}})

    async def list_sessions(request: Request) -> Response:
        summaries = get_manager().list_session_summaries()

        return JSONResponse(
            {"success": True, "data": summaries},
        )

    async def create_session(request: Request) -> Response:
        try:
            payload = await request.json()

        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}

        if not isinstance(payload, dict):
            payload = {}

        requested_id = payload.get("session_id")

        if requested_id is not None:
            try:
                validate_session_id(requested_id)

            except ValueError as exc:
                return _error(str(exc))

            if get_manager().get_session(requested_id) is not None:
                return _error(f"会话已存在：{requested_id}", 409)

        session = get_manager().create_session(requested_id)

        return JSONResponse(
            {
                "success": True,
                "data": {
                    "session_id": session.session_id,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "messages": [],
                },
            },
            status_code=201,
        )

    async def get_session(request: Request) -> Response:
        session_id = request.path_params["session_id"]

        try:
            validate_session_id(session_id)

        except ValueError as exc:
            return _error(str(exc))

        session = get_manager().get_session(session_id)

        if session is None:
            return _error("会话不存在", 404)

        return JSONResponse(
            {
                "success": True,
                "data": {
                    "session_id": session.session_id,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "messages": [
                        turn.to_dict()
                        for turn in session.turns
                    ],
                },
            }
        )

    async def delete_session(request: Request) -> Response:
        session_id = request.path_params["session_id"]

        try:
            validate_session_id(session_id)

        except ValueError as exc:
            return _error(str(exc))

        removed = get_manager().delete_session(session_id)

        if not removed:
            return _error("会话不存在", 404)

        return JSONResponse({"success": True, "data": {"removed": True}})

    async def chat(request: Request) -> Response:
        try:
            payload = await request.json()

        except (json.JSONDecodeError, UnicodeDecodeError):
            return _error("请求体必须是 JSON")

        if not isinstance(payload, dict):
            return _error("请求体必须是 JSON 对象")

        message = payload.get("message")
        session_id = payload.get("session_id")

        if not isinstance(message, str) or not message.strip():
            return _error("message 不能为空")

        if session_id is not None:
            try:
                validate_session_id(session_id)

            except ValueError as exc:
                return _error(str(exc))

        manager = get_manager()

        session = manager.get_or_create_session(session_id)

        async def event_stream() -> AsyncIterator[str]:
            queue: asyncio.Queue = asyncio.Queue()

            def listener(event: dict[str, Any]):
                queue.put_nowait(event)

            async def produce():
                token = set_tool_event_listener(listener)

                try:
                    lock = await get_lock()

                    async with lock:
                        runner = ConversationRunner(
                            agent=get_agent(),
                            manager=manager,
                            session_id=session.session_id,
                        )

                        async for event in runner.chat_stream(
                            message.strip()
                        ):
                            queue.put_nowait(event)

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    queue.put_nowait({
                        "event": "error",
                        "data": {
                            "type": type(exc).__name__,
                            "message": str(exc),
                        },
                    })

                finally:
                    reset_tool_event_listener(token)
                    queue.put_nowait(None)

            task = asyncio.create_task(produce())

            yield _sse({
                "event": "session",
                "data": {
                    "session_id": session.session_id,
                },
            })

            try:
                while True:
                    try:
                        item = await asyncio.wait_for(
                            queue.get(),
                            timeout=SSE_PING_SECONDS,
                        )

                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue

                    if item is None:
                        break

                    yield _sse(item)

            finally:
                if not task.done():
                    task.cancel()

                with contextlib.suppress(BaseException):
                    await task

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    routes = [
        Route("/", index),
        Route("/api/health", health),
        Route("/api/sessions", list_sessions, methods=["GET"]),
        Route("/api/sessions", create_session, methods=["POST"]),
        Route(
            "/api/sessions/{session_id}",
            get_session,
            methods=["GET"],
        ),
        Route(
            "/api/sessions/{session_id}",
            delete_session,
            methods=["DELETE"],
        ),
        Route("/api/chat", chat, methods=["POST"]),
        Mount(
            "/static",
            app=StaticFiles(directory=STATIC_DIR),
            name="static",
        ),
    ]

    return Starlette(routes=routes)


app = create_app()
