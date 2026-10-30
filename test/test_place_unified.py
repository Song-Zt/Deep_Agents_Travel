
import pytest

from tools.place_tools import (
    search_places,
    get_place_detail,
    geocode,
)


@pytest.mark.asyncio
async def test_search_places_empty_keyword():
    result = await search_places("")

    assert result["success"] is False
    assert result["tool"] == "search_places"
    assert result["data"] is None
    assert result["error"]["type"] == "ValueError"


@pytest.mark.asyncio
async def test_get_place_detail_empty_id():
    result = await get_place_detail("")

    assert result["success"] is False
    assert result["tool"] == "get_place_detail"
    assert result["error"]["type"] == "ValueError"


@pytest.mark.asyncio
async def test_geocode_empty_address():
    result = await geocode("")

    assert result["success"] is False
    assert result["tool"] == "geocode"
    assert result["error"]["type"] == "ValueError"


@pytest.mark.asyncio
async def test_search_places_success(monkeypatch):

    async def fake_call_tool(tool_name, arguments):
        class FakeItem:
            structuredContent = {
                "pois": [
                    {
                        "name": "故宫博物院",
                        "id": "test123",
                        "address": "北京市东城区",
                        "location": "116.397029,39.917839"
                    }
                ]
            }
            content = []

        return FakeItem()

    monkeypatch.setattr(
        "tools.place_tools.call_tool",
        fake_call_tool
    )

    result = await search_places("故宫", city="北京")

    assert result["success"] is True
    assert result["tool"] == "search_places"
    assert result["data"][0]["name"] == "故宫博物院"
    assert result["error"] is None
