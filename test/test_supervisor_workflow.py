
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.supervisor_agent import SupervisorAgent


@pytest.fixture
def supervisor():
    """
    创建不依赖真实 LLM 和 MCP 的 Supervisor。
    """

    agent = SupervisorAgent.__new__(SupervisorAgent)

    # 模拟 LLM
    agent.llm = type("MockLLM", (), {})()
    agent.llm.chat = AsyncMock(return_value="普通对话回复")

    # 模拟任务分类
    agent.classify_task = AsyncMock()

    # 模拟最终结果汇总
    agent._summarize_results = AsyncMock(
        return_value="这是汇总后的旅行方案"
    )

    # 模拟四个子 Agent
    agent.sightseeing_agent = type("MockAgent", (), {})()
    agent.route_agent = type("MockAgent", (), {})()
    agent.budget_agent = type("MockAgent", (), {})()
    agent.itinerary_agent = type("MockAgent", (), {})()

    agent.sightseeing_agent.recommend = AsyncMock(
        return_value={
            "success": True,
            "task": "sightseeing",
            "answer": "景点推荐结果",
        }
    )

    agent.route_agent.plan_route = AsyncMock(
        return_value={
            "success": True,
            "task": "route",
            "answer": "路线规划结果",
        }
    )

    agent.budget_agent.plan_budget = AsyncMock(
        return_value={
            "success": True,
            "task": "budget",
            "answer": "预算估算结果",
        }
    )

    agent.itinerary_agent.review_itinerary = AsyncMock(
        return_value={
            "success": True,
            "task": "itinerary",
            "answer": "行程审核结果",
        }
    )

    agent.sub_agents = {
        "sightseeing": agent.sightseeing_agent,
        "route": agent.route_agent,
        "budget": agent.budget_agent,
        "itinerary": agent.itinerary_agent,
    }

    return agent


@pytest.mark.asyncio
async def test_single_task_workflow(supervisor):
    """测试单一任务的完整执行流程。"""

    supervisor.classify_task.return_value = {
        "task_type": "sightseeing",
        "sub_tasks": [],
        "reason": "用户只需要景点推荐",
    }

    result = await supervisor.run("推荐北京的旅游景点")

    assert result["success"] is True
    assert result["task_type"] == "sightseeing"
    assert len(result["execution_results"]) == 1
    assert result["answer"] == "这是汇总后的旅行方案"

    supervisor.sightseeing_agent.recommend.assert_awaited_once()
    supervisor._summarize_results.assert_awaited_once()


@pytest.mark.asyncio
async def test_multi_task_workflow(supervisor):
    """测试多个子 Agent 的完整执行流程。"""

    supervisor.classify_task.return_value = {
        "task_type": "multi_task",
        "sub_tasks": [
            "sightseeing",
            "route",
            "budget",
        ],
        "reason": "用户提出了多个旅行需求",
    }

    result = await supervisor.run(
        "推荐北京景点，规划交通路线，并估算旅行预算"
    )

    assert result["success"] is True
    assert result["task_type"] == "multi_task"
    assert len(result["execution_results"]) == 3

    supervisor.sightseeing_agent.recommend.assert_awaited_once()
    supervisor.route_agent.plan_route.assert_awaited_once()
    supervisor.budget_agent.plan_budget.assert_awaited_once()

    supervisor._summarize_results.assert_awaited_once()


@pytest.mark.asyncio
async def test_general_workflow(supervisor):
    """测试普通聊天任务。"""

    supervisor.classify_task.return_value = {
        "task_type": "general",
        "sub_tasks": [],
        "reason": "用户只是普通问候",
    }

    result = await supervisor.run("你好")

    assert result["success"] is True
    assert result["task_type"] == "general"
    assert result["answer"] == "普通对话回复"
    assert result["execution_results"] == []

    supervisor.llm.chat.assert_awaited_once()
    supervisor._summarize_results.assert_not_awaited()


@pytest.mark.asyncio
async def test_sub_task_failure_workflow(supervisor):
    """测试一个子任务失败后，其他任务仍然执行。"""

    supervisor.classify_task.return_value = {
        "task_type": "multi_task",
        "sub_tasks": [
            "route",
            "budget",
        ],
        "reason": "用户需要路线和预算",
    }

    supervisor.route_agent.plan_route.side_effect = RuntimeError(
        "路线查询失败"
    )

    result = await supervisor.run(
        "规划路线并估算预算"
    )

    assert result["success"] is False
    assert len(result["execution_results"]) == 2

    assert result["execution_results"][0]["success"] is False
    assert result["execution_results"][1]["success"] is True

    supervisor.budget_agent.plan_budget.assert_awaited_once()

    # 即使某个子任务失败，仍然尝试汇总
    supervisor._summarize_results.assert_awaited_once()


@pytest.mark.asyncio
async def test_summary_failure_workflow(supervisor):
    """测试最终汇总失败时，是否保留原始执行结果。"""

    supervisor.classify_task.return_value = {
        "task_type": "budget",
        "sub_tasks": [],
        "reason": "用户需要预算估算",
    }

    supervisor._summarize_results.side_effect = RuntimeError(
        "LLM 汇总失败"
    )

    result = await supervisor.run("估算北京三日游预算")

    assert result["success"] is False
    assert result["error"]["type"] == "RuntimeError"

    # 原始子 Agent 结果仍然保留
    assert len(result["execution_results"]) == 1
    assert result["execution_results"][0]["success"] is True

    assert "汇总失败" in result["answer"]


@pytest.mark.asyncio
async def test_empty_input():
    """测试空输入校验。"""

    agent = SupervisorAgent.__new__(SupervisorAgent)

    with pytest.raises(ValueError, match="用户输入不能为空"):
        await agent.run("")

    with pytest.raises(ValueError, match="用户输入不能为空"):
        await agent.run("   ")
