
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from agents import SupervisorAgent


class FakeLLM:
    """模拟大模型，不产生真实 API 调用。"""

    def __init__(self, response):
        self.response = response
        self.last_messages = None
        self.last_kwargs = None

    async def chat(self, messages, **kwargs):
        self.last_messages = messages
        self.last_kwargs = kwargs
        return self.response

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_classify_sightseeing():
    llm = FakeLLM(
        '{"task_type":"sightseeing",'
        '"sub_tasks":[],"reason":"用户需要景点推荐"}'
    )
    agent = SupervisorAgent(llm_client=llm)

    result = await agent.classify_task("推荐北京值得去的景点")

    assert result["task_type"] == "sightseeing"
    assert result["sub_tasks"] == []


@pytest.mark.asyncio
async def test_classify_route():
    llm = FakeLLM(
        '{"task_type":"route",'
        '"sub_tasks":[],"reason":"用户需要路线规划"}'
    )
    agent = SupervisorAgent(llm_client=llm)

    result = await agent.classify_task("从故宫到颐和园怎么走")

    assert result["task_type"] == "route"


@pytest.mark.asyncio
async def test_classify_multi_task():
    llm = FakeLLM(
        '{"task_type":"multi_task",'
        '"sub_tasks":["sightseeing","route","budget"],'
        '"reason":"用户同时需要景点推荐、路线和预算"}'
    )
    agent = SupervisorAgent(llm_client=llm)

    result = await agent.classify_task(
        "推荐北京景点，规划游览路线，并估算费用"
    )

    assert result["task_type"] == "multi_task"
    assert result["sub_tasks"] == [
        "sightseeing",
        "route",
        "budget",
    ]


@pytest.mark.asyncio
async def test_classify_general():
    llm = FakeLLM(
        '{"task_type":"general",'
        '"sub_tasks":[],"reason":"用户只是问候"}'
    )
    agent = SupervisorAgent(llm_client=llm)

    result = await agent.classify_task("你好")

    assert result["task_type"] == "general"


@pytest.mark.asyncio
async def test_parse_markdown_json():
    llm = FakeLLM(
        '```json\n'
        '{"task_type":"budget",'
        '"sub_tasks":[],"reason":"用户需要预算估算"}\n'
        '```'
    )
    agent = SupervisorAgent(llm_client=llm)

    result = await agent.classify_task("北京旅游大概需要多少钱")

    assert result["task_type"] == "budget"


@pytest.mark.asyncio
async def test_invalid_task_type():
    llm = FakeLLM(
        '{"task_type":"shopping",'
        '"sub_tasks":[],"reason":"购物需求"}'
    )
    agent = SupervisorAgent(llm_client=llm)

    with pytest.raises(ValueError, match="不支持的任务类型"):
        await agent.classify_task("帮我购物")


@pytest.mark.asyncio
async def test_multi_task_without_sub_tasks():
    llm = FakeLLM(
        '{"task_type":"multi_task",'
        '"sub_tasks":[],"reason":"多个任务"}'
    )
    agent = SupervisorAgent(llm_client=llm)

    with pytest.raises(ValueError, match="至少一个子任务"):
        await agent.classify_task("帮我规划旅行")


@pytest.mark.asyncio
async def test_invalid_json():
    llm = FakeLLM("这不是 JSON")
    agent = SupervisorAgent(llm_client=llm)

    with pytest.raises(ValueError, match="不是有效 JSON"):
        await agent.classify_task("推荐北京景点")


@pytest.mark.asyncio
async def test_empty_input():
    llm = FakeLLM("{}")
    agent = SupervisorAgent(llm_client=llm)

    with pytest.raises(ValueError, match="用户输入不能为空"):
        await agent.classify_task("   ")


