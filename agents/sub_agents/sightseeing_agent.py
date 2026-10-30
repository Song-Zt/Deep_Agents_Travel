
import asyncio
import json
from typing import Any

from agents.base_agent import BaseAgent
from tools.registry import execute_tool


SIGHTSEEING_PROMPT = """
你是一名专业的旅行景点推荐助手。

你的任务是根据用户需求，结合高德地图查询到的真实景点数据，
为用户推荐合适的景点。

要求：
1. 只能根据提供的景点数据进行推荐。
2. 不得编造景点名称、地址、评分、开放时间等信息。
3. 如果数据中没有某个字段，应明确说明暂无数据，不要猜测。
4. 推荐时尽量考虑用户提出的兴趣和偏好。
5. 如果查询结果包含多个景点，尽量提供多个不同景点供用户选择。
6. 不要为了凑数量而重复推荐同一个景点。
7. 使用清晰、自然的中文回答。
"""


class SightseeingAgent(BaseAgent):
    """
    景点推荐 Agent。

    功能：
    1. 从用户需求中提取多个景点搜索关键词和城市。
    2. 并发调用高德地图搜索景点。
    3. 合并多次搜索结果。
    4. 根据 POI ID 或名称地址去重。
    5. 根据真实 POI 数据生成景点推荐。
    """

    MAX_SEARCH_KEYWORDS = 6

    # 高德 POI 一级分类中可视为景点的类型：
    # 11 风景名胜、14 科教文化服务（博物馆、展览馆、美术馆等）
    ALLOWED_TYPECODE_PREFIXES = ("11", "14")

    # 名称中包含这些词的 POI 视为可能独立存在的景区，不合并到上级景区
    INDEPENDENT_SCENIC_MARKERS = (
        "水关",
        "古长城",
        "自然风景区",
        "风景区",
        "森林公园",
    )

    # 每个核心景区最多保留多少个内部景点作为补充信息
    MAX_SUB_PLACES = 8

    def __init__(self, llm_client=None):
        super().__init__(
            name="SightseeingAgent",
            system_prompt=SIGHTSEEING_PROMPT,
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

    @staticmethod
    def _normalize_keywords(
        keywords: Any,
    ) -> list[str]:
        """
        统一关键词格式。

        兼容：
        1. 字符串
        2. 字符串列表
        3. 旧版模型只返回一个 keywords 字符串
        """
        if isinstance(keywords, str):
            # 兼容模型用逗号、顿号或分号分隔多个关键词
            keywords = (
                keywords.replace("，", ",")
                .replace("、", ",")
                .replace("；", ",")
                .replace(";", ",")
            )
            keyword_list = keywords.split(",")

        elif isinstance(keywords, list):
            keyword_list = keywords

        else:
            raise ValueError("景点搜索关键词必须是字符串或字符串列表")

        result = []
        seen = set()

        for keyword in keyword_list:
            if not isinstance(keyword, str):
                continue

            keyword = keyword.strip()

            if not keyword or keyword in seen:
                continue

            seen.add(keyword)
            result.append(keyword)

            if len(result) >= SightseeingAgent.MAX_SEARCH_KEYWORDS:
                break

        if not result:
            raise ValueError("模型未能提取有效的景点搜索关键词")

        return result

    async def extract_search_params(
        self,
        user_input: str,
    ) -> dict[str, Any]:
        """使用 LLM 提取多个景点搜索关键词和城市。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        prompt = """
你是旅行景点搜索参数提取器。

请从用户的旅行需求中提取景点搜索参数。
只返回 JSON，不要输出 Markdown 或其他解释。

格式：
{
    "keywords": [
        "故宫博物院",
        "天坛公园",
        "颐和园",
        "北海公园"
    ],
    "city": "北京"
}

字段说明：
- keywords：适合高德地图 POI 搜索的关键词列表。
- city：用户明确提到的目的地城市，没有提及时设置为 null。

提取规则：
1. 如果用户明确提到景点名称，必须将这些景点作为搜索关键词。
2. 如果用户要求推荐某个城市的经典景点，尽量提取 3 到 6 个有代表性的景点名称，分别搜索。
3. 如果用户提出特定兴趣，例如历史古迹、自然风光、博物馆，应优先提取相关搜索关键词。
4. 每个关键词应尽量具体，适合独立调用地图 POI 搜索。
5. 不要只返回一个宽泛的“景点”或“旅游景点”关键词。
6. 不要把用户没有提到的城市编造出来。
7. 如果用户只提出一个明确景点，就搜索该景点，不要强行扩展。
8. 最多返回 6 个关键词。
9. 不要提取交通路线、预算等非景点搜索任务。

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

        keyword_list = self._normalize_keywords(
            params.get("keywords")
        )

        city = params.get("city")

        if city is not None:
            if not isinstance(city, str):
                raise ValueError("city 必须是字符串或 null")

            city = city.strip() or None

        return {
            # 保留原来的 keywords 字段，兼容旧代码
            "keywords": keyword_list[0],
            # 新增多个搜索关键词
            "keyword_list": keyword_list,
            "city": city,
        }

    @staticmethod
    def _deduplicate_places(
        places: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """根据 POI ID 或名称和地址去重。"""
        unique_places = []
        seen = set()

        for place in places:
            if not isinstance(place, dict):
                continue

            poi_id = place.get("poi_id")

            if poi_id:
                key = ("poi_id", str(poi_id))
            else:
                name = str(place.get("name") or "").strip()
                address = str(place.get("address") or "").strip()

                if not name and not address:
                    continue

                key = ("name_address", name, address)

            if key in seen:
                continue

            seen.add(key)
            unique_places.append(place)

        return unique_places

    @classmethod
    def _filter_non_attraction_types(
        cls,
        places: list[dict],
    ) -> list[dict]:
        """
        按高德 POI 分类代码过滤非景点类型。

        例如：
        100100 酒店、150200 火车站、072101 寄存点、120201 办公楼。

        没有分类代码的 POI 予以保留，交给名称过滤处理。
        """

        filtered = []

        for place in places:
            typecode = str(place.get("typecode") or "").strip()

            if not typecode:
                filtered.append(place)
                continue

            codes = [
                code.strip()
                for code in typecode.split("|")
                if code.strip()
            ]

            if any(
                code.startswith(cls.ALLOWED_TYPECODE_PREFIXES)
                for code in codes
            ):
                filtered.append(place)

        return filtered

    def _filter_irrelevant_places(self, places: list[dict]) -> list[dict]:
        """
        过滤明显不适合作为独立旅游景点推荐的 POI。
        """

        exclude_keywords = [
            "公交站",
            "地铁站",
            "火车站",
            "高铁站",
            "客运站",
            "停车场",
            "停车区",
            "售票处",
            "售票窗口",
            "票务处",
            "检票处",
            "服务窗口",
            "服务中心",
            "出站口",
            "进站口",
            "接驳车站",
            "直通车",
            "寄存点",
            "寄存处",
            "寄存柜",
            "酒店",
            "宾馆",
            "旅馆",
            "招待所",
            "民宿",
            "公寓",
            "办公楼",
            "写字楼",
            "办公室",
            "保护中心",
            "研究所",
            "管理处",
            "管理中心",
            "桥",
            "大街",
            "道路",
            "路口",
            "加油站",
        ]

        filtered_places = []

        for place in places:
            name = place.get("name", "")

            if not name:
                continue

            # 过滤明显的交通设施和服务设施
            if any(keyword in name for keyword in exclude_keywords):
                continue

            filtered_places.append(place)

        return filtered_places

    @staticmethod
    def _extract_core_indexes(
        places: list[dict[str, Any]],
        keyword_list: list[str],
    ) -> dict[int, str]:
        """
        为每个关键词找出核心景区 POI。

        规则：关键词出现在名称中、且名称最短的那个 POI 视为核心景区，
        例如搜索“颐和园”时，颐和园本身而不是颐和园博物馆。
        """

        core_indexes: dict[int, str] = {}

        for keyword in keyword_list:
            keyword = str(keyword or "").strip()

            if not keyword:
                continue

            candidates = [
                index
                for index, place in enumerate(places)
                if keyword in str(place.get("name") or "")
            ]

            if not candidates:
                continue

            core_index = min(
                candidates,
                key=lambda index: len(
                    str(places[index].get("name") or "")
                ),
            )

            core_indexes.setdefault(core_index, keyword)

        return core_indexes

    @classmethod
    def _is_internal_place(
        cls,
        place: dict[str, Any],
        core: dict[str, Any],
    ) -> bool:
        """判断某个 POI 是否属于核心景区内部。"""

        name = str(place.get("name") or "").strip()
        address = str(place.get("address") or "").strip()
        core_name = str(core.get("name") or "").strip()

        if not name or not core_name or name == core_name:
            return False

        # 可能独立存在的景区优先保留，例如八达岭水关长城、
        # 八达岭古长城自然风景区
        if any(
            marker in name
            for marker in cls.INDEPENDENT_SCENIC_MARKERS
        ):
            return False

        # 1. 名称以核心景区名开头：
        #    颐和园-佛香阁、北海公园(北岸)、八达岭长城北城
        if name.startswith(core_name):
            return True

        # 2. 地址写明所属景区：
        #    德和园 -> 新建宫门路19号颐和园内(东侧)
        if core_name in address:
            return True

        return False

    @classmethod
    def _group_by_core_scenic_area(
        cls,
        places: list[dict[str, Any]],
        keyword_list: list[str],
    ) -> list[dict[str, Any]]:
        """
        按景区归属整理搜索结果。

        1. 核心景区保留在结果中。
        2. 景区内部景点写入核心景区的 sub_places 字段，作为补充信息，
           不再作为独立景点推荐。
        3. 可能独立存在的景区仍作为独立结果保留。
        """

        core_indexes = cls._extract_core_indexes(
            places,
            keyword_list,
        )

        if not core_indexes:
            return places

        sub_places: dict[int, list[dict[str, Any]]] = {
            index: []
            for index in core_indexes
        }

        independent: list[dict[str, Any]] = []

        for index, place in enumerate(places):
            if index in core_indexes:
                continue

            core_index = next(
                (
                    candidate
                    for candidate in core_indexes
                    if cls._is_internal_place(
                        place,
                        places[candidate],
                    )
                ),
                None,
            )

            if core_index is None:
                independent.append(place)
            elif len(sub_places[core_index]) < cls.MAX_SUB_PLACES:
                sub_places[core_index].append(place)

        grouped: list[dict[str, Any]] = []

        for index, place in enumerate(places):
            if index not in core_indexes:
                continue

            grouped.append({
                **place,
                "sub_places": sub_places[index],
            })

        return grouped + independent

    # 高德不单独返回营业状态，状态词直接写在名称或地址里
    CLOSED_STATUS_MARKERS = (
        "暂停营业",
        "停止营业",
        "已关闭",
        "临时关闭",
        "停业",
        "歇业",
        "建设中",
        "施工中",
        "装修中",
        "改造中",
        "未开放",
        "暂未开放",
    )

    @classmethod
    def _filter_operating_status(
        cls,
        places: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """剔除暂停营业、停业、建设中、未开放的 POI。"""

        kept: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for place in places:
            text = " ".join(
                str(place.get(key) or "")
                for key in ("name", "address")
            )

            marker = next(
                (
                    item
                    for item in cls.CLOSED_STATUS_MARKERS
                    if item in text
                ),
                None,
            )

            if marker is None:
                kept.append(place)
            else:
                rejected.append({
                    "name": place.get("name"),
                    "address": place.get("address"),
                    "reason": f"营业状态异常：{marker}",
                })

        return kept, rejected

    async def _filter_relevant_places(
        self,
        user_input: str,
        places: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        用 LLM 判断景点与用户需求的相关性。

        模型异常或返回格式不对时保留全部候选，避免推荐流程整体失败。
        """

        if not places:
            return [], []

        candidates = [
            {
                "index": index,
                "name": place.get("name"),
                "address": place.get("address"),
                "typecode": place.get("typecode"),
            }
            for index, place in enumerate(places)
        ]

        prompt = f"""
你是旅行景点相关性判断助手。

用户需求：
{user_input.strip()}

候选景点：
{json.dumps(candidates, ensure_ascii=False, indent=2)}

请判断每个候选景点是否与用户需求相关，只返回 JSON，不要输出 Markdown 或其他解释。

格式：
{{
    "relevant_indexes": [0, 2],
    "irrelevant": [
        {{"index": 1, "reason": "与用户需求无关的原因"}}
    ]
}}

判断规则：
1. 用户需求宽泛时，例如“推荐北京的经典景点”，只要是真实景点都算相关。
2. 用户明确指定主题或景点时，明显偏离主题的候选判为不相关。
3. 只能使用候选列表中的 index，不要编造。
4. 如果全部相关，irrelevant 返回空列表。
"""

        data = None

        # 推理模型会把推理过程算进 max_tokens，2048 时容易出现
        # finish_reason=length、content 为空，这里逐级放大重试
        for max_tokens in (4096, 8192):
            try:
                response = await self.llm.chat(
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    temperature=0,
                    max_tokens=max_tokens,
                )

                data = self._parse_json(response)
                relevant_indexes = data.get("relevant_indexes")

                if not isinstance(relevant_indexes, list):
                    raise ValueError("relevant_indexes 必须是列表")

                break

            except Exception as exc:
                print(
                    f"景点相关性过滤失败（max_tokens={max_tokens}）：{exc}"
                )
                data = None

        if data is None:
            print("景点相关性过滤最终失败，保留全部候选")
            return places, []

        kept_indexes = {
            index
            for index in data["relevant_indexes"]
            if isinstance(index, int) and 0 <= index < len(places)
        }

        kept = [
            place
            for index, place in enumerate(places)
            if index in kept_indexes
        ]

        rejected: list[dict[str, Any]] = []

        # 模型有时会返回 [1, 2] 这样的整数列表，这里一并兼容
        for item in data.get("irrelevant") or []:
            if isinstance(item, int):
                index = item
                reason = "与用户需求无关"
            elif isinstance(item, dict) and isinstance(item.get("index"), int):
                index = item["index"]
                reason = item.get("reason") or "与用户需求无关"
            else:
                continue

            if not 0 <= index < len(places) or index in kept_indexes:
                continue

            rejected.append({
                "name": places[index].get("name"),
                "address": places[index].get("address"),
                "reason": str(reason),
            })

        return kept, rejected

    async def _search_one_keyword(self, keyword: str, city: str | None):
        try:
            result = await execute_tool(
                "search_places",
                {
                    "keywords": keyword,
                    "city": city,
                },
            )

            if not isinstance(result, dict):
                return {
                    "success": False,
                    "keyword": keyword,
                    "places": [],
                    "error": {
                        "type": "InvalidResult",
                        "message": "搜索工具返回了无效的数据格式",
                    },
                }

            if not result.get("success"):
                return {
                    "success": False,
                    "keyword": keyword,
                    "places": [],
                    "error": result.get("error") or {
                        "type": "SearchError",
                        "message": "景点搜索失败",
                    },
                }

            data = result.get("data")

            if isinstance(data, dict):
                places = data.get("places", data.get("pois", []))
            elif isinstance(data, list):
                places = data
            else:
                places = []

            return {
                "success": True,
                "keyword": keyword,
                "places": places,
                "error": None,
            }

        except Exception as e:
            return {
                "success": False,
                "keyword": keyword,
                "places": [],
                "error": {
                    "type": type(e).__name__,
                    "message": str(e),
                },
            }

    async def search_multiple_keywords(
        self,
        keyword_list: list[str],
        city: str | None,
    ) -> dict[str, Any]:
        """并发搜索多个关键词，合并并去重结果。"""
        tasks = [
            self._search_one_keyword(keyword, city)
            for keyword in keyword_list
        ]

        results = await asyncio.gather(*tasks)

        all_places = []

        successful_keywords = []
        failed_searches = []

        for result in results:
            if result["success"]:
                successful_keywords.append(result["keyword"])
                all_places.extend(result["places"])
            else:
                failed_searches.append({
                    "keyword": result["keyword"],
                    "error": result["error"],
                })

        unique_places = self._deduplicate_places(all_places)

        # 先按 POI 分类代码过滤酒店、车站、寄存点、办公楼等非景点
        unique_places = self._filter_non_attraction_types(unique_places)

        # 过滤交通设施、售票处等明显不适合作为独立景点的 POI
        unique_places = self._filter_irrelevant_places(unique_places)

        # 把景区内部景点归属到核心景区，避免作为独立景点推荐
        unique_places = self._group_by_core_scenic_area(
            unique_places,
            keyword_list,
        )

        print(f"最终景点过滤后数量：{len(unique_places)}")

        print("\n========== 景点搜索结果统计 ==========")
        print(f"搜索关键词：{keyword_list}")
        print(f"搜索成功：{successful_keywords}")
        print(f"搜索失败：{failed_searches}")
        print(f"过滤后景点数量：{len(unique_places)}")

        sub_place_count = sum(
            len(place.get("sub_places") or [])
            for place in unique_places
        )

        print(
            f"核心/独立景点数量：{len(unique_places)}，"
            f"已归属的内部景点数量：{sub_place_count}"
        )

        for index, place in enumerate(unique_places, 1):
            print(
                f"{index}. "
                f"{place.get('name')} | "
                f"{place.get('address')}"
            )

        print("======================================\n")

        return {
            "places": unique_places,
            "successful_keywords": successful_keywords,
            "failed_searches": failed_searches,
            "search_count": len(keyword_list),
        }

    async def recommend(
        self,
        user_input: str,
    ) -> dict[str, Any]:
        """
        完整景点推荐流程：

        提取多个关键词
        -> 并发搜索
        -> 合并结果
        -> 去重、过滤、景区归属分组
        -> 相关性过滤
        -> 营业/建设状态检查
        -> LLM 整理推荐
        """
        params = await self.extract_search_params(user_input)

        keyword_list = params["keyword_list"]

        search_data = await self.search_multiple_keywords(
            keyword_list=keyword_list,
            city=params["city"],
        )

        places = search_data["places"]

        # 所有搜索都失败
        if not search_data["successful_keywords"] and search_data["failed_searches"]:

            # 取第一个搜索失败的具体错误
            first_error = search_data["failed_searches"][0].get("error")

            # 防止错误信息为空
            if not isinstance(first_error, dict):
                first_error = {
                    "type": "SearchError",
                    "message": "所有景点关键词搜索均失败",
                }

            return {
                "success": False,
                "task": "sightseeing",
                "search_params": params,
                "places": [],
                "search_info": search_data,
                "rejected_places": [],
                "answer": "景点搜索失败，请检查高德地图服务或稍后重试。",
                "error": first_error,
            }

        # 搜索成功，但没有找到 POI
        if not places:
            return {
                "success": True,
                "task": "sightseeing",
                "search_params": params,
                "places": [],
                "search_info": search_data,
                "rejected_places": [],
                "answer": (
                    "已完成多个关键词搜索，但暂时没有查询到符合条件的景点。"
                    "可以尝试调整城市或搜索关键词。"
                ),
                "error": None,
            }

        # 相关性过滤：只保留与用户需求相关的景点
        places, irrelevant_places = await self._filter_relevant_places(
            user_input,
            places,
        )

        # 营业/建设状态检查：剔除暂停营业、建设中、未开放的景点
        places, closed_places = self._filter_operating_status(places)

        rejected_places = irrelevant_places + closed_places

        # 核心景区内部的景点同样做状态检查
        for place in places:
            sub_places = place.get("sub_places")

            if not sub_places:
                continue

            kept_subs, closed_subs = self._filter_operating_status(
                sub_places
            )

            place["sub_places"] = kept_subs
            rejected_places.extend(closed_subs)

        search_data["places"] = places

        # 过滤后没有可推荐的景点
        if not places:
            return {
                "success": True,
                "task": "sightseeing",
                "search_params": params,
                "places": [],
                "search_info": search_data,
                "rejected_places": rejected_places,
                "answer": (
                    "已查询到景点数据，但过滤后没有与需求匹配"
                    "且正常营业的景点。可以尝试调整城市或搜索关键词。"
                ),
                "error": None,
            }

        # 只把真实查询到的数据交给 LLM
        places_json = json.dumps(
            places,
            ensure_ascii=False,
            indent=2,
        )

        search_info_json = json.dumps(
            search_data,
            ensure_ascii=False,
            indent=2,
        )

        summary_prompt = f"""
用户的旅行需求：
{user_input}

本次景点搜索信息：
{search_info_json}

高德地图实际查询到的景点数据：
{places_json}

请根据以上真实数据，为用户推荐景点。

要求：
1. 只能推荐 POI 数据中实际存在的景点。
2. 不要编造评分、门票、营业时间等信息。
3. 说明每个景点的名称和地址（如果有）。
4. 结合用户需求解释推荐理由。
5. 如果数据中缺少某项信息，请说明暂无数据。
6. 如果查询结果中有多个不同景点，尽量推荐多个，不要只介绍第一个。
7. 不要重复推荐同一个景点。
8. 不要把没有查询成功的关键词说成已经找到景点。
9. 如果搜索结果数量有限，应明确说明实际查询到的景点数量。
10. 不得根据常识补充不在 POI 数据中的景点信息。
11. 数据中带 sub_places 字段的是核心景区内部的景点，例如颐和园内的德和园、
    北海公园内的白塔。它们只能作为该核心景区的补充说明，
    不要单独列为推荐景点，也不要与本景区并列。
12. sub_places 为空的核心景区，按一个景区整体推荐即可。
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
            "task": "sightseeing",
            "search_params": params,
            "places": places,
            "search_info": search_data,
            "rejected_places": rejected_places,
            "answer": answer,
            "error": None,
        }
