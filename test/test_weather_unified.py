
import pytest

from tools import weather_tools


@pytest.mark.asyncio
async def test_get_weather_empty_city():
    result = await weather_tools.get_weather("")

    assert result["success"] is False
    assert result["tool"] == "get_weather"
    assert result["data"] is None
    assert result["error"]["type"] == "ValueError"


@pytest.mark.asyncio
async def test_get_weather_invalid_city_type():
    result = await weather_tools.get_weather(None)

    assert result["success"] is False
    assert result["tool"] == "get_weather"
    assert result["error"]["type"] == "TypeError"


@pytest.mark.asyncio
async def test_get_weather_success(monkeypatch):
    async def fake_call_tool(tool_name, arguments):
        assert tool_name == "maps_weather"
        assert arguments["city"] == "北京"

        return {
            "structuredContent": {
                "city": "北京",
                "forecasts": [
                    {
                        "date": "2026-10-30",
                        "week": "5",
                        "dayweather": "晴",
                        "nightweather": "多云",
                        "daytemp": "20",
                        "nighttemp": "10",
                        "daywind": "北风",
                        "nightwind": "北风",
                        "daypower": "3",
                        "nightpower": "2"
                    }
                ]
            }
        }

    monkeypatch.setattr(
        weather_tools,
        "call_tool",
        fake_call_tool
    )

    result = await weather_tools.get_weather(" 北京 ")

    assert result["success"] is True
    assert result["tool"] == "get_weather"
    assert result["error"] is None

    data = result["data"]

    assert data["city"] == "北京"
    assert data["forecast_days"] == 1

    forecast = data["forecasts"][0]

    assert forecast["weekday"] == "星期五"
    assert forecast["day_weather"] == "晴"
    assert forecast["day_temp"] == 20.0
    assert forecast["night_temp"] == 10.0


@pytest.mark.asyncio
async def test_get_weather_mcp_failure(monkeypatch):
    async def fake_call_tool(tool_name, arguments):
        raise RuntimeError("模拟天气 MCP 调用失败")

    monkeypatch.setattr(
        weather_tools,
        "call_tool",
        fake_call_tool
    )

    result = await weather_tools.get_weather("北京")

    assert result["success"] is False
    assert result["tool"] == "get_weather"
    assert result["error"]["type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_get_weather_invalid_forecasts(monkeypatch):
    async def fake_call_tool(tool_name, arguments):
        return {
            "structuredContent": {
                "city": "北京",
                "forecasts": "无效数据"
            }
        }

    monkeypatch.setattr(
        weather_tools,
        "call_tool",
        fake_call_tool
    )

    result = await weather_tools.get_weather("北京")

    assert result["success"] is False
    assert result["error"]["type"] == "ValueError"
