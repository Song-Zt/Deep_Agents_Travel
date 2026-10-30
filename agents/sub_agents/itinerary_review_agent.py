
import json
from typing import Any

from agents.base_agent import BaseAgent


ITINERARY_REVIEW_PROMPT = """
你是一名专业的旅行行程审核助手。

你的任务是审核用户提供的旅行计划，发现潜在问题并提出优化建议。

审核原则：
1. 只能根据用户提供的行程信息进行判断。
2. 不得编造景点营业时间、交通耗时、门票价格等信息。
3. 如果缺少必要信息，应标记为待确认。
4. 重点检查行程安排是否过于紧凑、是否存在时间冲突、
   是否有明显的路线不合理风险以及预算信息是否完整。
5. 区分明确的问题和需要进一步核实的风险。
6. 使用清晰、自然的中文回答。
"""


class ItineraryReviewAgent(BaseAgent):
    """
    旅行行程审核 Agent。

    支持：
    1. 提取行程信息
    2. 检查行程完整性
    3. 审核时间安排
    4. 识别路线安排风险
    5. 检查预算信息
    6. 生成行程审核报告
    """

    def __init__(self, llm_client=None):
        super().__init__(
            name="ItineraryReviewAgent",
            system_prompt=ITINERARY_REVIEW_PROMPT,
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

    async def extract_itinerary(
        self,
        user_input: str,
    ) -> dict[str, Any]:
        """提取用户提供的行程信息。"""

        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        prompt = """
你是旅行行程信息提取器。

请从用户提供的内容中提取行程信息，只返回 JSON。

JSON 格式：
{
    "destination": "北京",
    "days": 2,
    "travelers": 2,
    "daily_itinerary": [
        {
            "day": 1,
            "activities": [
                {
                    "time": "09:00",
                    "place": "故宫",
                    "description": "参观景点"
                }
            ]
        }
    ],
    "total_budget": 3000,
    "constraints": []
}

提取规则：
1. destination：目的地，没有提及则为 null。
2. days：旅行天数，没有明确提及则为 null。
3. travelers：人数，没有提及则默认为 1。
4. daily_itinerary：按天整理用户明确提供的活动。
5. activities 中的 time、place、description 尽量提取原文信息。
6. 用户没有提供的信息设置为 null 或空列表。
7. total_budget：用户明确提供的总预算，没有提供则为 null。
8. constraints：提取用户明确提出的限制或偏好。
9. 不得编造景点、时间、预算或活动。
10. 只返回 JSON，不要输出其他解释。

用户提供的行程：
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
        """验证提取后的行程参数。"""

        if not isinstance(params, dict):
            raise ValueError("行程参数必须是字典")

        destination = params.get("destination")
        days = params.get("days")
        travelers = params.get("travelers", 1)
        daily_itinerary = params.get("daily_itinerary", [])
        total_budget = params.get("total_budget")
        constraints = params.get("constraints", [])

        if destination is not None:
            if not isinstance(destination, str):
                raise ValueError("目的地必须是字符串或 null")

            destination = destination.strip() or None

        if days is not None:
            if (
                isinstance(days, bool)
                or not isinstance(days, int)
                or days <= 0
            ):
                raise ValueError("旅行天数必须是正整数")

        if (
            isinstance(travelers, bool)
            or not isinstance(travelers, int)
            or travelers <= 0
        ):
            raise ValueError("出行人数必须是正整数")

        if not isinstance(daily_itinerary, list):
            raise ValueError("每日行程必须是列表")

        if total_budget is not None:
            if (
                isinstance(total_budget, bool)
                or not isinstance(total_budget, (int, float))
                or total_budget <= 0
            ):
                raise ValueError("总预算必须是大于 0 的数字或 null")

            total_budget = float(total_budget)

        if not isinstance(constraints, list):
            raise ValueError("行程限制必须是列表")

        for index, day_plan in enumerate(daily_itinerary):
            if not isinstance(day_plan, dict):
                raise ValueError(
                    f"第 {index + 1} 天的行程必须是字典"
                )

            activities = day_plan.get("activities", [])

            if not isinstance(activities, list):
                raise ValueError(
                    f"第 {index + 1} 天的活动必须是列表"
                )

            for activity_index, activity in enumerate(activities):
                if not isinstance(activity, dict):
                    raise ValueError(
                        f"第 {index + 1} 天第 "
                        f"{activity_index + 1} 个活动必须是字典"
                    )

        return {
            "destination": destination,
            "days": days,
            "travelers": travelers,
            "daily_itinerary": daily_itinerary,
            "total_budget": total_budget,
            "constraints": constraints,
        }

    async def review_itinerary(
        self,
        user_input: str,
    ) -> dict[str, Any]:
        """
        完整审核流程：
        提取行程 -> LLM 审核 -> 返回审核报告。
        """

        params = await self.extract_itinerary(user_input)

        itinerary_json = json.dumps(
            params,
            ensure_ascii=False,
            indent=2,
        )

        review_prompt = f"""
请审核下面的旅行行程。

结构化行程信息：
{itinerary_json}

请从以下维度进行审核：
1. completeness：行程信息是否完整。
2. time_arrangement：时间安排是否合理。
3. route_arrangement：路线安排是否存在明显风险。
4. budget：预算信息是否完整、是否存在明显风险。
5. overall：整体评价。

请只返回 JSON，格式如下：

{{
    "overall_status": "pass",
    "score": 85,
    "issues": [
        {{
            "category": "time_arrangement",
            "level": "medium",
            "description": "问题描述",
            "suggestion": "修改建议"
        }}
    ],
    "pending_checks": [
        "需要进一步确认的事项"
    ],
    "summary": "整体审核总结"
}}

字段要求：
- overall_status 只能是 pass、warning、fail。
- score 为 0 到 100 的整数。
- issues 必须是列表。
- issue.level 只能是 low、medium、high。
- pending_checks 必须是列表。
- summary 必须是字符串。

审核规则：
1. 没有发现明显问题时，可以返回 pass。
2. 存在需要调整的问题时，返回 warning。
3. 存在严重时间冲突或明显不可执行的问题时，返回 fail。
4. 不要仅仅因为没有提供实时营业时间就判定行程失败。
5. 对无法从现有信息判断的事项，放入 pending_checks。
6. 不得编造交通时间、门票价格或营业时间。
7. 只返回 JSON，不要输出 Markdown。
"""

        response = await self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                {
                    "role": "user",
                    "content": review_prompt,
                },
            ],
            temperature=0.2,
        )

        review_result = self._parse_json(response)

        review_result = self._validate_review_result(
            review_result
        )

        return {
            "success": True,
            "task": "itinerary_review",
            "itinerary_params": params,
            "review_result": review_result,
            "answer": review_result["summary"],
            "error": None,
        }

    @staticmethod
    def _validate_review_result(
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """验证行程审核报告。"""

        status = result.get("overall_status")
        score = result.get("score")
        issues = result.get("issues")
        pending_checks = result.get("pending_checks")
        summary = result.get("summary")

        if status not in {"pass", "warning", "fail"}:
            raise ValueError("审核状态必须是 pass、warning 或 fail")

        if (
            isinstance(score, bool)
            or not isinstance(score, int)
            or not 0 <= score <= 100
        ):
            raise ValueError("审核评分必须是 0 到 100 的整数")

        if not isinstance(issues, list):
            raise ValueError("审核问题必须是列表")

        for issue in issues:
            if not isinstance(issue, dict):
                raise ValueError("每条审核问题必须是字典")

            if issue.get("category") is None:
                raise ValueError("审核问题必须提供 category")

            if issue.get("level") not in {"low", "medium", "high"}:
                raise ValueError("问题等级必须是 low、medium 或 high")

            if not isinstance(issue.get("description"), str):
                raise ValueError("问题描述必须是字符串")

            if not isinstance(issue.get("suggestion"), str):
                raise ValueError("修改建议必须是字符串")

        if not isinstance(pending_checks, list):
            raise ValueError("待确认事项必须是列表")

        if not all(isinstance(item, str) for item in pending_checks):
            raise ValueError("待确认事项必须全部是字符串")

        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("审核总结不能为空")

        return {
            "overall_status": status,
            "score": score,
            "issues": issues,
            "pending_checks": pending_checks,
            "summary": summary.strip(),
        }
