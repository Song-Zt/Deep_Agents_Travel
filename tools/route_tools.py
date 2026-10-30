
from typing import Any

from tools.amap_client import call_tool
from tools.place_tools import parse_mcp_result, parse_location
from tools.base import success_result, error_result


def _validate_coordinate(value: str, name: str) -> str:
    """
    校验经纬度字符串，格式为：经度,纬度
    例如：116.397029,39.917839
    """
    if not isinstance(value, str):
        raise TypeError(f"{name} 必须是字符串")

    if not value.strip():
        raise ValueError(f"{name} 不能为空")

    # parse_location 会校验经纬度格式及范围
    parse_location(value)

    return value


async def _execute_route(
    result_tool: str,
    amap_tool: str,
    arguments: dict
) -> dict:
    """
    统一执行高德路线 MCP 调用，并封装返回结果。
    """
    try:
        result = await call_tool(amap_tool, arguments)
        data = parse_mcp_result(result)

        return success_result(result_tool, data)

    except Exception as e:
        return error_result(result_tool, e)


async def plan_walking_route(
    origin: str,
    destination: str
) -> dict:
    """查询两地之间的步行路线。"""
    try:
        origin = _validate_coordinate(origin, "origin")
        destination = _validate_coordinate(destination, "destination")

        return await _execute_route(
            "plan_walking_route",
            "maps_direction_walking",
            {
                "origin": origin,
                "destination": destination
            }
        )

    except Exception as e:
        return error_result("plan_walking_route", e)


async def plan_driving_route(
    origin: str,
    destination: str
) -> dict:
    """查询两地之间的驾车路线。"""
    try:
        origin = _validate_coordinate(origin, "origin")
        destination = _validate_coordinate(destination, "destination")

        return await _execute_route(
            "plan_driving_route",
            "maps_direction_driving",
            {
                "origin": origin,
                "destination": destination
            }
        )

    except Exception as e:
        return error_result("plan_driving_route", e)


async def plan_transit_route(
    origin: str,
    destination: str,
    city: str,
    cityd: str
) -> dict:
    """
    查询两地之间的公共交通路线。

    city：起点所在城市，例如北京
    cityd：终点所在城市，例如北京
    """
    try:
        origin = _validate_coordinate(origin, "origin")
        destination = _validate_coordinate(destination, "destination")

        if not isinstance(city, str) or not city.strip():
            raise ValueError("必须提供有效的起点城市 city")

        if not isinstance(cityd, str) or not cityd.strip():
            raise ValueError("必须提供有效的终点城市 cityd")

        return await _execute_route(
            "plan_transit_route",
            "maps_direction_transit_integrated",
            {
                "origin": origin,
                "destination": destination,
                "city": city,
                "cityd": cityd
            }
        )

    except Exception as e:
        return error_result("plan_transit_route", e)


async def plan_bicycling_route(
    origin: str,
    destination: str
) -> dict:
    """查询两地之间的骑行路线。"""
    try:
        origin = _validate_coordinate(origin, "origin")
        destination = _validate_coordinate(destination, "destination")

        return await _execute_route(
            "plan_bicycling_route",
            "maps_direction_bicycling",
            {
                "origin": origin,
                "destination": destination
            }
        )

    except Exception as e:
        return error_result("plan_bicycling_route", e)


async def calculate_distance(
    origins: str,
    destination: str,
    distance_type: int = 1
) -> dict:
    """
    计算起点到终点的距离。

    distance_type:
        1：驾车距离
        0：直线距离
        3：步行距离

    origins 支持高德要求的坐标字符串格式。
    单个起点示例：116.397029,39.917839
    """
    try:
        if isinstance(distance_type, bool) or distance_type not in (0, 1, 3):
            raise ValueError("distance_type 只能是 0、1 或 3")

        origins = _validate_coordinate(origins, "origins")
        destination = _validate_coordinate(destination, "destination")

        return await _execute_route(
            "calculate_distance",
            "maps_distance",
            {
                "origins": origins,
                "destination": destination,
                "type": distance_type
            }
        )

    except Exception as e:
        return error_result("calculate_distance", e)
