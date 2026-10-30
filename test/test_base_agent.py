import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from agents import BaseAgent


class FakeLLM:
    """模拟 LLM 客户端"""

    def __init__(self):
        self.responses = ["你好，我是旅行助手。", "北京适合游览故宫。"]
        self.call_count = 0
        self.last_messages = None
        self.closed = False

    async def chat(self, messages):
        self.last_messages = messages
        response = self.responses[self.call_count]
        self.call_count += 1
        return response

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_agent_run():
    llm = FakeLLM()

    agent = BaseAgent(
        name="旅行助手",
        system_prompt="你是一个旅行助手。",
        llm_client=llm,
    )

    result = await agent.run("你好")

    assert result == "你好，我是旅行助手。"
    assert len(agent.messages) == 3
    assert agent.messages[0]["role"] == "system"
    assert agent.messages[1]["role"] == "user"
    assert agent.messages[2]["role"] == "assistant"


@pytest.mark.asyncio
async def test_agent_multi_turn():
    llm = FakeLLM()

    agent = BaseAgent(
        name="旅行助手",
        system_prompt="你是一个旅行助手。",
        llm_client=llm,
    )

    await agent.run("你好")
    result = await agent.run("北京有哪些景点？")

    assert result == "北京适合游览故宫。"
    assert len(agent.messages) == 5
    assert llm.call_count == 2


def test_agent_reset():
    llm = FakeLLM()

    agent = BaseAgent(
        name="旅行助手",
        system_prompt="你是一个旅行助手。",
        llm_client=llm,
    )

    agent.messages.append({
        "role": "user",
        "content": "你好",
    })

    agent.reset()

    assert len(agent.messages) == 1
    assert agent.messages[0]["role"] == "system"


def test_agent_empty_name():
    llm = FakeLLM()

    with pytest.raises(ValueError):
        BaseAgent(
            name="",
            system_prompt="你是一个旅行助手。",
            llm_client=llm,
        )


def test_agent_empty_prompt():
    llm = FakeLLM()

    with pytest.raises(ValueError):
        BaseAgent(
            name="旅行助手",
            system_prompt="",
            llm_client=llm,
        )


@pytest.mark.asyncio
async def test_agent_does_not_close_shared_llm():
    llm = FakeLLM()

    agent = BaseAgent(
        name="旅行助手",
        system_prompt="你是一个旅行助手。",
        llm_client=llm,
    )

    await agent.close()

    assert llm.closed is False