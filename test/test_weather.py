
import pytest

from tools.weather_tools import get_weather


@pytest.mark.asyncio
async def test_real_weather():
    """真实调用高德 MCP，测试天气查询。"""

    result = await get_weather("北京")

    assert result["success"] is True
    assert result["tool"] == "get_weather"
    assert result["error"] is None

    data = result["data"]

    assert data["city"] in ("北京", "北京市")
    assert data["forecast_days"] > 0
    assert isinstance(data["forecasts"], list)

    # 检查单日天气数据结构
    forecast = data["forecasts"][0]

    assert "date" in forecast
    assert "weekday" in forecast
    assert "day_weather" in forecast
    assert "night_weather" in forecast
    assert "day_temp" in forecast
    assert "night_temp" in forecast


@pytest.mark.asyncio
async def test_empty_city():
    """测试城市名称为空时的错误处理。"""

    result = await get_weather("")

    assert result["success"] is False
    assert result["tool"] == "get_weather"
    assert result["data"] is None

    assert result["error"]["type"] == "ValueError"
    assert result["error"]["message"] == "城市名称不能为空"
