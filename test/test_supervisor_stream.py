import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from agents import SupervisorAgent


def _classification(task_type, sub_tasks=None, reason="判断理由"):
    return json.dumps(
        {
            "task_type": task_type,
            "sub_tasks": sub_tasks or [],
            "reason": reason,
        },
        ensure_ascii=False,
    )


class StreamingLLM:
    """chat 按顺序返回，chat_stream 分段吐出文本。"""

    def __init__(self, chat_responses, stream_chunks):
        self.chat_responses = list(chat_responses)
        self.stream_chunks = list(stream_chunks)
        self.chat_calls = []
        self.stream_calls = []

    async def chat(self, messages, **kwargs):
        self.chat_calls.append(messages)

        if not self.chat_responses:
            raise RuntimeError("没有更多预设 chat 响应")

        return self.chat_responses.pop(0)

    async def chat_stream(self, messages, **kwargs):
        self.stream_calls.append({"messages": messages, "kwargs": kwargs})

        for chunk in self.stream_chunks:
            yield chunk

    async def close(self):
        pass


async def _collect(agent, user_input, history=None):
    return [
        event
        async for event in agent.run_stream(user_input, history=history)
    ]


@pytest.mark.asyncio
async def test_run_stream_general_streams_deltas():
    llm = StreamingLLM(
        chat_responses=[_classification("general")],
        stream_chunks=["你好", "，", "有什么可以帮你？"],
    )
    agent = SupervisorAgent(llm_client=llm)

    events = await _collect(agent, "你好")

    names = [event["event"] for event in events]

    assert names == [
        "stage",
        "stage",
        "classified",
        "delta",
        "delta",
        "delta",
        "done",
    ]

    assert events[3]["data"]["text"] == "你好"

    done = events[-1]["data"]
    assert done["success"] is True
    assert done["task_type"] == "general"
    assert done["answer"] == "你好，有什么可以帮你？"


@pytest.mark.asyncio
async def test_run_stream_sub_task_and_summary():
    llm = StreamingLLM(
        chat_responses=[_classification("sightseeing", reason="景点推荐")],
        stream_chunks=["推荐", "颐和园。"],
    )
    agent = SupervisorAgent(llm_client=llm)

    async def fake_execute(task_type, user_input):
        assert task_type == "sightseeing"
        assert user_input == "推荐北京景点"

        return {
            "success": True,
            "task": task_type,
            "answer": "颐和园、故宫",
        }

    agent._execute_sub_task = fake_execute

    events = await _collect(agent, "推荐北京景点")

    names = [event["event"] for event in events]

    assert "subtask_done" in names
    assert names.index("subtask_done") < names.index("delta")

    subtask = next(e for e in events if e["event"] == "subtask_done")
    assert subtask["data"]["task"] == "sightseeing"
    assert subtask["data"]["success"] is True

    done = events[-1]["data"]
    assert done["answer"] == "推荐颐和园。"
    assert done["execution_results"][0]["answer"] == "颐和园、故宫"

    # 汇总是流式生成的
    assert llm.stream_calls


@pytest.mark.asyncio
async def test_run_stream_rewrites_follow_up_with_history():
    llm = StreamingLLM(
        chat_responses=[
            "推荐几个上海的经典景点",
            _classification("sightseeing"),
        ],
        stream_chunks=["上海外滩"],
    )
    agent = SupervisorAgent(llm_client=llm)

    async def fake_execute(task_type, user_input):
        return {"success": True, "task": task_type, "answer": user_input}

    agent._execute_sub_task = fake_execute

    events = await _collect(
        agent,
        "那上海呢？",
        history=[
            {"role": "user", "content": "推荐几个北京的景点"},
            {"role": "assistant", "content": "颐和园、故宫都不错。"},
        ],
    )

    rewritten = next(
        event for event in events if event["event"] == "rewritten"
    )

    assert rewritten["data"]["original"] == "那上海呢？"
    assert rewritten["data"]["resolved"] == "推荐几个上海的经典景点"

    done = events[-1]["data"]
    assert done["resolved_input"] == "推荐几个上海的经典景点"


@pytest.mark.asyncio
async def test_run_stream_falls_back_when_summary_fails():
    class BrokenStreamLLM(StreamingLLM):
        async def chat_stream(self, messages, **kwargs):
            raise RuntimeError("模型连接中断")
            yield ""  # pragma: no cover

    llm = BrokenStreamLLM(
        chat_responses=[_classification("route")],
        stream_chunks=[],
    )
    agent = SupervisorAgent(llm_client=llm)

    async def fake_execute(task_type, user_input):
        return {"success": True, "task": task_type, "answer": "步行 10 分钟"}

    agent._execute_sub_task = fake_execute

    events = await _collect(agent, "从故宫到天坛怎么走")

    done = events[-1]["data"]

    assert done["success"] is False
    assert done["error"]["message"] == "模型连接中断"
    assert "步行 10 分钟" in done["answer"]


@pytest.mark.asyncio
async def test_run_stream_rejects_empty_input():
    llm = StreamingLLM([], [])
    agent = SupervisorAgent(llm_client=llm)

    with pytest.raises(ValueError):
        await _collect(agent, "   ")
