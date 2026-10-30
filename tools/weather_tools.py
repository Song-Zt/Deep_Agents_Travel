
from typing import Any

from tools.amap_client import call_tool
from tools.place_tools import parse_mcp_result
from tools.base import success_result, error_result


WEEKDAY_MAP = {
    "1": "星期一",
    "2": "星期二",
    "3": "星期三",
    "4": "星期四",
    "5": "星期五",
    "6": "星期六",
    "7": "星期日",
}


def _to_float(value: Any) -> float | None:
    """安全地将温度转换为浮点数。"""
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_forecast(item: dict[str, Any]) -> dict[str, Any]:
    """
    将高德天气预报中的单日数据转换为统一格式。
    """
    return {
        "date": item.get("date"),
        "weekday": WEEKDAY_MAP.get(
            str(item.get("week", "")),
            item.get("week")
        ),
        "day_weather": item.get("dayweather"),
        "night_weather": item.get("nightweather"),
        "day_temp": _to_float(
            item.get("daytemp_float", item.get("daytemp"))
        ),
        "night_temp": _to_float(
            item.get("nighttemp_float", item.get("nighttemp"))
        ),
        "day_wind": item.get("daywind"),
        "night_wind": item.get("nightwind"),
        "day_wind_power": item.get("daypower"),
        "night_wind_power": item.get("nightpower"),
    }


async def get_weather(city: str) -> dict[str, Any]:
    """
    查询指定城市天气，返回统一格式的天气预报。

    Args:
        city: 城市名称，例如北京、上海、深圳。

    Returns:
        统一格式的结果：
        {
            "success": True,
            "tool": "get_weather",
            "data": {...},
            "error": None
        }
    """

    try:
        # 1. 参数校验
        if not isinstance(city, str):
            raise TypeError("城市名称必须是字符串")

        city = city.strip()

        if not city:
            raise ValueError("城市名称不能为空")

        # 2. 调用高德天气 MCP
        result = await call_tool(
            "maps_weather",
            {"city": city}
        )

        # 3. 解析 MCP 返回结果
        weather_data = parse_mcp_result(result)

        if not isinstance(weather_data, dict):
            raise ValueError("天气接口返回的数据格式不正确")

        forecasts = weather_data.get("forecasts")

        if not isinstance(forecasts, list):
            raise ValueError("天气接口没有返回有效的 forecasts 列表")

        # 4. 标准化天气预报数据
        normalized_forecasts = [
            normalize_forecast(item)
            for item in forecasts
            if isinstance(item, dict)
        ]

        if not normalized_forecasts:
            raise ValueError("天气接口没有返回有效的天气预报数据")

        # 5. 统一成功结果
        data = {
            "city": weather_data.get("city") or city,
            "forecast_days": len(normalized_forecasts),
            "forecasts": normalized_forecasts,
        }

        return success_result("get_weather", data)

    except Exception as e:
        # 6. 统一失败结果
        return error_result("get_weather", e)