class SequencedLLM:
    """按顺序返回预设响应，用于覆盖多轮会话流程。"""

    def __init__(self, chat_responses, metadata_responses=None):
        self.chat_responses = list(chat_responses)
        self.metadata_responses = list(metadata_responses or [])
        self.calls = []
        self.metadata_calls = []

    async def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})

        if not self.chat_responses:
            raise RuntimeError("SequencedLLM 没有更多预设响应")

        return self.chat_responses.pop(0)

    async def chat_with_metadata(self, messages, **kwargs):
        self.metadata_calls.append({"messages": messages, "kwargs": kwargs})

        content = (
            self.metadata_responses.pop(0)
            if self.metadata_responses
            else ""
        )

        return {
            "content": content,
            "finish_reason": "stop",
            "usage": None,
        }

    async def close(self):
        pass


def test_build_history_messages_filters_invalid_items():
    result = SupervisorAgent._build_history_messages([
        {"role": "system", "content": "系统消息"},
        {"role": "user", "content": "   "},
        {"role": "user", "content": "你好"},
        "不是字典",
        {"role": "assistant", "content": "你好，需要规划旅行吗？"},
    ])

    assert result == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，需要规划旅行吗？"},
    ]


@pytest.mark.asyncio
async def test_classify_task_includes_history():
    llm = FakeLLM(
        '{"task_type":"sightseeing","sub_tasks":[],"reason":"景点推荐"}'
    )
    agent = SupervisorAgent(llm_client=llm)

    await agent.classify_task(
        "那上海呢？",
        history=[
            {"role": "user", "content": "推荐几个北京景点"},
            {"role": "assistant", "content": "推荐故宫和天坛。"},
        ],
    )

    assert llm.last_messages[0]["role"] == "system"
    assert llm.last_messages[1] == {
        "role": "user",
        "content": "推荐几个北京景点",
    }
    assert llm.last_messages[-1] == {
        "role": "user",
        "content": "那上海呢？",
    }


@pytest.mark.asyncio
async def test_run_rewrites_follow_up_query(monkeypatch):
    llm = SequencedLLM(
        chat_responses=[
            "推荐上海的经典景点",
            '{"task_type":"sightseeing","sub_tasks":[],"reason":"景点推荐"}',
        ],
        metadata_responses=["上海推荐：外滩、豫园。"],
    )

    agent = SupervisorAgent(llm_client=llm)

    received = {}

    async def fake_execute_sub_task(task_type, user_input):
        received["task_type"] = task_type
        received["user_input"] = user_input
        return {"success": True, "task": task_type, "answer": "ok"}

    monkeypatch.setattr(
        agent,
        "_execute_sub_task",
        fake_execute_sub_task,
    )

    result = await agent.run(
        "那上海呢？",
        history=[
            {"role": "user", "content": "推荐几个北京景点"},
            {"role": "assistant", "content": "推荐故宫和天坛。"},
        ],
    )

    assert result["resolved_input"] == "推荐上海的经典景点"
    assert received["user_input"] == "推荐上海的经典景点"

    # 改写请求、分类请求都带上了历史
    rewrite_messages = llm.calls[0]["messages"]
    classify_messages = llm.calls[1]["messages"]

    assert {
        "role": "user",
        "content": "推荐几个北京景点",
    } in rewrite_messages
    assert {
        "role": "user",
        "content": "推荐几个北京景点",
    } in classify_messages

    # 汇总请求同样带上了历史
    summary_messages = llm.metadata_calls[0]["messages"]

    assert {
        "role": "assistant",
        "content": "推荐故宫和天坛。",
    } in summary_messages


@pytest.mark.asyncio
async def test_run_without_history_skips_rewrite(monkeypatch):
    llm = SequencedLLM(
        chat_responses=[
            '{"task_type":"sightseeing","sub_tasks":[],"reason":"景点推荐"}',
        ],
        metadata_responses=["推荐故宫。"],
    )

    agent = SupervisorAgent(llm_client=llm)

    async def fake_execute_sub_task(task_type, user_input):
        return {"success": True, "task": task_type, "answer": "ok"}

    monkeypatch.setattr(
        agent,
        "_execute_sub_task",
        fake_execute_sub_task,
    )

    result = await agent.run("推荐北京景点")

    assert result["resolved_input"] == "推荐北京景点"
    # 没有历史时直接分类，不额外调用改写
    assert len(llm.calls) == 1
