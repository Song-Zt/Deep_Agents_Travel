
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

import agents.sub_agents.sightseeing_agent as sightseeing_module
from agents.sub_agents import SightseeingAgent


class FakeLLM:
    """模拟大模型，避免测试时调用真实 API。"""

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


@pytest.mark.asyncio
async def test_extract_search_params():
    llm = FakeLLM([
        '{"keywords":"旅游景点","city":"北京"}'
    ])
    agent = SightseeingAgent(llm_client=llm)

    result = await agent.extract_search_params(
        "推荐几个北京适合游玩的景点"
    )

    assert result == {
        "keywords": "旅游景点",
        "keyword_list": ["旅游景点"],
        "city": "北京",
    }
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_extract_search_params_without_city():
    llm = FakeLLM([
        '{"keywords":"自然风景区","city":null}'
    ])
    agent = SightseeingAgent(llm_client=llm)

    result = await agent.extract_search_params(
        "我想去自然风景区游玩"
    )

    assert result["keywords"] == "自然风景区"
    assert result["city"] is None


@pytest.mark.asyncio
async def test_recommend_success(monkeypatch):
    llm = FakeLLM([
        '{"keywords":"旅游景点","city":"北京"}',
        '{"relevant_indexes":[0,1],"irrelevant":[]}',
        "根据查询结果，推荐故宫和天坛。",
    ])

    async def fake_execute_tool(tool_name, arguments):
        assert tool_name == "search_places"
        assert arguments["keywords"] == "旅游景点"
        assert arguments["city"] == "北京"

        return {
            "success": True,
            "tool": "search_places",
            "data": [
                {
                    "name": "故宫博物院",
                    "address": "北京市东城区景山前街4号",
                    "location": "116.397,39.918",
                },
                {
                    "name": "天坛公园",
                    "address": "北京市东城区天坛东里甲1号",
                    "location": "116.407,39.883",
                },
            ],
            "error": None,
        }

    monkeypatch.setattr(
        sightseeing_module,
        "execute_tool",
        fake_execute_tool,
    )

    agent = SightseeingAgent(llm_client=llm)
    result = await agent.recommend("推荐北京的旅游景点")

    assert result["success"] is True
    assert result["task"] == "sightseeing"
    assert len(result["places"]) == 2
    assert "故宫" in result["answer"]
    assert result["rejected_places"] == []
    assert llm.call_count == 3


@pytest.mark.asyncio
async def test_recommend_search_failure(monkeypatch):
    llm = FakeLLM([
        '{"keywords":"旅游景点","city":"北京"}'
    ])

    async def fake_execute_tool(tool_name, arguments):
        return {
            "success": False,
            "tool": "search_places",
            "data": None,
            "error": {
                "type": "ConnectionError",
                "message": "MCP 连接失败",
            },
        }

    monkeypatch.setattr(
        sightseeing_module,
        "execute_tool",
        fake_execute_tool,
    )

    agent = SightseeingAgent(llm_client=llm)
    result = await agent.recommend("推荐北京的旅游景点")

    assert result["success"] is False
    assert result["places"] == []
    assert result["error"]["type"] == "ConnectionError"
    # 搜索失败后，不再调用第二次 LLM 生成推荐
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_recommend_no_places(monkeypatch):
    llm = FakeLLM([
        '{"keywords":"旅游景点","city":"北京"}'
    ])

    async def fake_execute_tool(tool_name, arguments):
        return {
            "success": True,
            "tool": "search_places",
            "data": [],
            "error": None,
        }

    monkeypatch.setattr(
        sightseeing_module,
        "execute_tool",
        fake_execute_tool,
    )

    agent = SightseeingAgent(llm_client=llm)
    result = await agent.recommend("推荐北京的旅游景点")

    assert result["success"] is True
    assert result["places"] == []
    assert "没有查询到" in result["answer"]
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_extract_invalid_json():
    llm = FakeLLM(["这不是 JSON"])
    agent = SightseeingAgent(llm_client=llm)

    with pytest.raises(ValueError, match="不是有效 JSON"):
        await agent.extract_search_params("推荐北京的景点")


