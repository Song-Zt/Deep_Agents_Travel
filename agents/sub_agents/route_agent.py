
import json
from typing import Any

from agents.base_agent import BaseAgent
from tools.registry import execute_tool


ROUTE_PROMPT = """
你是一名专业的旅行路线规划助手。

你的任务是根据用户需求，结合高德地图返回的真实路线数据，
向用户解释路线规划结果。

要求：
1. 只能根据提供的路线数据回答。
2. 不得编造距离、耗时、道路名称、换乘方案或费用。
3. 如果数据中没有某项信息，应说明暂无相关数据。
4. 使用清晰、自然的中文回答。
5. 优先突出路线距离、预计耗时、交通方式和关键换乘信息。
"""


ROUTE_TASK_TYPES = {
    "walking",
    "driving",
    "transit",
    "bicycling",
    "distance",
}


class RouteAgent(BaseAgent):
    """
    路线规划 Agent。

    支持：
    1. 步行路线
    2. 驾车路线
    3. 公交路线
    4. 骑行路线
    5. 两地距离计算
    """

    def __init__(self, llm_client=None):
        super().__init__(
            name="RouteAgent",
            system_prompt=ROUTE_PROMPT,
            llm_client=llm_client,
        )

    @staticmethod
    def _parse_json(response: str) -> dict[str, Any]:
        """解析 LLM 返回的 JSON，兼容 Markdown 代码块。"""
        if not isinstance(response, str) or not response.strip():
            raise ValueError("模型返回内容不能为空")

        content = response.strip()

        if content.startswith("```"):
            lines = content.splitlines()

            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]

            content = "\n".join(lines).strip()

        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"模型返回的内容不是有效 JSON：{exc}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError("模型返回结果必须是 JSON 对象")

        return result

    async def extract_route_params(
        self,
        user_input: str,
    ) -> dict[str, Any]:
        """提取路线类型、起点、终点及其他参数。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        prompt = """
你是路线规划参数提取器。

请分析用户需求，只返回 JSON，不要输出 Markdown 或其他解释。

JSON 格式：
{
    "task_type": "walking",
    "origin": "出发地",
    "destination": "目的地",
    "city": "出发城市",
    "cityd": "目的地城市",
    "distance_type": 1
}

task_type 只能选择：
- walking：步行路线
- driving：驾车路线
- transit：公交路线
- bicycling：骑行路线
- distance：距离计算

提取规则：
1. origin 和 destination 必须提取用户明确表达的地点。
2. 不得编造用户没有提供的起点或终点。
3. 用户明确说步行、走路时选择 walking。
4. 用户明确说开车、驾车时选择 driving。
5. 用户明确说公交、地铁、公共交通时选择 transit。
6. 用户明确说骑车、自行车时选择 bicycling。
7. 用户只想知道两地距离时选择 distance。
8. 如果用户没有明确表达交通方式，但要求规划路线，默认选择 transit（公交/地铁）。
9. transit 必须提供 city 和 cityd；如果起点和终点在同一城市，两个字段填写相同城市。
10. distance_type 只能是 0、1、3，默认是 1。
11. 尽可能提取出发城市 city 和目的地城市 cityd。
12. 用户明确说出城市时，必须提取。
13. 如果没有提及城市，但可以根据明确的地点名称判断所在城市，可以提取该城市；无法判断时设置为 null。
14. 不要将用户没有指定的交通方式理解为驾车。
15. 用户明确指定的交通方式优先于默认交通方式。
16. transit 必须提供 city 和 cityd；如果起点和终点在同一城市，两个字段填写相同城市。
17. distance_type 只能是 0、1、3，默认是 1。
18. 尽可能提取出发城市 city 和目的地城市 cityd。
19. 用户明确说出城市时，必须提取。
20. 如果没有提及城市，设置为 null。

