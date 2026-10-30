
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
    创建 Supervisor，并用 Mock 替换四个子 Agent。
    不连接真实 LLM 和 MCP。
    """
    agent = SupervisorAgent.__new__(SupervisorAgent)

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
async def test_execute_sightseeing(supervisor):
    """测试景点任务能否正确调度。"""

    result = await supervisor._execute_sub_task(
        "sightseeing",
        "推荐北京景点",
    )

    assert result["success"] is True
    assert result["task"] == "sightseeing"

    supervisor.sightseeing_agent.recommend.assert_awaited_once_with(
        "推荐北京景点"
    )


@pytest.mark.asyncio
async def test_execute_route(supervisor):
    """测试路线任务能否正确调度。"""

    result = await supervisor._execute_sub_task(
        "route",
        "规划故宫到天坛的路线",
    )

    assert result["success"] is True
    assert result["task"] == "route"

    supervisor.route_agent.plan_route.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_budget(supervisor):
    """测试预算任务能否正确调度。"""

    result = await supervisor._execute_sub_task(
        "budget",
        "估算北京旅游预算",
    )

    assert result["success"] is True
    assert result["task"] == "budget"

    supervisor.budget_agent.plan_budget.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_itinerary(supervisor):
    """测试行程审核任务能否正确调度。"""

    result = await supervisor._execute_sub_task(
        "itinerary",
        "审核我的北京三日游行程",
    )

    assert result["success"] is True
    assert result["task"] == "itinerary"

    supervisor.itinerary_agent.review_itinerary.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_task(supervisor):
    """测试不存在的任务类型。"""

    result = await supervisor._execute_sub_task(
        "unknown",
        "测试任务",
    )

    assert result["success"] is False
    assert "没有找到对应的 Agent" in result["error"]


@pytest.mark.asyncio
async def test_sub_agent_exception(supervisor):
    """测试子 Agent 出错时能否捕获异常。"""

    supervisor.route_agent.plan_route.side_effect = RuntimeError(
        "路线服务异常"
    )

    result = await supervisor._execute_sub_task(
        "route",
        "规划路线",
    )

    assert result["success"] is False
    assert result["error"]["type"] == "RuntimeError"
    assert result["error"]["message"] == "路线服务异常"


@pytest.mark.asyncio
async def test_multi_task_execution_order(supervisor):
    """测试多个任务是否按指定顺序执行。"""

    execution_order = []

    async def sightseeing_mock(user_input):
        execution_order.append("sightseeing")
        return {"success": True, "task": "sightseeing"}

    async def route_mock(user_input):
        execution_order.append("route")
        return {"success": True, "task": "route"}

    async def budget_mock(user_input):
        execution_order.append("budget")
        return {"success": True, "task": "budget"}

    supervisor.sightseeing_agent.recommend.side_effect = sightseeing_mock
    supervisor.route_agent.plan_route.side_effect = route_mock
    supervisor.budget_agent.plan_budget.side_effect = budget_mock

    tasks = ["sightseeing", "route", "budget"]

    results = []

    for task in tasks:
        result = await supervisor._execute_sub_task(
            task,
            "规划北京旅行",
        )
        results.append(result)

    assert execution_order == [
        "sightseeing",
        "route",
        "budget",
    ]

    assert all(item["success"] for item in results)


@pytest.mark.asyncio
async def test_failed_task_does_not_block_following_tasks(supervisor):
    """测试一个任务失败后，后续任务仍然可以执行。"""

    execution_order = []

    async def failed_route(user_input):
        execution_order.append("route")
        raise RuntimeError("路线查询失败")

    async def budget_mock(user_input):
        execution_order.append("budget")
        return {
            "success": True,
            "task": "budget",
        }

    supervisor.route_agent.plan_route.side_effect = failed_route
    supervisor.budget_agent.plan_budget.side_effect = budget_mock

    route_result = await supervisor._execute_sub_task(
        "route",
        "规划路线",
    )

    budget_result = await supervisor._execute_sub_task(
        "budget",
        "估算预算",
    )

    assert route_result["success"] is False
    assert budget_result["success"] is True

    assert execution_order == ["route", "budget"]