@pytest.mark.asyncio
async def test_extract_empty_keywords():
    llm = FakeLLM([
        '{"keywords":"","city":"北京"}'
    ])
    agent = SightseeingAgent(llm_client=llm)

    with pytest.raises(ValueError, match="有效的景点搜索关键词"):
        await agent.extract_search_params("推荐北京的景点")


@pytest.mark.asyncio
async def test_search_multiple_keywords_filters_non_attractions(monkeypatch):
    """酒店、火车站、寄存点、办公楼、票务处等不应作为景点推荐。"""

    places = [
        {"name": "天安门广场", "typecode": "110210|110105"},
        {"name": "故宫博物院", "typecode": "110201|140100"},
        {"name": "中国人民革命军事博物馆", "typecode": "140100"},
        {"name": "汉庭酒店(北京天安门广场店)", "typecode": "100105"},
        {"name": "八达岭长城站", "typecode": "150200"},
        {"name": "天安门广场寄存点(鑫通平价超市)", "typecode": "072101"},
        {"name": "中国国家博物馆亦庄办公楼", "typecode": "120201"},
        {"name": "中国人民革命军事博物馆-票务处", "typecode": "070300"},
    ]

    async def fake_execute_tool(tool_name, arguments):
        return {
            "success": True,
            "tool": "search_places",
            "data": places,
            "error": None,
        }

    monkeypatch.setattr(
        sightseeing_module,
        "execute_tool",
        fake_execute_tool,
    )

    agent = SightseeingAgent(llm_client=FakeLLM([]))
    result = await agent.search_multiple_keywords(["北京景点"], "北京")

    names = [place["name"] for place in result["places"]]

    assert names == [
        "天安门广场",
        "故宫博物院",
        "中国人民革命军事博物馆",
    ]


@pytest.mark.asyncio
async def test_search_keeps_places_without_typecode(monkeypatch):
    """没有分类代码的 POI 无法判断类型，应保留。"""

    async def fake_execute_tool(tool_name, arguments):
        return {
            "success": True,
            "tool": "search_places",
            "data": [{"name": "天坛公园"}],
            "error": None,
        }

    monkeypatch.setattr(
        sightseeing_module,
        "execute_tool",
        fake_execute_tool,
    )

    agent = SightseeingAgent(llm_client=FakeLLM([]))
    result = await agent.search_multiple_keywords(["天坛"], "北京")

    assert [place["name"] for place in result["places"]] == ["天坛公园"]


@pytest.mark.asyncio
async def test_group_by_core_scenic_area(monkeypatch):
    """景区内部景点应归属到核心景区，独立景区仍单独保留。"""

    places = [
        {"name": "颐和园", "typecode": "110201", "address": "新建宫门路19号"},
        {"name": "颐和园-佛香阁", "typecode": "110205", "address": "新建宫门路19号颐和园"},
        {"name": "德和园", "typecode": "110000", "address": "新建宫门路19号颐和园内(东侧)"},
        {"name": "北海公园", "typecode": "110101", "address": "文津街1号"},
        {"name": "北海公园(北岸)", "typecode": "110101", "address": "文津街1号北海公园"},
        {"name": "八达岭长城", "typecode": "110202", "address": "G6京藏高速"},
        {"name": "八达岭长城北城", "typecode": "110200", "address": "北二楼东侧"},
        {"name": "八达岭水关长城", "typecode": "110202", "address": "八达岭石佛寺村"},
        {"name": "八达岭古长城自然风景区", "typecode": "110202", "address": "八达岭镇东沟村"},
    ]

    async def fake_execute_tool(tool_name, arguments):
        return {
            "success": True,
            "tool": "search_places",
            "data": places,
            "error": None,
        }

    monkeypatch.setattr(
        sightseeing_module,
        "execute_tool",
        fake_execute_tool,
    )

    agent = SightseeingAgent(llm_client=FakeLLM([]))
    result = await agent.search_multiple_keywords(
        ["颐和园", "北海公园", "八达岭长城"],
        "北京",
    )

    names = [place["name"] for place in result["places"]]

    assert names == [
        "颐和园",
        "北海公园",
        "八达岭长城",
        "八达岭水关长城",
        "八达岭古长城自然风景区",
    ]

    by_name = {place["name"]: place for place in result["places"]}

    assert [p["name"] for p in by_name["颐和园"]["sub_places"]] == [
        "颐和园-佛香阁",
        "德和园",
    ]
    assert [p["name"] for p in by_name["北海公园"]["sub_places"]] == [
        "北海公园(北岸)",
    ]
    assert [p["name"] for p in by_name["八达岭长城"]["sub_places"]] == [
        "八达岭长城北城",
    ]


