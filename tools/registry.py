
"""
旅行助手工具注册中心。

统一管理地点、路线和天气工具，
为后续 Agent 提供按名称调用工具的入口。
"""

import inspect
import time
import types
from typing import (
    Any,
    Callable,
    Union,
    get_args,
    get_origin,
)

from tools.base import error_result
from tools.events import (
    emit_tool_event,
    format_arguments,
    summarize_result,
)
from tools.place_tools import (
    search_places,
    get_place_detail,
    geocode,
)
from tools.route_tools import (
    plan_walking_route,
    plan_driving_route,
    plan_transit_route,
    plan_bicycling_route,
    calculate_distance,
)
from tools.weather_tools import get_weather


# 工具注册表
# key：工具名称
# value：对应的 Python 函数
TOOL_REGISTRY: dict[str, Callable] = {
    # 地点工具
    "search_places": search_places,
    "get_place_detail": get_place_detail,
    "geocode": geocode,

    # 路线工具
    "plan_walking_route": plan_walking_route,
    "plan_driving_route": plan_driving_route,
    "plan_transit_route": plan_transit_route,
    "plan_bicycling_route": plan_bicycling_route,
    "calculate_distance": calculate_distance,

    # 天气工具
    "get_weather": get_weather,
}
# 工具描述
TOOL_DESCRIPTIONS = {
    "search_places": "根据关键词和城市搜索地点，例如景点、餐厅、酒店和商场。",
    "get_place_detail": "根据高德地图 POI ID 查询地点详细信息。",
    "geocode": "将地址或地点名称转换为经纬度坐标。",
    "plan_walking_route": "规划两个坐标之间的步行路线。",
    "plan_driving_route": "规划两个坐标之间的驾车路线。",
    "plan_transit_route": "规划两个地点之间的公共交通路线。",
    "plan_bicycling_route": "规划两个坐标之间的骑行路线。",
    "calculate_distance": "计算两个或多个地点之间的距离。",
    "get_weather": "查询指定城市的天气预报。",
}


# 参数描述
PARAMETER_DESCRIPTIONS = {
    "keywords": "搜索关键词，例如故宫、咖啡馆。",
    "city": "城市名称，例如北京、上海。",
    "citylimit": "是否限制在指定城市范围内搜索。",
    "poi_id": "高德地图 POI ID。",
    "address": "需要进行地理编码的地址或地点名称。",
    "location": "地点经纬度，格式为经度,纬度。",
    "origin": "起点经纬度，格式为经度,纬度。",
    "destination": "终点经纬度，格式为经度,纬度。",
    "cityd": "目的地所在城市名称。",
    "type": "距离计算类型，具体可选值由工具函数定义。",
}


def get_registered_tools() -> list[str]:
    """获取所有已注册的工具名称。"""
    return list(TOOL_REGISTRY.keys())


def get_tool(tool_name: str) -> Callable | None:
    """根据名称获取工具函数。"""
    return TOOL_REGISTRY.get(tool_name)


def python_type_to_json_schema(annotation: Any) -> dict:
    """将 Python 类型注解转换为 JSON Schema。"""

    if annotation is inspect.Parameter.empty:
        return {}

    if annotation is Any:
        return {}

    origin = get_origin(annotation)
    args = get_args(annotation)

    # 处理 Optional 和 Union
    if origin in (Union, types.UnionType):
        non_none_types = [
            item for item in args
            if item is not type(None)
        ]

        if len(non_none_types) == 1:
            return python_type_to_json_schema(
                non_none_types[0]
            )

        return {
            "anyOf": [
                python_type_to_json_schema(item)
                for item in non_none_types
            ]
        }

    # 处理列表
    if origin is list:
        item_type = args[0] if args else Any

        return {
            "type": "array",
            "items": python_type_to_json_schema(item_type),
        }

    # 处理字典
    if origin is dict:
        return {"type": "object"}

    type_mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    json_type = type_mapping.get(annotation)

    if json_type:
        return {"type": json_type}

    return {}


def get_tool_parameters_schema(tool: Callable) -> dict:
    """根据工具函数签名自动生成参数 Schema。"""

    signature = inspect.signature(tool)

    properties = {}
    required = []

    for name, parameter in signature.parameters.items():

        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        property_schema = python_type_to_json_schema(
            parameter.annotation
        )

        property_schema["description"] = (
            PARAMETER_DESCRIPTIONS.get(
                name,
                f"参数 {name}",
            )
        )

        if parameter.default is inspect.Parameter.empty:
            required.append(name)

        elif parameter.default is None or isinstance(
            parameter.default,
            (str, int, float, bool),
        ):
            property_schema["default"] = parameter.default

        properties[name] = property_schema

    schema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }

    if required:
        schema["required"] = required

    return schema


def get_tool_schemas() -> list[dict]:
    """获取所有工具的 Function Calling 定义。"""

    schemas = []

    for tool_name, tool in TOOL_REGISTRY.items():

        schemas.append({
            "type": "function",
            "function": {
                "name": tool_name,
                "description": TOOL_DESCRIPTIONS.get(
                    tool_name,
                    f"执行工具：{tool_name}",
                ),
                "parameters": get_tool_parameters_schema(tool),
            },
        })

    return schemas


async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict:
    """
    根据工具名称执行对应函数。

    参数：
        tool_name: 工具名称
        arguments: 工具参数字典

    返回：
        统一格式的工具执行结果
    """

    if not isinstance(tool_name, str) or not tool_name.strip():
        return error_result(
            "unknown",
            ValueError("工具名称不能为空"),
        )

    tool = get_tool(tool_name)

    if tool is None:
        return error_result(
            tool_name,
            ValueError(f"未注册的工具：{tool_name}"),
        )

    if arguments is None:
        arguments = {}

    if not isinstance(arguments, dict):
        return error_result(
            tool_name,
            TypeError("工具参数必须是字典类型"),
        )

    emit_tool_event({
        "event": "tool",
        "data": {
            "tool": tool_name,
            "status": "start",
            "arguments": format_arguments(arguments),
        },
    })

    started = time.perf_counter()

    try:
        result = tool(**arguments)

        # 兼容同步函数和异步函数
        if inspect.isawaitable(result):
            result = await result

        emit_tool_event({
            "event": "tool",
            "data": {
                "tool": tool_name,
                "status": "end",
                "success": (
                    result.get("success")
                    if isinstance(result, dict)
                    else True
                ),
                "duration_ms": int(
                    (time.perf_counter() - started) * 1000
                ),
                "summary": summarize_result(result),
            },
        })

        return result

    except Exception as exc:
        emit_tool_event({
            "event": "tool",
            "data": {
                "tool": tool_name,
                "status": "end",
                "success": False,
                "duration_ms": int(
                    (time.perf_counter() - started) * 1000
                ),
                "summary": f"失败：{exc}"[:200],
            },
        })

        return error_result(tool_name, exc)
