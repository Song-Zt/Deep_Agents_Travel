
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

import agents.sub_agents.route_agent as route_module
from agents.sub_agents import RouteAgent


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.last_messages = None

    async def chat(self, messages, **kwargs):
        self.last_messages = messages

        if self.call_count >= len(self.responses):
            raise RuntimeError("FakeLLM 没有更多预设响应")

        response = self.responses[self.call_count]
        self.call_count += 1
        return response

    async def close(self):
        pass


def make_params(
    task_type="walking",
    origin="故宫",
    destination="天坛",
    city=None,
    cityd=None,
    distance_type=1,
):
    return {
        "task_type": task_type,
        "origin": origin,
        "destination": destination,
        "city": city,
        "cityd": cityd,
        "distance_type": distance_type,
    }

async def fake_route_execute_tool(tool_name, arguments):
    """
    模拟地理编码和路线工具。

    调用顺序：
    1. geocode 起点
    2. geocode 终点
    3. 路线工具
    """

    # 模拟地理编码
    if tool_name == "geocode":
        address = arguments["address"]

        locations = {
            "故宫": "116.397,39.918",
            "天坛": "116.407,39.883",
            "北京站": "116.427,39.903",
            "颐和园": "116.275,39.999",
        }

        location = locations.get(address)

        if location is None:
            return {
                "success": False,
                "data": None,
                "error": {
                    "type": "ValueError",
                    "message": f"无法解析地点：{address}",
                },
            }

        return {
            "success": True,
            "data": {
                "address": address,
                "location": location,
            },
            "error": None,
        }

    # 模拟路线工具
    route_tools = {
        "plan_walking_route",
        "plan_driving_route",
        "plan_transit_route",
        "plan_bicycling_route",
        "calculate_distance",
    }

    if tool_name in route_tools:
        return {
            "success": True,
            "data": {
                "route": "模拟路线数据",
                "distance": "5公里",
                "origin": arguments.get("origin")
                or arguments.get("origins"),
                "destination": arguments.get("destination"),
            },
            "error": None,
        }

    raise ValueError(f"未知工具：{tool_name}")

@pytest.mark.asyncio
async def test_extract_walking_params():
    llm = FakeLLM([
        '{"task_type":"walking","origin":"故宫",'
        '"destination":"天坛","city":null,'
        '"cityd":null,"distance_type":1}'
    ])
    agent = RouteAgent(llm_client=llm)

    result = await agent.extract_route_params(
        "从故宫步行到天坛"
    )

    assert result["task_type"] == "walking"
    assert result["origin"] == "故宫"
    assert result["destination"] == "天坛"


@pytest.mark.asyncio
async def test_validate_transit_params():
    params = make_params(
        task_type="transit",
        city="北京",
        cityd="北京",
    )

    result = RouteAgent._validate_params(params)

    assert result["city"] == "北京"
    assert result["cityd"] == "北京"


@pytest.mark.asyncio
async def test_transit_requires_city():
    params = make_params(
        task_type="transit",
        city=None,
        cityd="北京",
    )

    with pytest.raises(ValueError, match="出发城市"):
        RouteAgent._validate_params(params)


@pytest.mark.asyncio
async def test_invalid_distance_type():
    params = make_params(
        task_type="distance",
        distance_type=2,
    )

    with pytest.raises(ValueError, match="0、1 或 3"):
        RouteAgent._validate_params(params)


@pytest.mark.asyncio
async def test_distance_rejects_bool():
    params = make_params(
        task_type="distance",
        distance_type=True,
    )

    with pytest.raises(ValueError, match="0、1 或 3"):
        RouteAgent._validate_params(params)


@pytest.mark.asyncio
async def test_empty_origin():
    params = make_params(origin=" ")

    with pytest.raises(ValueError, match="出发地不能为空"):
        RouteAgent._validate_params(params)


@pytest.mark.asyncio
async def test_invalid_task_type():
    params = make_params(task_type="flying")

    with pytest.raises(ValueError, match="不支持的路线任务类型"):
        RouteAgent._validate_params(params)


@pytest.mark.asyncio
async def test_parse_markdown_json():
    llm = FakeLLM([
        '```json\n'
        '{"task_type":"driving","origin":"北京站",'
        '"destination":"故宫","city":null,'
        '"cityd":null,"distance_type":1}\n'
        '```'
    ])
    agent = RouteAgent(llm_client=llm)

    result = await agent.extract_route_params(
        "从北京站开车到故宫"
    )

    assert result["task_type"] == "driving"


