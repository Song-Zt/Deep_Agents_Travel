
"""
工具调用事件广播。

Agent 执行工具时通过这里发出事件，
前端据此实时展示「正在调用什么工具、耗时多久、是否成功」。

使用 ContextVar 保存监听器，因此不同会话/请求之间互不影响。
"""

import json
from contextvars import ContextVar
from typing import Any, Callable

ToolEventListener = Callable[[dict[str, Any]], None]


_listener: ContextVar[ToolEventListener | None] = ContextVar(
    "tool_event_listener",
    default=None,
)


def set_tool_event_listener(
    listener: ToolEventListener | None,
) -> Any:
    """设置当前上下文的工具事件监听器，返回用于恢复的 token。"""

    return _listener.set(listener)


def reset_tool_event_listener(token: Any):
    """恢复之前的监听器。"""

    _listener.reset(token)


def emit_tool_event(event: dict[str, Any]):
    """
    广播一条工具事件。

    监听器自身的异常不能影响工具执行，这里直接吞掉。
    """

    listener = _listener.get()

    if listener is None:
        return

    try:
        listener(event)

    except Exception:
        pass


def format_arguments(
    arguments: dict[str, Any] | None,
    max_length: int = 500,
) -> str:
    """把工具参数转成适合展示的短字符串。"""

    if not arguments:
        return ""

    try:
        text = json.dumps(
            arguments,
            ensure_ascii=False,
            default=str,
        )

    except (TypeError, ValueError):
        text = str(arguments)

    if len(text) > max_length:
        text = text[:max_length] + "..."

    return text


def summarize_result(result: Any) -> str:
    """把工具返回结果压缩成一句话，用于前端展示。"""

    if not isinstance(result, dict):
        return "完成"

    if result.get("success") is False:
        error = result.get("error")

        if isinstance(error, dict):
            message = error.get("message") or error.get("type")
        else:
            message = str(error)

        return f"失败：{message}"[:200]

    data = result.get("data")

    if isinstance(data, list):
        return f"返回 {len(data)} 条结果"

    if isinstance(data, dict):
        places = data.get("places")

        if isinstance(places, list):
            return f"返回 {len(places)} 个地点"

        return f"返回 {len(data)} 个字段"

    return "完成"
