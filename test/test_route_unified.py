
import pytest

from tools import route_tools


@pytest.mark.asyncio
async def test_walking_route_invalid_coordinate():
    result = await route_tools.plan_walking_route(
        "",
        "116.410829,39.881913"
    )

    assert result["success"] is False
    assert result["tool"] == "plan_walking_route"
    assert result["data"] is None
    assert result["error"]["type"] == "ValueError"


@pytest.mark.asyncio
async def test_transit_route_empty_city():
    result = await route_tools.plan_transit_route(
        "116.397029,39.917839",
        "116.410829,39.881913",
        "",
        "北京"
    )

    assert result["success"] is False
    assert result["tool"] == "plan_transit_route"
    assert result["error"]["type"] == "ValueError"


@pytest.mark.asyncio
async def test_distance_invalid_type():
    result = await route_tools.calculate_distance(
        "116.397029,39.917839",
        "116.410829,39.881913",
        2
    )

    assert result["success"] is False
    assert result["tool"] == "calculate_distance"
    assert result["error"]["type"] == "ValueError"


@pytest.mark.asyncio
async def test_walking_route_success(monkeypatch):
    async def fake_call_tool(tool_name, arguments):
        assert tool_name == "maps_direction_walking"
        assert arguments["origin"] == "116.397029,39.917839"

        return {
            "structuredContent": {
                "route": {
                    "paths": [
                        {
                            "distance": "5514",
                            "duration": "4411"
                        }
                    ]
                }
            }
        }

    monkeypatch.setattr(
        route_tools,
        "call_tool",
        fake_call_tool
    )

    result = await route_tools.plan_walking_route(
        "116.397029,39.917839",
        "116.410829,39.881913"
    )

    assert result["success"] is True, result
    assert result["tool"] == "plan_walking_route"
    assert result["error"] is None
    assert result["data"]["route"]["paths"][0]["distance"] == "5514"


@pytest.mark.asyncio
async def test_mcp_call_failure(monkeypatch):
    async def fake_call_tool(tool_name, arguments):
        raise RuntimeError("模拟 MCP 调用失败")

    monkeypatch.setattr(
        route_tools,
        "call_tool",
        fake_call_tool
    )

    result = await route_tools.plan_driving_route(
        "116.397029,39.917839",
        "116.410829,39.881913"
    )

    assert result["success"] is False
    assert result["tool"] == "plan_driving_route"
    assert result["error"]["type"] == "RuntimeError"
