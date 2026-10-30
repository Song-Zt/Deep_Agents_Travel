
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.sub_agents.budget_agent import BudgetAgent


def test_budget_allocation_mode():
    """测试用户提供总预算时的预算分配。"""
    params = {
        "total_budget": 3000,
        "days": 2,
        "travelers": 2,
        "city": "北京",
        "travel_style": "comfortable",
    }

    result = BudgetAgent.calculate_budget(params)

    assert result["mode"] == "budget_allocation"
    assert result["total_budget"] == 3000
    assert result["allocation"]["accommodation"]["amount"] == 900
    assert result["allocation"]["food"]["amount"] == 750
    assert result["per_person_budget"] == 1500


def test_budget_estimation_mode():
    """测试用户没有提供总预算时的自动估算。"""
    params = {
        "total_budget": None,
        "days": 2,
        "travelers": 2,
        "city": "北京",
        "travel_style": "comfortable",
    }

    result = BudgetAgent.calculate_budget(params)

    assert result["mode"] == "budget_estimation"
    assert result["total_budget"] == 1892
    assert result["allocation"]["accommodation"]["amount"] == 400
    assert result["allocation"]["food"]["amount"] == 600
    assert result["allocation"]["reserve"]["amount"] == 172
    assert result["per_person_budget"] == 946


def test_economy_estimation_mode():
    """测试经济型自动估算。"""
    params = {
        "total_budget": None,
        "days": 3,
        "travelers": 2,
        "city": "上海",
        "travel_style": "economy",
    }

    result = BudgetAgent.calculate_budget(params)

    assert result["mode"] == "budget_estimation"
    assert result["total_budget"] > 0
    assert result["travel_style"] == "economy"


def test_invalid_days():
    """测试天数校验。"""
    params = {
        "total_budget": None,
        "days": 0,
        "travelers": 2,
        "city": "北京",
        "travel_style": "comfortable",
    }

    try:
        BudgetAgent.calculate_budget(params)
    except ValueError as exc:
        assert "旅行天数" in str(exc)
    else:
        raise AssertionError("天数为 0 时应该抛出 ValueError")


def test_invalid_total_budget():
    """测试非法总预算。"""
    params = {
        "total_budget": -100,
        "days": 2,
        "travelers": 2,
        "city": "北京",
        "travel_style": "comfortable",
    }

    try:
        BudgetAgent.calculate_budget(params)
    except ValueError as exc:
        assert "旅行总预算" in str(exc)
    else:
        raise AssertionError("负数预算应该抛出 ValueError")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
