
import json
import math
from typing import Any

from agents.base_agent import BaseAgent


BUDGET_PROMPT = """
你是一名专业的旅行预算规划助手。

你的任务是根据程序计算出的预算数据，为用户解释旅行预算方案。

要求：
1. 只能依据提供的预算数据和估算假设回答。
2. 不得擅自修改预算金额或分配比例。
3. 明确说明这是规划估算，不是实时市场报价。
4. 如果预算存在明显不足，应给出节省开支的建议。
5. 使用清晰、自然的中文回答。
"""


# 用户提供总预算时，按照旅行风格分配的比例
BUDGET_RATIOS = {
    "economy": {
        "accommodation": 0.25,
        "food": 0.25,
        "transport": 0.20,
        "tickets": 0.15,
        "reserve": 0.15,
    },
    "comfortable": {
        "accommodation": 0.30,
        "food": 0.25,
        "transport": 0.20,
        "tickets": 0.15,
        "reserve": 0.10,
    },
    "luxury": {
        "accommodation": 0.40,
        "food": 0.25,
        "transport": 0.15,
        "tickets": 0.10,
        "reserve": 0.10,
    },
}


# 自动估算时使用的默认规划参数。
# 注意：这些是可调整的示例假设，不是实时市场价格。
#
# accommodation_per_room_night：每间房每晚的假设费用
# food_per_person_day：每人每天的假设餐饮费用
# transport_per_person_day：每人每天的假设交通费用
# tickets_per_person_day：每人每天的假设门票及活动费用
# reserve_ratio：备用金占基础费用的比例
ESTIMATION_RATES = {
    "economy": {
        "accommodation_per_room_night": 180,
        "food_per_person_day": 80,
        "transport_per_person_day": 40,
        "tickets_per_person_day": 60,
        "reserve_ratio": 0.10,
    },
    "comfortable": {
        "accommodation_per_room_night": 400,
        "food_per_person_day": 150,
        "transport_per_person_day": 80,
        "tickets_per_person_day": 100,
        "reserve_ratio": 0.10,
    },
    "luxury": {
        "accommodation_per_room_night": 900,
        "food_per_person_day": 300,
        "transport_per_person_day": 180,
        "tickets_per_person_day": 200,
        "reserve_ratio": 0.15,
    },
}


TRAVEL_STYLES = {
    "economy",
    "comfortable",
    "luxury",
}


CATEGORY_NAMES = {
    "accommodation": "住宿",
    "food": "餐饮",
    "transport": "交通",
    "tickets": "景点门票及活动",
    "reserve": "备用金",
}


