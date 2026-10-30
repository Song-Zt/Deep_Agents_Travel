import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from conversation.conversation_manager import (
    ConversationManager,
    ConversationRunner,
)
from conversation.session import ConversationSession
from conversation.storage import SQLiteStorage


def _session(session_id="s1", max_turns=40):
    return ConversationSession(session_id=session_id, max_turns=max_turns)


def test_sqlite_round_trip(tmp_path):
    storage = SQLiteStorage(tmp_path / "chat.db")

    session = _session()
    session.add_user("推荐北京景点")
    session.add_assistant("颐和园、故宫都不错。", metadata={"task_type": "sightseeing"})

    storage.save_session(session)

    loaded = storage.load_session("s1")

    assert loaded is not None
    assert loaded.session_id == "s1"
    assert [turn.role for turn in loaded.turns] == ["user", "assistant"]
    assert loaded.turns[1].content == "颐和园、故宫都不错。"
    assert loaded.turns[1].metadata == {"task_type": "sightseeing"}


def test_sqlite_load_missing_session_returns_none(tmp_path):
    storage = SQLiteStorage(tmp_path / "chat.db")

    assert storage.load_session("nope") is None


def test_sqlite_rejects_invalid_session_id(tmp_path):
    storage = SQLiteStorage(tmp_path / "chat.db")

    with pytest.raises(ValueError):
        storage.load_session("../etc/passwd")


def test_sqlite_trimming_is_persisted(tmp_path):
    storage = SQLiteStorage(tmp_path / "chat.db")

    session = _session(max_turns=4)

    for index in range(6):
        session.add_user(f"问题 {index}")
        session.add_assistant(f"回答 {index}")

    storage.save_session(session)

    loaded = storage.load_session("s1")

    assert len(loaded.turns) == 4
    assert loaded.turns[0].content == "问题 4"
    assert loaded.turns[-1].content == "回答 5"


def test_sqlite_list_session_summaries(tmp_path):
    storage = SQLiteStorage(tmp_path / "chat.db")

    first = _session("s1")
    first.add_user("北京三日游怎么安排？")
    first.add_assistant("可以这样安排……")
    storage.save_session(first)

    second = _session("s2")
    second.add_user("上海有什么好吃的")
    storage.save_session(second)

    summaries = storage.list_session_summaries()

    ids = [item["session_id"] for item in summaries]

    assert set(ids) == {"s1", "s2"}
    assert summaries[0]["session_id"] == "s2"  # 最近更新的排在前面
    assert summaries[0]["title"] == "上海有什么好吃的"
    assert summaries[0]["message_count"] == 1

    s1 = next(item for item in summaries if item["session_id"] == "s1")
    assert s1["title"] == "北京三日游怎么安排？"
    assert s1["message_count"] == 2


def test_sqlite_delete_session_cascades_messages(tmp_path):
    storage = SQLiteStorage(tmp_path / "chat.db")

    session = _session()
    session.add_user("你好")
    storage.save_session(session)

    assert storage.delete_session("s1") is True
    assert storage.load_session("s1") is None
    assert storage.delete_session("s1") is False


def test_manager_persists_across_instances(tmp_path):
    database_path = tmp_path / "chat.db"

    first = ConversationManager(database_path=database_path)
    first.record_user("s1", "推荐北京景点")
    first.record_assistant("s1", "颐和园不错。")

    second = ConversationManager(database_path=database_path)

    history = second.history("s1")

    assert history == [
        {"role": "user", "content": "推荐北京景点"},
        {"role": "assistant", "content": "颐和园不错。"},
    ]

    assert second.list_session_summaries()[0]["session_id"] == "s1"


def test_manager_delete_removes_from_storage(tmp_path):
    database_path = tmp_path / "chat.db"

    manager = ConversationManager(database_path=database_path)
    manager.record_user("s1", "你好")

    assert manager.delete_session("s1") is True

    reloaded = ConversationManager(database_path=database_path)

    assert reloaded.get_session("s1") is None
    assert reloaded.list_sessions() == []


class EchoAgent:
    """流式返回固定内容，用于测试会话落库。"""

    async def run_stream(self, user_input, history=None):
        yield {"event": "delta", "data": {"text": "回复："}}
        yield {"event": "delta", "data": {"text": user_input}}
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
                "answer": f"回复：{user_input}",
                "error": None,
            },
        }

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_runner_stream_records_conversation(tmp_path):
    manager = ConversationManager(database_path=tmp_path / "chat.db")

    runner = ConversationRunner(
        agent=EchoAgent(),
        manager=manager,
        session_id="s1",
    )

    events = [event async for event in runner.chat_stream("你好")]

    assert events[0]["event"] == "delta"
    assert events[-1]["event"] == "done"

    reloaded = ConversationManager(database_path=tmp_path / "chat.db")

    assert reloaded.history("s1") == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "回复：你好"},
    ]


class BrokenAgent:
    async def run_stream(self, user_input, history=None):
        raise RuntimeError("模型不可用")
        yield {}  # pragma: no cover

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_runner_stream_rolls_back_failed_turn(tmp_path):
    manager = ConversationManager(database_path=tmp_path / "chat.db")

    runner = ConversationRunner(
        agent=BrokenAgent(),
        manager=manager,
        session_id="s1",
    )

    with pytest.raises(RuntimeError):
        async for _ in runner.chat_stream("你好"):
            pass

    reloaded = ConversationManager(database_path=tmp_path / "chat.db")

    assert reloaded.history("s1") == []
