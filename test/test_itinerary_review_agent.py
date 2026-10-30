
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from agents.sub_agents import ItineraryReviewAgent


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
    destination="北京",
    days=2,
    travelers=2,
    daily_itinerary=None,
    total_budget=3000,
    constraints=None,
):
    if daily_itinerary is None:
        daily_itinerary = [
            {
                "day": 1,
                "activities": [
                    {
                        "time": "09:00",
                        "place": "故宫",
                        "description": "参观景点",
                    }
                ],
            }
        ]

    if constraints is None:
        constraints = []

    return {
        "destination": destination,
        "days": days,
        "travelers": travelers,
        "daily_itinerary": daily_itinerary,
        "total_budget": total_budget,
        "constraints": constraints,
    }


def make_review_result():
    return {
        "overall_status": "warning",
        "score": 85,
        "issues": [
            {
                "category": "time_arrangement",
                "level": "medium",
                "description": "第二天行程信息不完整",
                "suggestion": "补充第二天的活动安排",
            }
        ],
        "pending_checks": [
            "确认景点营业时间"
        ],
        "summary": "整体行程基本合理，建议补充第二天安排。",
    }


def test_parse_markdown_json():
    response = """
```json
{
    "overall_status": "pass",
    "score": 90,
    "issues": [],
    "pending_checks": [],
    "summary": "行程基本合理。"
}
```
"""

    result = ItineraryReviewAgent._parse_json(response)

    assert result["overall_status"] == "pass"
    assert result["score"] == 90


def test_validate_itinerary_params():
    result = ItineraryReviewAgent._validate_params(
        make_params()
    )

    assert result["destination"] == "北京"
    assert result["days"] == 2
    assert result["travelers"] == 2
    assert len(result["daily_itinerary"]) == 1


def test_reject_invalid_days():
    with pytest.raises(ValueError, match="旅行天数"):
        ItineraryReviewAgent._validate_params(
            make_params(days=0)
        )


def test_reject_invalid_travelers():
    with pytest.raises(ValueError, match="出行人数"):
        ItineraryReviewAgent._validate_params(
            make_params(travelers=0)
        )


def test_reject_invalid_itinerary():
    with pytest.raises(ValueError, match="每日行程"):
        ItineraryReviewAgent._validate_params(
            make_params(daily_itinerary="错误数据")
        )


def test_reject_invalid_budget():
    with pytest.raises(ValueError, match="总预算"):
        ItineraryReviewAgent._validate_params(
            make_params(total_budget=-100)
        )


def test_validate_review_result():
    result = ItineraryReviewAgent._validate_review_result(
        make_review_result()
    )

    assert result["overall_status"] == "warning"
    assert result["score"] == 85
    assert len(result["issues"]) == 1


def test_reject_invalid_review_status():
    result = make_review_result()
    result["overall_status"] = "unknown"

    with pytest.raises(ValueError, match="审核状态"):
        ItineraryReviewAgent._validate_review_result(result)


def test_reject_invalid_review_score():
    result = make_review_result()
    result["score"] = 101

    with pytest.raises(ValueError, match="审核评分"):
        ItineraryReviewAgent._validate_review_result(result)


@pytest.mark.asyncio
async def test_extract_itinerary():
    llm = FakeLLM([
        """
{
    "destination": "北京",
    "days": 2,
    "travelers": 2,
    "daily_itinerary": [
        {
            "day": 1,
            "activities": [
                {
                    "time": "09:00",
                    "place": "故宫",
                    "description": "参观景点"
                }
            ]
        }
    ],
    "total_budget": 3000,
    "constraints": []
}
"""
    ])

    agent = ItineraryReviewAgent(llm_client=llm)

    result = await agent.extract_itinerary(
        "两个人去北京玩两天，第一天上午九点参观故宫，总预算3000元"
    )

    assert result["destination"] == "北京"
    assert result["days"] == 2
    assert result["travelers"] == 2
    assert result["total_budget"] == 3000
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_review_itinerary():
    params_response = {
        "destination": "北京",
        "days": 2,
        "travelers": 2,
        "daily_itinerary": [
            {
                "day": 1,
                "activities": [
                    {
                        "time": "09:00",
                        "place": "故宫",
                        "description": "参观景点",
                    }
                ],
            }
        ],
        "total_budget": 3000,
        "constraints": [],
    }

    llm = FakeLLM([
        __import__("json").dumps(
            params_response,
            ensure_ascii=False,
        ),
        __import__("json").dumps(
            make_review_result(),
            ensure_ascii=False,
        ),
    ])

    agent = ItineraryReviewAgent(llm_client=llm)

    result = await agent.review_itinerary(
        "两个人去北京玩两天，第一天上午九点参观故宫"
    )

    assert result["success"] is True
    assert result["task"] == "itinerary_review"
    assert result["review_result"]["overall_status"] == "warning"
    assert result["review_result"]["score"] == 85
    assert result["answer"] == "整体行程基本合理，建议补充第二天安排。"
    assert llm.call_count == 2


@pytest.mark.asyncio
async def test_empty_input():
    llm = FakeLLM([])
    agent = ItineraryReviewAgent(llm_client=llm)

    with pytest.raises(ValueError, match="用户输入不能为空"):
        await agent.extract_itinerary(" ")