class BudgetAgent(BaseAgent):
    """
    旅行预算规划 Agent。

    支持：
    1. 提取预算需求
    2. 用户给定总预算后进行预算分配
    3. 用户未给定总预算时自动估算
    4. 计算人均预算
    5. 计算每日预算
    6. 生成预算分析建议
    """

    def __init__(self, llm_client=None):
        super().__init__(
            name="BudgetAgent",
            system_prompt=BUDGET_PROMPT,
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

    async def extract_budget_params(
        self,
        user_input: str,
    ) -> dict[str, Any]:
        """从用户输入中提取预算规划参数。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        prompt = """
你是旅行预算参数提取器。

请分析用户需求，只返回 JSON，不要输出 Markdown 或其他解释。

JSON 格式：
{
    "total_budget": null,
    "days": 3,
    "travelers": 2,
    "city": "北京",
    "travel_style": "comfortable"
}

字段说明：
- total_budget：旅行总预算，单位人民币元。用户没有提供时必须为 null。
- days：旅行天数，必须是正整数。用户没有提供时为 null。
- travelers：出行人数，必须是正整数。用户没有提供时默认为 1。
- city：旅行目的地城市，未提及时设置为 null。
- travel_style：只能是 economy、comfortable、luxury。

提取规则：
1. 用户明确提供预算时，提取总预算。
2. 用户没有提供总预算时，设置为 null，不得自行编造。
3. 用户没有提供天数时，设置为 null。
4. 用户没有提供人数时，默认设置为 1。
5. 用户明确说明城市时，提取城市名称，否则设置为 null。
6. 经济型、穷游、节省开支对应 economy。
7. 舒适型、普通旅行对应 comfortable。
8. 高端、豪华旅行对应 luxury。
9. 没有说明旅行风格时，默认 comfortable。
10. 不得编造用户没有提供的预算和天数。
11. 只提取用户明确表达的信息，不要把推荐方案当成用户已经确定的条件。

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
        return self._validate_params(params)

    @staticmethod
    def _validate_params(
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """验证预算参数，允许 total_budget 为 None。"""
        if not isinstance(params, dict):
            raise ValueError("预算参数必须是字典")

        total_budget = params.get("total_budget")
        days = params.get("days")
        travelers = params.get("travelers", 1)
        city = params.get("city")
        travel_style = params.get(
            "travel_style",
            "comfortable",
        )

        # 总预算可以为空，为空时进入自动估算模式
        if total_budget is not None:
            if (
                isinstance(total_budget, bool)
                or not isinstance(total_budget, (int, float))
                or not math.isfinite(total_budget)
                or total_budget <= 0
            ):
                raise ValueError("旅行总预算必须是大于 0 的数字，或 null")

            total_budget = float(total_budget)

        if (
            isinstance(days, bool)
            or not isinstance(days, int)
            or days <= 0
        ):
            raise ValueError("旅行天数必须是正整数，请明确旅行天数")

        if (
            isinstance(travelers, bool)
            or not isinstance(travelers, int)
            or travelers <= 0
        ):
            raise ValueError("出行人数必须是正整数")

        if city is not None:
            if not isinstance(city, str):
                raise ValueError("城市必须是字符串或 null")

            city = city.strip() or None

        if travel_style not in TRAVEL_STYLES:
            raise ValueError(
                "旅行风格只能是 economy、comfortable 或 luxury"
            )

        return {
            "total_budget": total_budget,
            "days": days,
            "travelers": travelers,
            "city": city,
            "travel_style": travel_style,
        }

    @staticmethod
    def calculate_budget(
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        计算预算。

        total_budget 不为空：按照比例分配用户预算。
        total_budget 为空：根据默认估算参数计算旅行预算。
        """
        params = BudgetAgent._validate_params(params)

        if params["total_budget"] is None:
            return BudgetAgent.estimate_budget(params)

        return BudgetAgent.allocate_budget(params)

    @staticmethod
    def allocate_budget(
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """按照旅行风格分配用户提供的总预算。"""
        total_budget = params["total_budget"]
        travelers = params["travelers"]
        days = params["days"]
        travel_style = params["travel_style"]

        ratios = BUDGET_RATIOS[travel_style]

        allocation = {}

        for key, ratio in ratios.items():
            allocation[key] = {
                "name": CATEGORY_NAMES[key],
                "ratio": ratio,
                "amount": round(total_budget * ratio, 2),
            }

        return {
            "mode": "budget_allocation",
            "total_budget": round(total_budget, 2),
            "days": days,
            "travelers": travelers,
            "city": params["city"],
            "travel_style": travel_style,
            "allocation": allocation,
            "per_person_budget": round(
                total_budget / travelers,
                2,
            ),
            "per_person_daily_budget": round(
                total_budget / travelers / days,
                2,
            ),
            "daily_total_budget": round(
                total_budget / days,
                2,
            ),
            "estimation_assumptions": None,
        }

    @staticmethod
    def estimate_budget(
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        根据人数、天数和旅行风格自动估算预算。

        默认假设：
        1. 两人入住一间房，不足两人也按一间房计算。
        2. 住宿晚数按 max(旅行天数 - 1, 0) 计算。
        3. 餐饮、交通、门票按人天计算。
        4. 备用金按照基础费用的一定比例计算。
        """
        days = params["days"]
        travelers = params["travelers"]
        travel_style = params["travel_style"]

        rates = ESTIMATION_RATES[travel_style]

        rooms = math.ceil(travelers / 2)
        nights = max(days - 1, 0)

        accommodation = (
            rates["accommodation_per_room_night"]
            * rooms
            * nights
        )

        food = (
            rates["food_per_person_day"]
            * travelers
            * days
        )

        transport = (
            rates["transport_per_person_day"]
            * travelers
            * days
        )

        tickets = (
            rates["tickets_per_person_day"]
            * travelers
            * days
        )

        base_total = (
            accommodation
            + food
            + transport
            + tickets
        )

        reserve = base_total * rates["reserve_ratio"]
        total_budget = base_total + reserve

        amounts = {
            "accommodation": accommodation,
            "food": food,
            "transport": transport,
            "tickets": tickets,
            "reserve": reserve,
        }

        allocation = {}

        for key, amount in amounts.items():
            allocation[key] = {
                "name": CATEGORY_NAMES[key],
                "ratio": round(amount / total_budget, 4)
                if total_budget > 0 else 0,
                "amount": round(amount, 2),
            }

        total_budget = round(total_budget, 2)

        return {
            "mode": "budget_estimation",
            "total_budget": total_budget,
            "days": days,
            "travelers": travelers,
            "city": params["city"],
            "travel_style": travel_style,
            "allocation": allocation,
            "per_person_budget": round(
                total_budget / travelers,
                2,
            ),
            "per_person_daily_budget": round(
                total_budget / travelers / days,
                2,
            ),
            "daily_total_budget": round(
                total_budget / days,
                2,
            ),
            "estimation_assumptions": {
                "rates": rates.copy(),
                "rooms": rooms,
                "nights": nights,
                "accommodation_rule": "默认每两人入住一间房",
                "city_factor": "未使用城市差异系数，所有城市采用相同默认参数",
                "price_note": "示例规划参数，不代表实时市场价格",
            },
        }

    async def plan_budget(
        self,
        user_input: str,
    ) -> dict[str, Any]:
        """完整预算规划流程：提取参数、计算预算、生成建议。"""
        params = await self.extract_budget_params(user_input)

        budget_data = self.calculate_budget(params)

        budget_json = json.dumps(
            budget_data,
            ensure_ascii=False,
            indent=2,
        )

        if budget_data["mode"] == "budget_estimation":
            mode_description = """
当前为自动预算估算模式。
请特别说明估算依据、住宿晚数、人数和各项费用假设。
明确指出这些参数是程序内置的示例规划假设，
没有使用实时酒店、餐饮、交通或门票报价。
"""
        else:
            mode_description = """
当前为用户指定总预算的预算分配模式。
请按照程序给出的比例解释各项预算分配。
"""

        summary_prompt = f"""
用户的旅行需求：
{user_input}

程序计算出的预算数据：
{budget_json}

当前预算模式说明：
{mode_description}

请根据预算数据生成旅行预算分析。

要求：
1. 逐项解释住宿、餐饮、交通、景点门票及备用金。
2. 说明总预算、人均预算和人均每日预算。
3. 结合旅行天数和人数分析预算安排。
4. 自动估算模式下，必须说明估算假设和默认参数的局限。
5. 用户指定预算模式下，不得改变预算分配比例。
6. 不得编造酒店、餐厅、门票的真实价格。
7. 明确说明当前金额是规划估算，不是实时市场报价。
8. 如果用户选择经济型，可以给出控制开支的建议。
9. 使用中文，结构清晰。
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
            "task": "budget",
            "budget_params": params,
            "budget_data": budget_data,
            "answer": answer,
            "error": None,
        }
