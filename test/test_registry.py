
import pytest

from tools.registry import (
    TOOL_REGISTRY,
    get_registered_tools,
    get_tool,
    execute_tool,
)


def test_registry_contains_all_tools():
    expected_tools = {
        "search_places",
        "get_place_detail",
        "geocode",
        "plan_walking_route",
        "plan_driving_route",
        "plan_transit_route",
        "plan_bicycling_route",
        "calculate_distance",
        "get_weather",
    }

    assert set(get_registered_tools()) == expected_tools


def test_get_tool_success():
    tool = get_tool("get_weather")

    assert tool is not None
    assert callable(tool)


def test_get_tool_not_found():
    assert get_tool("not_exists") is None


@pytest.mark.asyncio
async def test_execute_tool_not_found():
    result = await execute_tool("not_exists")

    assert result["success"] is False
    assert "未注册的工具" in result["error"]["message"]


@pytest.mark.asyncio
async def test_execute_tool_invalid_arguments():
    result = await execute_tool(
        "get_weather",
        arguments="北京",
    )

    assert result["success"] is False
    assert result["error"]["type"] == "TypeError"


@pytest.mark.asyncio
async def test_execute_tool_success(monkeypatch):

    async def fake_get_weather(city):
        return {
            "success": True,
            "tool": "get_weather",
            "data": {"city": city},
            "error": None,
        }

    monkeypatch.setitem(
        TOOL_REGISTRY,
        "get_weather",
        fake_get_weather,
    )

    result = await execute_tool(
        "get_weather",
        {"city": "北京"},
    )

    assert result["success"] is True
    assert result["data"]["city"] == "北京"
