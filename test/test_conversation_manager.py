
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from conversation import (
    ConversationManager,
    ConversationRunner,
    ConversationSession,
)


class FakeAgent:
    """模拟 Supervisor，记录每轮收到的历史消息。"""

    def __init__(self, fail_on_call: int | None = None):
        self.calls = []
        self.fail_on_call = fail_on_call

    async def run(self, user_input, history=None):
        self.calls.append({
            "user_input": user_input,
            "history": list(history or []),
        })

        if self.fail_on_call == len(self.calls):
            raise RuntimeError("模拟执行失败")

        return {
            "answer": f"回答：{user_input}",
            "task_type": "general",
        }

    async def close(self):
        pass


def test_session_records_turns():
    session = ConversationSession("s1")

    session.add_user("推荐北京景点")
    session.add_assistant("推荐故宫和天坛")

    assert session.history() == [
        {"role": "user", "content": "推荐北京景点"},
        {"role": "assistant", "content": "推荐故宫和天坛"},
    ]


def test_history_limit():
    session = ConversationSession("s1")

    session.add_user("第一轮")
    session.add_assistant("第一轮回答")
    session.add_user("第二轮")

    assert session.history(limit=1) == [
        {"role": "user", "content": "第二轮"},
    ]


def test_session_trims_old_turns():
    session = ConversationSession("s1", max_turns=4)

    for index in range(6):
        session.add_user(f"消息{index}")

    assert len(session.turns) == 4
    assert session.turns[0].content == "消息2"


def test_invalid_session_id_rejected():
    with pytest.raises(ValueError, match="非法的会话 ID"):
        ConversationSession("../etc/passwd")


def test_manager_persists_sessions(tmp_path):
    manager = ConversationManager(storage_dir=tmp_path)

    manager.record_user("s1", "你好")
    manager.record_assistant("s1", "你好，需要规划旅行吗？")

    # 新管理器从磁盘恢复
    reloaded = ConversationManager(storage_dir=tmp_path)

    assert reloaded.list_sessions() == ["s1"]
    assert reloaded.history("s1") == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，需要规划旅行吗？"},
    ]


def test_manager_reset_and_delete(tmp_path):
    manager = ConversationManager(storage_dir=tmp_path)

    manager.record_user("s1", "你好")
    manager.reset("s1")

    assert manager.history("s1") == []

    manager.record_user("s1", "再来一次")
    manager.delete_session("s1")

    assert manager.get_session("s1") is None
    assert manager.list_sessions() == []


@pytest.mark.asyncio
async def test_runner_passes_history_to_agent():
    agent = FakeAgent()
    manager = ConversationManager()
    runner = ConversationRunner(agent=agent, manager=manager, session_id="s1")

    await runner.chat("推荐北京景点")
    await runner.chat("那上海呢？")

    assert agent.calls[0]["history"] == []

    assert agent.calls[1]["history"] == [
        {"role": "user", "content": "推荐北京景点"},
        {"role": "assistant", "content": "回答：推荐北京景点"},
    ]

    assert runner.session.history() == [
        {"role": "user", "content": "推荐北京景点"},
        {"role": "assistant", "content": "回答：推荐北京景点"},
        {"role": "user", "content": "那上海呢？"},
        {"role": "assistant", "content": "回答：那上海呢？"},
    ]


@pytest.mark.asyncio
async def test_runner_drops_failed_turn():
    agent = FakeAgent(fail_on_call=1)
    runner = ConversationRunner(
        agent=agent,
        manager=ConversationManager(),
        session_id="s1",
    )

    with pytest.raises(RuntimeError):
        await runner.chat("推荐北京景点")

    assert runner.session.history() == []


@pytest.mark.asyncio
async def test_runner_reset():
    agent = FakeAgent()
    runner = ConversationRunner(
        agent=agent,
        manager=ConversationManager(),
        session_id="s1",
    )

    await runner.chat("推荐北京景点")
    runner.reset()

    assert runner.session.history() == []