@pytest.mark.asyncio
async def test_plan_walking_route(monkeypatch):
    llm = FakeLLM([
        '{"task_type":"walking","origin":"故宫",'
        '"destination":"天坛","city":null,'
        '"cityd":null,"distance_type":1}',
        "建议从故宫步行前往天坛。",
    ])

    monkeypatch.setattr(
        route_module,
        "execute_tool",
        fake_route_execute_tool,
    )

    agent = RouteAgent(llm_client=llm)

    result = await agent.plan_route("从故宫步行到天坛")

    assert result["success"] is True
    assert result["tool"] == "plan_walking_route"
    assert result["route_data"]["distance"] == "5公里"

    # 参数提取一次，路线结果整理一次
    assert llm.call_count == 2


@pytest.mark.asyncio
async def test_plan_transit_route(monkeypatch):
    llm = FakeLLM([
        '{"task_type":"transit","origin":"北京站",'
        '"destination":"颐和园","city":"北京",'
        '"cityd":"北京","distance_type":1}',
        "可以乘坐公共交通前往颐和园。",
    ])

    monkeypatch.setattr(
        route_module,
        "execute_tool",
        fake_route_execute_tool,
    )

    agent = RouteAgent(llm_client=llm)

    result = await agent.plan_route(
        "从北京站坐公交去颐和园"
    )

    assert result["success"] is True
    assert result["tool"] == "plan_transit_route"

    # 公交参数仍然保留城市信息
    assert result["route_params"]["city"] == "北京"
    assert result["route_params"]["cityd"] == "北京"


@pytest.mark.asyncio
async def test_calculate_distance(monkeypatch):
    llm = FakeLLM([
        '{"task_type":"distance","origin":"故宫",'
        '"destination":"天坛","city":null,'
        '"cityd":null,"distance_type":1}',
        "两地距离约为5公里。",
    ])

    monkeypatch.setattr(
        route_module,
        "execute_tool",
        fake_route_execute_tool,
    )

    agent = RouteAgent(llm_client=llm)

    result = await agent.plan_route(
        "计算故宫到天坛的距离"
    )

    assert result["success"] is True
    assert result["tool"] == "calculate_distance"

    assert result["route_data"]["distance"] == "5公里"


@pytest.mark.asyncio
async def test_route_tool_failure(monkeypatch):
    llm = FakeLLM([
        '{"task_type":"walking","origin":"故宫",'
        '"destination":"天坛","city":null,'
        '"cityd":null,"distance_type":1}',
    ])

    async def fake_execute_tool(tool_name, arguments):
        # 地理编码正常
        if tool_name == "geocode":
            locations = {
                "故宫": "116.397,39.918",
                "天坛": "116.407,39.883",
            }

            return {
                "success": True,
                "data": {
                    "location": locations[arguments["address"]],
                },
                "error": None,
            }

        # 路线工具失败
        if tool_name == "plan_walking_route":
            return {
                "success": False,
                "data": None,
                "error": {
                    "type": "ConnectionError",
                    "message": "MCP连接失败",
                },
            }

        raise ValueError(f"未知工具：{tool_name}")

    monkeypatch.setattr(
        route_module,
        "execute_tool",
        fake_execute_tool,
    )

    agent = RouteAgent(llm_client=llm)

    result = await agent.plan_route("从故宫步行到天坛")

    assert result["success"] is False
    assert result["error"]["type"] == "ConnectionError"
    assert result["error"]["message"] == "MCP连接失败"

    # 只提取参数，没有进入路线结果整理阶段
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_empty_input():
    llm = FakeLLM([])
    agent = RouteAgent(llm_client=llm)

    with pytest.raises(ValueError, match="用户输入不能为空"):
        await agent.extract_route_params(" ")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_input", "expected_task_type"),
    [
        ("计算故宫到天坛的距离", "distance"),
        ("故宫到天坛有多远", "distance"),
        ("故宫到天坛怎么走", "transit"),
        ("故宫到天坛怎么开车", "driving"),
        ("故宫到天坛步行怎么走", "walking"),
        ("故宫到天坛怎么骑车", "bicycling"),
        ("故宫到天坛怎么坐地铁", "transit"),
    ],
)
async def test_extract_route_params_task_type(
    user_input,
    expected_task_type,
):
    llm = FakeLLM([
        (
            '{"task_type":"driving",'
            '"origin":"故宫",'
            '"destination":"天坛",'
            '"city":"北京",'
            '"cityd":"北京",'
            '"distance_type":1}'
        )
    ])

    agent = RouteAgent(llm_client=llm)

    params = await agent.extract_route_params(user_input)

    assert params["task_type"] == expected_task_type