@pytest.mark.asyncio
async def test_relevance_filter_drops_unrelated_places():
    """明显偏离用户需求的景点应被剔除并记录原因。"""

    llm = FakeLLM([
        '{"relevant_indexes":[0],'
        '"irrelevant":[{"index":1,"reason":"与用户需求无关"}]}'
    ])

    agent = SightseeingAgent(llm_client=llm)

    places = [
        {"name": "中国人民革命军事博物馆", "address": "复兴路9号"},
        {"name": "天安门广场", "address": "东长安街"},
    ]

    kept, rejected = await agent._filter_relevant_places(
        "我想去军事博物馆",
        places,
    )

    assert [place["name"] for place in kept] == ["中国人民革命军事博物馆"]
    assert rejected[0]["name"] == "天安门广场"
    assert rejected[0]["reason"] == "与用户需求无关"


@pytest.mark.asyncio
async def test_relevance_filter_keeps_all_on_invalid_response():
    """模型返回异常时保留全部候选，不影响推荐流程。"""

    llm = FakeLLM(["这不是 JSON", "这也不是 JSON"])
    agent = SightseeingAgent(llm_client=llm)

    places = [{"name": "故宫博物院"}, {"name": "天坛公园"}]

    kept, rejected = await agent._filter_relevant_places(
        "推荐北京景点",
        places,
    )

    assert len(kept) == 2
    assert rejected == []


def test_operating_status_filter():
    """暂停营业、建设中的 POI 应被剔除并记录。"""

    places = [
        {"name": "八达岭长城", "address": "G6京藏高速"},
        {"name": "八达岭长城熊乐园售票处(暂停营业)", "address": "八达岭长城内"},
        {"name": "某景区", "address": "建设中，暂未开放"},
    ]

    kept, rejected = SightseeingAgent._filter_operating_status(places)

    assert [place["name"] for place in kept] == ["八达岭长城"]
    assert len(rejected) == 2
    assert "暂停营业" in rejected[0]["reason"]
    assert "建设中" in rejected[1]["reason"]


@pytest.mark.asyncio
async def test_recommend_reports_rejected_places(monkeypatch):
    """完整流程中，被剔除的景点应出现在 rejected_places 中。"""

    llm = FakeLLM([
        '{"keywords":"八达岭长城","city":"北京"}',
        '{"relevant_indexes":[],"irrelevant":[{"index":0,"reason":"与用户需求无关"}]}',
    ])

    async def fake_execute_tool(tool_name, arguments):
        return {
            "success": True,
            "tool": "search_places",
            "data": [
                {"name": "天安门广场", "typecode": "110210|110105"},
            ],
            "error": None,
        }

    monkeypatch.setattr(
        sightseeing_module,
        "execute_tool",
        fake_execute_tool,
    )

    agent = SightseeingAgent(llm_client=llm)
    result = await agent.recommend("只想去八达岭长城")

    assert result["success"] is True
    assert result["places"] == []
    assert result["rejected_places"][0]["name"] == "天安门广场"
    assert "没有与需求匹配" in result["answer"]
