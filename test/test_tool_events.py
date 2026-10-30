import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.events import (
    emit_tool_event,
    format_arguments,
    reset_tool_event_listener,
    set_tool_event_listener,
    summarize_result,
)


def test_emit_without_listener_is_noop():
    # 没有监听器时不应该抛异常
    emit_tool_event({"event": "tool", "data": {"tool": "x"}})


def test_listener_receives_and_can_be_reset():
    received = []

    token = set_tool_event_listener(received.append)

    try:
        emit_tool_event({"event": "tool", "data": {"tool": "search_places"}})

    finally:
        reset_tool_event_listener(token)

    assert received == [
        {"event": "tool", "data": {"tool": "search_places"}},
    ]

    emit_tool_event({"event": "tool", "data": {"tool": "ignored"}})

    assert len(received) == 1


def test_listener_exception_is_swallowed():
    def broken(_):
        raise RuntimeError("前端队列已关闭")

    token = set_tool_event_listener(broken)

    try:
        emit_tool_event({"event": "tool", "data": {}})

    finally:
        reset_tool_event_listener(token)


def test_format_arguments_truncates():
    assert format_arguments(None) == ""

    text = format_arguments({"keywords": "北京"}, max_length=10)

    assert text.endswith("...")
    assert len(text) == 13


def test_summarize_result_variants():
    assert summarize_result({"success": False, "error": {"message": "超时"}}) == "失败：超时"
    assert summarize_result({"success": True, "data": [1, 2, 3]}) == "返回 3 条结果"
    assert summarize_result({"success": True, "data": {"places": [1]}}) == "返回 1 个地点"
    assert summarize_result({"success": True, "data": {"a": 1}}) == "返回 1 个字段"
    assert summarize_result("plain") == "完成"
