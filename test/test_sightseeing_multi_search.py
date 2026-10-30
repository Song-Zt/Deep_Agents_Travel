
import sys
from pathlib import Path

from unittest.mock import AsyncMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.sub_agents.sightseeing_agent import SightseeingAgent


def test_normalize_keywords():
    result = SightseeingAgent._normalize_keywords(
        ["故宫", "天坛", "故宫", "颐和园"]
    )

    assert result == ["故宫", "天坛", "颐和园"]


def test_normalize_string_keywords():
    result = SightseeingAgent._normalize_keywords(
        "故宫，天坛、颐和园"
    )

    assert result == ["故宫", "天坛", "颐和园"]


def test_deduplicate_places():
    places = [
        {"poi_id": "001", "name": "故宫", "address": "北京"},
        {"poi_id": "001", "name": "故宫", "address": "北京"},
        {"poi_id": "002", "name": "天坛", "address": "北京"},
        {"name": "颐和园", "address": "北京"},
        {"name": "颐和园", "address": "北京"},
    ]

    result = SightseeingAgent._deduplicate_places(places)

    assert len(result) == 3


def test_empty_keyword_rejected():
    try:
        SightseeingAgent._normalize_keywords([])
    except ValueError as exc:
        assert "关键词" in str(exc)
    else:
        raise AssertionError("空关键词应该报错")


def test_max_keywords_limit():
    keywords = [f"景点{i}" for i in range(10)]

    result = SightseeingAgent._normalize_keywords(keywords)

    assert len(result) == 6


async def test_multiple_search_merge():
    """验证多关键词搜索可以合并结果并去重。"""
    agent = SightseeingAgent.__new__(SightseeingAgent)

    mock_results = {
        "故宫": {
            "success": True,
            "data": [
                {"poi_id": "001", "name": "故宫"},
                {"poi_id": "002", "name": "天坛"},
            ],
            "error": None,
        },
        "天坛": {
            "success": True,
            "data": [
                {"poi_id": "002", "name": "天坛"},
                {"poi_id": "003", "name": "颐和园"},
            ],
            "error": None,
        },
    }

    async def fake_execute_tool(name, arguments):
        return mock_results[arguments["keywords"]]

    with patch(
        "agents.sub_agents.sightseeing_agent.execute_tool",
        new=AsyncMock(side_effect=fake_execute_tool),
    ):
        result = await agent.search_multiple_keywords(
            ["故宫", "天坛"],
            "北京",
        )

    assert len(result["places"]) == 3
    assert len(result["successful_keywords"]) == 2
    assert len(result["failed_searches"]) == 0


async def test_partial_search_failure():
    """验证部分关键词搜索失败时，其他搜索结果仍然保留。"""
    agent = SightseeingAgent.__new__(SightseeingAgent)

    async def fake_execute_tool(name, arguments):
        if arguments["keywords"] == "故宫":
            return {
                "success": True,
                "data": [{"poi_id": "001", "name": "故宫"}],
                "error": None,
            }

        return {
            "success": False,
            "data": None,
            "error": {"message": "搜索失败"},
        }

    with patch(
        "agents.sub_agents.sightseeing_agent.execute_tool",
        new=AsyncMock(side_effect=fake_execute_tool),
    ):
        result = await agent.search_multiple_keywords(
            ["故宫", "天坛"],
            "北京",
        )

    assert len(result["places"]) == 1
    assert len(result["successful_keywords"]) == 1
    assert len(result["failed_searches"]) == 1

def test_filter_irrelevant_places():
    from agents.sub_agents.sightseeing_agent import SightseeingAgent

    agent = SightseeingAgent()

    places = [
        {
            "name": "故宫博物院",
            "poi_id": "1",
            "address": "景山前街4号"
        },
        {
            "name": "故宫博物院售票处",
            "poi_id": "2",
            "address": "故宫内"
        },
        {
            "name": "天坛公园",
            "poi_id": "3",
            "address": "天坛东里甲1号"
        },
        {
            "name": "颐和园公交站",
            "poi_id": "4",
            "address": "颐和园附近"
        },
        {
            "name": "德和园",
            "poi_id": "5",
            "address": "颐和园内"
        }
    ]

    result = agent._filter_irrelevant_places(places)

    names = [place["name"] for place in result]

    assert "故宫博物院" in names
    assert "天坛公园" in names
    assert "德和园" in names

    assert "故宫博物院售票处" not in names
    assert "颐和园公交站" not in names

if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))

