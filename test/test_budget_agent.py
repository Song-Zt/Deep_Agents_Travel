
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from agents.sub_agents import BudgetAgent


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    async def chat(self, messages, **kwargs):
        if self.call_count >= len(self.responses):
            raise RuntimeError("FakeLLM 没有更多预设响应")

        response = self.responses[self.call_count]
        self.call_count += 1
        return response

    async def close(self):
        pass


def make_params(
    total_budget=5000,
    days=3,
    travelers=2,
    city="北京",
    travel_style="comfortable",
):
    return {
        "total_budget": total_budget,
        "days": days,
        "travelers": travelers,
        "city": city,
        "travel_style": travel_style,
    }


def test_validate_budget_params():
    result = BudgetAgent._validate_params(make_params())

    assert result["total_budget"] == 5000
    assert result["days"] == 3
    assert result["travelers"] == 2
    assert result["travel_style"] == "comfortable"


def test_reject_invalid_total_budget():
    with pytest.raises(ValueError, match="旅行总预算"):
        BudgetAgent._validate_params(
            make_params(total_budget=0)
        )


def test_reject_invalid_days():
    with pytest.raises(ValueError, match="旅行天数"):
        BudgetAgent._validate_params(
            make_params(days=0)
        )


def test_reject_invalid_travelers():
    with pytest.raises(ValueError, match="出行人数"):
        BudgetAgent._validate_params(
            make_params(travelers=0)
        )


def test_reject_invalid_travel_style():
    with pytest.raises(ValueError, match="旅行风格"):
        BudgetAgent._validate_params(
            make_params(travel_style="unknown")
        )


def test_calculate_comfortable_budget():
    result = BudgetAgent.calculate_budget(make_params())

    assert result["total_budget"] == 5000

    assert result["allocation"]["accommodation"]["amount"] == 1500
    assert result["allocation"]["food"]["amount"] == 1250
    assert result["allocation"]["transport"]["amount"] == 1000
    assert result["allocation"]["tickets"]["amount"] == 750
    assert result["allocation"]["reserve"]["amount"] == 500

    assert result["per_person_budget"] == 2500
    assert result["per_person_daily_budget"] == 833.33


def test_calculate_economy_budget():
    result = BudgetAgent.calculate_budget(
        make_params(travel_style="economy")
    )

    assert result["allocation"]["accommodation"]["amount"] == 1250
    assert result["allocation"]["food"]["amount"] == 1250
    assert result["allocation"]["transport"]["amount"] == 1000
    assert result["allocation"]["tickets"]["amount"] == 750
    assert result["allocation"]["reserve"]["amount"] == 750


def test_calculate_luxury_budget():
    result = BudgetAgent.calculate_budget(
        make_params(travel_style="luxury")
    )

    assert result["allocation"]["accommodation"]["amount"] == 2000
    assert result["allocation"]["food"]["amount"] == 1250
    assert result["allocation"]["transport"]["amount"] == 750
    assert result["allocation"]["tickets"]["amount"] == 500
    assert result["allocation"]["reserve"]["amount"] == 500


@pytest.mark.asyncio
async def test_extract_budget_params():
    llm = FakeLLM([
        '{"total_budget":5000,"days":3,'
        '"travelers":2,"city":"北京",'
        '"travel_style":"comfortable"}'
    ])

    agent = BudgetAgent(llm_client=llm)

    result = await agent.extract_budget_params(
        "两个人去北京玩三天，总预算5000元，舒适型"
    )

    assert result["total_budget"] == 5000
    assert result["days"] == 3
    assert result["travelers"] == 2
    assert result["city"] == "北京"


@pytest.mark.asyncio
async def test_plan_budget():
    llm = FakeLLM([
        '{"total_budget":5000,"days":3,'
        '"travelers":2,"city":"北京",'
        '"travel_style":"comfortable"}',
        "这是一份北京三日游预算方案。",
    ])

    agent = BudgetAgent(llm_client=llm)

    result = await agent.plan_budget(
        "两个人去北京玩三天，总预算5000元"
    )

    assert result["success"] is True
    assert result["task"] == "budget"
    assert result["budget_data"]["total_budget"] == 5000
    assert result["budget_data"]["per_person_budget"] == 2500
    assert result["answer"] == "这是一份北京三日游预算方案。"
    assert llm.call_count == 2


@pytest.mark.asyncio
async def test_empty_input():
    llm = FakeLLM([])
    agent = BudgetAgent(llm_client=llm)

    with pytest.raises(ValueError, match="用户输入不能为空"):
        await agent.extract_budget_params(" ")
