
import json
from typing import Any, Optional

from tools.amap_client import call_tool
from tools.base import success_result, error_result


def parse_mcp_result(result):
    """
    解析 MCP 返回结果。

    兼容：
    1. MCP SDK 返回对象
    2. 普通 Python 字典
    3. structuredContent
    4. content 中的 JSON 文本
    """

    # 兼容字典和 MCP SDK 对象
    if isinstance(result, dict):
        structured_content = result.get("structuredContent")
        content = result.get("content")
    else:
        structured_content = getattr(result, "structuredContent", None)
        content = getattr(result, "content", None)

    # 优先使用结构化结果
    if structured_content is not None:
        return structured_content

    # 尝试解析 content 中的文本
    if content:
        for item in content:
            if isinstance(item, dict):
                text_content = item.get("text")
            else:
                text_content = getattr(item, "text", None)

            if not text_content:
                continue

            try:
                return json.loads(text_content)
            except (json.JSONDecodeError, TypeError):
                continue

    raise ValueError("无法从 MCP 返回结果中解析 JSON 数据")


def normalize_poi(poi: dict) -> dict:
    """统一 POI 数据格式。"""

    return {
        "name": poi.get("name"),
        "poi_id": poi.get("id"),
        "address": poi.get("address"),
        "location": poi.get("location"),
        "city": poi.get("city"),
        "type": poi.get("type"),
        "typecode": poi.get("typecode"),
        "alias": poi.get("alias"),
        "photo": poi.get("photo"),
        "rating": poi.get("rating"),
        "level": poi.get("level"),
        "opening_hours": (
            poi.get("opentime2") or poi.get("open_time")
        ),
        "cost": poi.get("cost"),
    }


async def search_places(
    keywords: str,
    city: Optional[str] = None,
    citylimit: bool = True,
) -> dict:
    """
    搜索景点、酒店、餐厅等 POI。
    """

    tool_name = "search_places"

    try:
        if not isinstance(keywords, str) or not keywords.strip():
            raise ValueError("搜索关键词不能为空")

        if city is not None and not isinstance(city, str):
            raise TypeError("city 必须是字符串")

        arguments = {
            "keywords": keywords.strip(),
            "citylimit": citylimit,
        }

        if city and city.strip():
            arguments["city"] = city.strip()

        result = await call_tool(
            "maps_text_search",
            arguments,
        )

        data = parse_mcp_result(result)

        if not isinstance(data, dict):
            raise ValueError("地点搜索接口返回的数据格式不正确")

        pois = data.get("pois", [])

        if not isinstance(pois, list):
            raise ValueError("地点搜索结果中的 pois 格式不正确")

        normalized_pois = [
            normalize_poi(poi)
            for poi in pois
            if isinstance(poi, dict)
        ]

        return success_result(tool_name, normalized_pois)

    except Exception as e:
        return error_result(tool_name, e)


async def get_place_detail(poi_id: str) -> dict:
    """
    根据 POI ID 获取地点详情。
    """

    tool_name = "get_place_detail"

    try:
        if not isinstance(poi_id, str) or not poi_id.strip():
            raise ValueError("POI ID 不能为空")

        result = await call_tool(
            "maps_search_detail",
            {"id": poi_id.strip()},
        )

        data = parse_mcp_result(result)

        # 兼容返回单个对象或 pois 数组的情况
        if isinstance(data, list):
            if not data:
                raise ValueError(f"没有找到 POI：{poi_id}")
            data = data[0]

        if not isinstance(data, dict):
            raise ValueError("地点详情接口返回的数据格式不正确")

        if "pois" in data:
            pois = data["pois"]

            if not pois:
                raise ValueError(f"没有找到 POI：{poi_id}")

            data = pois[0]

        if not isinstance(data, dict):
            raise ValueError("地点详情数据格式不正确")

        normalized_poi = normalize_poi(data)

        return success_result(tool_name, normalized_poi)

    except Exception as e:
        return error_result(tool_name, e)


async def geocode(
    address: str,
    city: Optional[str] = None
) -> dict:
    """
    地理编码：将地址转换为经纬度。
    """

    tool_name = "geocode"

    try:
        if not isinstance(address, str) or not address.strip():
            raise ValueError("地址不能为空")

        if city is not None and not isinstance(city, str):
            raise TypeError("city 必须是字符串")

        address = address.strip()

        arguments = {
            "address": address
        }

        if city and city.strip():
            arguments["city"] = city.strip()

        result = await call_tool(
            "maps_geo",
            arguments
        )

        data = parse_mcp_result(result)

        if not isinstance(data, dict):
            raise ValueError("地理编码接口返回的数据格式不正确")

        # 兼容不同 MCP 返回字段
        results = (
            data.get("results")
            or data.get("geocodes")
            or []
        )

        if not results:
            raise ValueError(f"地址解析失败：{address}")

        item = results[0]

        if not isinstance(item, dict):
            raise ValueError("地理编码结果格式不正确")

        location = item.get("location")

        if not location:
            raise ValueError("地址解析结果中没有经纬度")

        # 验证经纬度格式
        parse_location(location)

        normalized_data = {
            "address": address,
            "location": location,
            "city": item.get("city"),
            "province": item.get("province"),
            "district": item.get("district"),
            "level": item.get("level")
        }

        return success_result(tool_name, normalized_data)

    except Exception as e:
        return error_result(tool_name, e)


def parse_location(location: str) -> tuple[float, float]:
    """
    解析高德经纬度字符串。

    返回：
        (longitude, latitude)
    """

    if not isinstance(location, str) or "," not in location:
        raise ValueError(f"无效的经纬度：{location}")

    lon, lat = location.split(",", 1)

    try:
        longitude = float(lon.strip())
        latitude = float(lat.strip())
    except ValueError:
        raise ValueError(f"经纬度必须是有效数字：{location}")

    if not -180 <= longitude <= 180:
        raise ValueError("经度超出有效范围")

    if not -90 <= latitude <= 90:
        raise ValueError("纬度超出有效范围")

    return longitude, latitude