用户需求：
""" + user_input.strip()

        response = await self.llm.chat(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0,
        )

        params = self._parse_json(response)

        user_text = user_input.strip()

        # 1. 优先判断是否为距离计算任务
        # 判断是否为距离计算任务
        distance_keywords = [
            "距离",
            "多远",
            "相距",
        ]

        distance_action_keywords = [
            "计算",
            "查询",
            "测量",
            "多少",
            "有多远",
            "多远",
        ]

        is_distance_query = (
                any(keyword in user_text for keyword in distance_keywords)
                and any(keyword in user_text for keyword in distance_action_keywords)
        )

        if is_distance_query:
            params["task_type"] = "distance"

        else:
            # 2. 判断用户是否明确指定交通方式
            transport_keywords = {
                "walking": ["步行", "走路", "徒步"],
                "driving": ["开车", "驾车", "自驾"],
                "transit": ["公交", "地铁", "公共交通", "坐公交", "坐地铁"],
                "bicycling": ["骑车", "骑行", "自行车", "骑单车"],
            }

            explicit_task_type = None

            for task_type, keywords in transport_keywords.items():
                if any(keyword in user_text for keyword in keywords):
                    explicit_task_type = task_type
                    break

            # 3. 用户明确指定交通方式时，遵从用户选择
            if explicit_task_type is not None:
                params["task_type"] = explicit_task_type

            # 4. 没有指定交通方式时，默认公共交通
            else:
                params["task_type"] = "transit"

        return self._validate_params(params)

    @staticmethod
    def _validate_params(params: dict[str, Any]) -> dict[str, Any]:
        """验证路线参数，避免无效参数传入工具层。"""

        task_type = params.get("task_type")

        if task_type not in ROUTE_TASK_TYPES:
            raise ValueError(f"不支持的路线任务类型：{task_type}")

        origin = params.get("origin")
        destination = params.get("destination")

        if not isinstance(origin, str) or not origin.strip():
            raise ValueError("出发地不能为空")

        if not isinstance(destination, str) or not destination.strip():
            raise ValueError("目的地不能为空")

        result = {
            "task_type": task_type,
            "origin": origin.strip(),
            "destination": destination.strip(),
            "city": params.get("city"),
            "cityd": params.get("cityd"),
        }

        for field in ("city", "cityd"):
            value = result[field]

            if value is not None:
                if not isinstance(value, str):
                    raise ValueError(f"{field} 必须是字符串或 null")
                result[field] = value.strip() or None

        if task_type == "transit":
            city = params.get("city")
            cityd = params.get("cityd")

            if not isinstance(city, str) or not city.strip():
                raise ValueError("公交路线必须提供出发城市 city")

            if not isinstance(cityd, str) or not cityd.strip():
                raise ValueError("公交路线必须提供目的地城市 cityd")

            result["city"] = city.strip()
            result["cityd"] = cityd.strip()

        if task_type == "distance":
            distance_type = params.get("distance_type", 1)

            if (
                isinstance(distance_type, bool)
                or distance_type not in (0, 1, 3)
            ):
                raise ValueError("distance_type 只能是 0、1 或 3")

            result["distance_type"] = distance_type

        return result


    async def _geocode_location(
        self,
        address: str,
        city: str | None = None,
    ) -> str:
        """将地点名称转换为高德路线工具需要的经纬度字符串。"""

        arguments = {
            "address": address,
            "city": city,
        }

        result = await execute_tool("geocode", arguments)

        if not result.get("success"):
            raise RuntimeError(
                f"地点解析失败：{address}，"
                f"错误：{result.get('error')}"
            )

        data = result.get("data")

        if not isinstance(data, dict):
            raise ValueError(f"地点解析结果格式错误：{address}")

        location = data.get("location")

        if not isinstance(location, str) or not location.strip():
            raise ValueError(f"无法获取地点坐标：{address}")

        return location.strip()


    async def plan_route(self, user_input: str) -> dict[str, Any]:
        """
        完整路线规划流程：
        提取参数 -> 调用高德工具 -> LLM 整理结果。
        """

        params = await self.extract_route_params(user_input)

        task_type = params["task_type"]

        # 根据任务类型选择已经注册的高德工具
        tool_mapping = {
            "walking": "plan_walking_route",
            "driving": "plan_driving_route",
            "transit": "plan_transit_route",
            "bicycling": "plan_bicycling_route",
            "distance": "calculate_distance",
        }

        tool_name = tool_mapping[task_type]

        # 构造与现有工具函数签名一致的参数
        if task_type == "transit":
            arguments = {
                "origin": params["origin"],
                "destination": params["destination"],
                "city": params["city"],
                "cityd": params["cityd"],
            }
        elif task_type == "distance":
            arguments = {
                "origins": params["origin"],
                "destination": params["destination"],
                "distance_type": params["distance_type"],
            }
        else:
            arguments = {
                "origin": params["origin"],
                "destination": params["destination"],
            }


        # 先将起点、终点转换为经纬度
        try:
            origin_location = await self._geocode_location(
                params["origin"],
                params.get("city"),
            )

            destination_location = await self._geocode_location(
                params["destination"],
                params.get("cityd") or params.get("city"),
            )

        except Exception as exc:
            return {
                "success": False,
                "task": task_type,
                "tool": tool_name,
                "route_params": params,
                "route_data": None,
                "answer": "地点解析失败，暂时无法规划路线。",
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }

        # 将地名参数替换为经纬度
        if task_type == "distance":
            arguments["origins"] = origin_location
            arguments["destination"] = destination_location
        else:
            arguments["origin"] = origin_location
            arguments["destination"] = destination_location

        # 调用路线工具
        route_result = await execute_tool(
            tool_name,
            arguments,
        )


        if not route_result.get("success"):
            return {
                "success": False,
                "task": task_type,
                "tool": tool_name,
                "route_params": params,
                "route_data": None,
                "answer": "路线查询失败，请检查地点信息或稍后重试。",
                "error": route_result.get("error"),
            }

        route_data = route_result.get("data")

        # 将真实路线数据交给 LLM 整理
        route_json = json.dumps(
            route_data,
            ensure_ascii=False,
            indent=2,
        )

        summary_prompt = f"""
用户的路线需求：
{user_input}

路线任务类型：
{task_type}

高德地图返回的真实路线数据：
{route_json}

请根据以上数据向用户解释路线规划结果。

要求：
1. 只能依据高德返回的数据。
2. 不要编造路线、距离、耗时和费用。
3. 如果有多个方案，可以比较它们的优缺点。
4. 使用中文，结构清晰。
5. 如果数据为空或不足，请明确说明。
"""

        answer = await self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                {
                    "role": "user",
                    "content": summary_prompt,
                },
            ],
            temperature=0.3,
        )

        return {
            "success": True,
            "task": task_type,
            "tool": tool_name,
            "route_params": params,
            "route_data": route_data,
            "answer": answer,
            "error": None,
        }
