
import json
from typing import Any, AsyncIterator

from agents.base_agent import BaseAgent
from agents.sub_agents import (
    SightseeingAgent,
    RouteAgent,
    BudgetAgent,
    ItineraryReviewAgent,
)


# Supervisor 可以识别的任务类型
TASK_TYPES = {
    "sightseeing",
    "route",
    "budget",
    "itinerary",
    "multi_task",
    "general",
}

# multi_task 拆分时允许分配的具体任务
SUB_TASK_TYPES = {
    "sightseeing",
    "route",
    "budget",
    "itinerary",
}


SUPERVISOR_PROMPT = """
你是一个旅行助手系统的总调度 Agent，负责理解用户需求并识别任务类型。

你不需要直接回答用户的旅行问题，只需要分析需求并输出 JSON。

任务类型只能从以下类型中选择：

1. sightseeing：景点搜索、景点推荐、景点介绍
2. route：地点之间的路线规划、交通方式、距离查询
3. budget：旅行费用、预算估算
4. itinerary：制定或优化旅行行程
5. multi_task：用户同时提出了多个需要不同 Agent 处理的任务
6. general：问候、闲聊或与上述旅行任务无关的问题

判断规则：
- 用户只提出一种明确任务时，选择对应类型。
- 用户同时提出多个不同任务时，选择 multi_task。
- multi_task 必须在 sub_tasks 中列出需要执行的具体任务。
- 非 multi_task 的 sub_tasks 必须为空数组。
- 不要根据用户没有表达的需求擅自增加任务。
- 如果用户只是打招呼，选择 general。

必须严格按照下面的 JSON 格式输出，不要输出 Markdown，不要输出额外解释：

{
    "task_type": "sightseeing",
    "sub_tasks": [],
    "reason": "判断理由"
}
非常重要：
sub_tasks 中只能使用以下四个英文字符串：
- sightseeing
- route
- budget
- itinerary

禁止使用中文任务名称。
禁止返回对象、字典或其他复杂结构。
sub_tasks 必须是字符串数组。

例如：
用户需要景点推荐、路线规划和预算估算时，必须返回：

{
    "task_type": "multi_task",
    "sub_tasks": ["sightseeing", "route", "budget"],
    "reason": "用户提出了三个不同的旅行需求"
}
"""


SUMMARY_PROMPT = """
你是一个专业的旅行助手，负责汇总多个旅行业务 Agent 的执行结果。

请根据用户需求和子 Agent 返回的数据，直接生成完整、实用的旅行方案。

要求：
1. 只能使用提供的数据，不得编造信息。
2. 景点任务：列出景点名称和地址，介绍已有的关键信息。
3. 路线任务：说明起点、终点、交通方式和路线结果。
4. 预算任务：列出预算总额和各项费用明细。
5. 多个子任务必须全部汇总，不能遗漏。
6. 失败的任务需要明确说明原因。
7. 估算价格必须标注为估算值。
8. 使用中文，结构清晰，简洁实用。
9. 不需要展示 POI ID、内部字段或技术信息。
10. 直接输出最终旅行方案，不要解释你的分析过程。
"""


class SupervisorAgent(BaseAgent):
    """
    旅行助手总调度 Agent。

    负责：
    1. 理解用户需求
    2. 识别任务类型
    3. 调度不同业务 Agent
    4. 汇总多个 Agent 的执行结果
    """

    def __init__(self, llm_client=None):
        super().__init__(
            name="SupervisorAgent",
            system_prompt=SUPERVISOR_PROMPT,
            llm_client=llm_client,
        )

        # 所有子 Agent 共用 Supervisor 的 LLMClient
        self.sightseeing_agent = SightseeingAgent(
            llm_client=self.llm
        )
        self.route_agent = RouteAgent(
            llm_client=self.llm
        )
        self.budget_agent = BudgetAgent(
            llm_client=self.llm
        )
        self.itinerary_agent = ItineraryReviewAgent(
            llm_client=self.llm
        )

        # 统一管理子 Agent
        self.sub_agents = {
            "sightseeing": self.sightseeing_agent,
            "route": self.route_agent,
            "budget": self.budget_agent,
            "itinerary": self.itinerary_agent,
        }

    @staticmethod
    def _parse_json(response: str) -> dict[str, Any]:
        """解析 LLM 返回的 JSON，兼容 Markdown 代码块。"""

        if not isinstance(response, str) or not response.strip():
            raise ValueError("Supervisor 返回内容不能为空")

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
                f"Supervisor 返回的内容不是有效 JSON：{exc}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError("Supervisor 返回结果必须是 JSON 对象")

        return result

    @staticmethod
    def _validate_result(result: dict[str, Any]) -> dict[str, Any]:
        """校验任务分类结果。"""

        task_type = result.get("task_type")
        sub_tasks = result.get("sub_tasks")
        reason = result.get("reason")

        if task_type not in TASK_TYPES:
            raise ValueError(f"不支持的任务类型：{task_type}")

        if not isinstance(sub_tasks, list):
            raise ValueError("sub_tasks 必须是列表")

        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason 必须是非空字符串")

        if task_type == "multi_task":
            if not sub_tasks:
                raise ValueError("multi_task 必须包含至少一个子任务")

            invalid_tasks = [
                task
                for task in sub_tasks
                if not isinstance(task, str)
                   or task.strip() not in SUB_TASK_TYPES
            ]

            if invalid_tasks:
                raise ValueError(
                    f"multi_task 包含不支持的子任务类型：{invalid_tasks}，"
                    f"允许的类型：{sorted(SUB_TASK_TYPES)}"
                )

            # 去除字符串首尾空格
            sub_tasks = [task.strip() for task in sub_tasks]

        elif sub_tasks:
            raise ValueError(
                "只有 multi_task 类型允许包含 sub_tasks"
            )

        # 去重，保留原有顺序
        sub_tasks = list(dict.fromkeys(sub_tasks))

        return {
            "task_type": task_type,
            "sub_tasks": sub_tasks,
            "reason": reason.strip(),
        }

    @staticmethod
    def _build_history_messages(
        history: list[dict[str, Any]] | None,
        limit: int = 10,
    ) -> list[dict[str, str]]:
        """
        校验并截取最近的历史消息。

        只保留合法的 user / assistant 消息，
        避免脏数据被拼进模型请求。
        """

        if not history:
            return []

        messages: list[dict[str, str]] = []

        for item in history[-limit:]:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if role not in ("user", "assistant"):
                continue

            if not isinstance(content, str) or not content.strip():
                continue

            messages.append({
                "role": role,
                "content": content.strip(),
            })

        return messages

    async def _resolve_query(
        self,
        user_input: str,
        history: list[dict[str, str]],
    ) -> str:
        """
        结合历史，把省略式追问改写成独立请求。

        例如历史在聊北京景点，用户追问“那上海呢？”，
        改写成“推荐上海的经典景点”，再交给子 Agent 执行。
        """

        user_input = user_input.strip()

        if not history:
            return user_input

        rewrite_prompt = (
            "你是旅行助手的查询改写器。\n"
            "请结合最近对话，把用户当前的输入改写成一个语义完整、"
            "不依赖上下文也能理解的独立请求。\n"
            "要求：\n"
            "1. 保留用户当前输入中的全部意图和约束。\n"
            "2. 可以补齐历史中出现过的城市、景点、时间等信息，"
            "但不得编造历史中不存在的信息。\n"
            "3. 只输出改写后的请求文本，不要解释，不要加引号。\n"
            "4. 如果当前输入本身已经完整，原样输出。\n"
        )

        try:
            response = await self.llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": rewrite_prompt,
                    },
                    *history,
                    {
                        "role": "user",
                        "content": user_input,
                    },
                ],
                temperature=0,
                max_tokens=4096,
            )

        except Exception as exc:
            print(f"查询改写失败，使用原始输入：{exc}")
            return user_input

        rewritten = (response or "").strip()

        return rewritten or user_input

    async def classify_task(
        self,
        user_input: str,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """分析用户需求，返回任务类型和子任务。"""

        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        response = await self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                *self._build_history_messages(history),
                {
                    "role": "user",
                    "content": user_input.strip(),
                },
            ],
            temperature=0,
            max_tokens=4096,
        )

        print("\n========== Supervisor 原始分类响应 ==========")
        print(response)
        print("==============================================\n")

        result = self._parse_json(response)
        return self._validate_result(result)

    async def _execute_sub_task(
        self,
        task_type: str,
        user_input: str,
    ) -> dict[str, Any]:
        """
        根据任务类型调用对应的子 Agent。
        """

        agent = self.sub_agents.get(task_type)

        if agent is None:
            return {
                "success": False,
                "task": task_type,
                "answer": "",
                "error": f"没有找到对应的 Agent：{task_type}",
            }

        try:
            if task_type == "sightseeing":
                result = await agent.recommend(user_input)

            elif task_type == "route":
                result = await agent.plan_route(user_input)

            elif task_type == "budget":
                result = await agent.plan_budget(user_input)

            elif task_type == "itinerary":
                result = await agent.review_itinerary(user_input)

            else:
                raise ValueError(f"不支持的子任务类型：{task_type}")

            return result

        except Exception as exc:
            return {
                "success": False,
                "task": task_type,
                "answer": "",
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }

    def _build_summary_messages(
        self,
        user_input: str,
        classification: dict[str, Any],
        execution_results: list[dict[str, Any]],
        history: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        """构造汇总请求，流式和非流式共用。"""

        payload = {
            "user_request": user_input,
            "classification": classification,
            "execution_results": self._compact_execution_results(
                execution_results
            ),
        }

        user_content = json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )

        return [
            {
                "role": "system",
                "content": SUMMARY_PROMPT,
            },
            *self._build_history_messages(history),
            {
                "role": "user",
                "content": user_content,
            },
        ]

    @staticmethod
    def _summarize_sub_result(result: dict[str, Any]) -> str:
        """把子 Agent 结果压缩成一句话，用于前端展示。"""

        if not isinstance(result, dict):
            return "完成"

        if result.get("success"):
            answer = str(result.get("answer") or "").strip()
            answer = answer.replace("\n", " ")

            return answer[:80] + "..." if len(answer) > 80 else answer or "完成"

        error = result.get("error")

        if isinstance(error, dict):
            message = error.get("message") or error.get("type")
        else:
            message = error

        return f"失败：{message}"[:160]

    async def _summarize_results(
            self,
            user_input: str,
            classification: dict[str, Any],
            execution_results: list[dict[str, Any]],
            history: list[dict[str, Any]] | None = None,
    ) -> str:
        """压缩子 Agent 结果后交给 LLM 汇总。"""

        messages = self._build_summary_messages(
            user_input=user_input,
            classification=classification,
            execution_results=execution_results,
            history=history,
        )

        print("\n========== Supervisor 汇总输入 ==========")
        print(f"原始结果字符数：{len(json.dumps(execution_results, ensure_ascii=False, default=str))}")
        print(f"历史消息条数：{len(self._build_history_messages(history))}")
        print(f"消息字符数：{len(json.dumps(messages, ensure_ascii=False, default=str))}")
        print("==========================================\n")

        response = await self.llm.chat_with_metadata(
            messages=messages,
            temperature=0.3,
            max_tokens=8192,
        )

        answer = response["content"].strip()
        finish_reason = response["finish_reason"]
        usage = response["usage"]

        print("\n========== Supervisor 汇总响应信息 ==========")
        print(f"finish_reason: {finish_reason}")
        print(f"usage: {json.dumps(usage, ensure_ascii=False, indent=2)}")
        print(f"答案字符数: {len(answer)}")
        print(f"答案内容: {repr(answer)}")
        print("==============================================\n")

        if finish_reason == "length":
            print("警告：Supervisor 汇总内容仍然可能被截断！")

        if not answer:
            print("警告：Supervisor 汇总模型没有返回有效文本！")

        return answer

    async def run(
        self,
        user_input: str,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        执行完整旅行助手任务。

        流程：
        1. 结合历史改写当前请求
        2. 任务分类
        3. 调度业务 Agent
        4. 汇总结果
        """

        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        user_input = user_input.strip()

        history_messages = self._build_history_messages(history)

        # 第一步：把省略式追问改写成独立请求
        resolved_input = await self._resolve_query(
            user_input,
            history_messages,
        )

        if resolved_input != user_input:
            print("\n========== 查询改写 ==========")
            print(f"原始输入：{user_input}")
            print(f"改写结果：{resolved_input}")
            print("==============================\n")

        # 第二步：任务分类
        classification = await self.classify_task(
            resolved_input,
            history=history_messages,
        )

        task_type = classification["task_type"]

        # general：直接进行普通对话
        if task_type == "general":
            answer = await self.llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个友好、专业的旅行助手。"
                            "请使用中文回答用户。"
                        ),
                    },
                    *history_messages,
                    {
                        "role": "user",
                        "content": resolved_input,
                    },
                ]
            )

            return {
                "success": True,
                "task_type": task_type,
                "classification": classification,
                "resolved_input": resolved_input,
                "execution_results": [],
                "answer": answer.strip(),
                "error": None,
            }

        # 第三步：确定要执行的具体任务
        if task_type == "multi_task":
            tasks = classification["sub_tasks"]
        else:
            tasks = [task_type]

        # 第四步：按顺序执行子 Agent
        execution_results = []

        for task in tasks:
            result = await self._execute_sub_task(
                task_type=task,
                user_input=resolved_input,
            )

            execution_results.append(result)

        # 第五步：汇总执行结果
        try:
            answer = await self._summarize_results(
                user_input=resolved_input,
                classification=classification,
                execution_results=execution_results,
                history=history_messages,
            )
            print("\n========== Supervisor 汇总调试 ==========")

            print("\n子 Agent 原始执行结果：")
            print(
                json.dumps(
                    execution_results,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )

            print("\nSupervisor 最终汇总答案：")
            print(repr(answer))

            print("==========================================\n")
            summary_error = None

        except Exception as exc:
            summary_error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }

            # 汇总 LLM 失败时，保留子 Agent 原始结果
            answer = (
                "旅行任务已执行，但最终汇总失败。"
                "以下是各业务 Agent 的执行结果：\n"
                + json.dumps(
                    execution_results,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )

        all_success = all(
            item.get("success") is True
            for item in execution_results
        )

        return {
            "success": all_success and summary_error is None,
            "task_type": task_type,
            "classification": classification,
            "resolved_input": resolved_input,
            "execution_results": execution_results,
            "answer": answer,
            "error": summary_error,
        }

    async def run_stream(
        self,
        user_input: str,
        history: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        流式执行任务，逐步产出事件。

        事件类型：
        - stage：当前执行阶段
        - rewritten：查询改写结果
        - classified：任务分类结果
        - tool：工具调用开始/结束（由工具层广播）
        - subtask_done：子任务完成
        - delta：最终回答的增量文本
        - done：本次执行的完整结果

        未捕获的异常会直接抛给调用方（例如任务分类失败），
        由上层决定如何向前端展示。
        """

        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        user_input = user_input.strip()

        history_messages = self._build_history_messages(history)

        yield {
            "event": "stage",
            "data": {
                "stage": "rewrite",
                "label": "理解并改写问题",
            },
        }

        resolved_input = await self._resolve_query(
            user_input,
            history_messages,
        )

        if resolved_input != user_input:
            yield {
                "event": "rewritten",
                "data": {
                    "original": user_input,
                    "resolved": resolved_input,
                },
            }

        yield {
            "event": "stage",
            "data": {
                "stage": "classify",
                "label": "识别任务类型",
            },
        }

        classification = await self.classify_task(
            resolved_input,
            history=history_messages,
        )

        task_type = classification["task_type"]

        yield {
            "event": "classified",
            "data": classification,
        }

        # general：不需要业务 Agent，直接流式闲聊
        if task_type == "general":
            async for event in self._stream_answer(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个友好、专业的旅行助手。"
                            "请使用中文回答用户。"
                        ),
                    },
                    *history_messages,
                    {
                        "role": "user",
                        "content": resolved_input,
                    },
                ],
                classification=classification,
                resolved_input=resolved_input,
            ):
                yield event

            return

        if task_type == "multi_task":
            tasks = classification["sub_tasks"]
        else:
            tasks = [task_type]

        execution_results = []

        for task in tasks:
            yield {
                "event": "stage",
                "data": {
                    "stage": "subtask",
                    "task": task,
                    "label": f"执行 {task} 任务",
                },
            }

            result = await self._execute_sub_task(
                task_type=task,
                user_input=resolved_input,
            )

            execution_results.append(result)

            yield {
                "event": "subtask_done",
                "data": {
                    "task": task,
                    "success": result.get("success") is True,
                    "summary": self._summarize_sub_result(result),
                },
            }

        yield {
            "event": "stage",
            "data": {
                "stage": "summary",
                "label": "汇总生成回答",
            },
        }

        messages = self._build_summary_messages(
            user_input=resolved_input,
            classification=classification,
            execution_results=execution_results,
            history=history_messages,
        )

        answer_parts: list[str] = []
        summary_error = None

        try:
            async for delta in self.llm.chat_stream(
                messages=messages,
                temperature=0.3,
                max_tokens=8192,
            ):
                answer_parts.append(delta)

                yield {
                    "event": "delta",
                    "data": {"text": delta},
                }

            answer = "".join(answer_parts).strip()

        except Exception as exc:
            summary_error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }

            answer = (
                "旅行任务已执行，但最终汇总失败。"
                "以下是各业务 Agent 的执行结果：\n"
                + json.dumps(
                    execution_results,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )

            yield {
                "event": "delta",
                "data": {"text": answer},
            }

        all_success = all(
            item.get("success") is True
            for item in execution_results
        )

        yield {
            "event": "done",
            "data": {
                "success": all_success and summary_error is None,
                "task_type": task_type,
                "classification": classification,
                "resolved_input": resolved_input,
                "execution_results": execution_results,
                "answer": answer,
                "error": summary_error,
            },
        }

    async def _stream_answer(
        self,
        messages: list[dict[str, str]],
        classification: dict[str, Any],
        resolved_input: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式输出纯文本回答，用于 general 任务。"""

        parts: list[str] = []
        error = None

        try:
            async for delta in self.llm.chat_stream(messages=messages):
                parts.append(delta)

                yield {
                    "event": "delta",
                    "data": {"text": delta},
                }

        except Exception as exc:
            error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }

        answer = "".join(parts).strip()

        if error is not None and not answer:
            message = f"回答生成失败：{error['message']}"
            answer = message

            yield {
                "event": "delta",
                "data": {"text": message},
            }

        yield {
            "event": "done",
            "data": {
                "success": error is None,
                "task_type": "general",
                "classification": classification,
                "resolved_input": resolved_input,
                "execution_results": [],
                "answer": answer,
                "error": error,
            },
        }

    async def close(self):
        """
        关闭 Supervisor。

        子 Agent 使用共享 LLM，因此它们的 close()
        不会关闭共享客户端。

        最后由 Supervisor 关闭自己创建的 LLM。
        """

        for agent in self.sub_agents.values():
            await agent.close()

        await super().close()

    def _compact_execution_results(
        self,
        execution_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        压缩子 Agent 执行结果，去除对最终旅行方案无用的字段。
        保留景点、路线、预算等重要信息。
        """

        ignored_keys = {
            "poi_id",
            "typecode",
            "alias",
            "photo",
            "photos",
            "location",
            "city",
            "province",
            "district",
        }

        def compact(value, depth=0):
            if value is None:
                return None

            if depth > 6:
                return str(value)[:300]

            if isinstance(value, dict):
                result = {}

                for key, item in value.items():
                    if key in ignored_keys or item is None:
                        continue

                    compacted = compact(item, depth + 1)

                    if compacted is not None:
                        result[key] = compacted

                return result

            if isinstance(value, list):
                # 景点列表单独处理，避免前几个景点的内部 POI
                # 占满整个列表，导致其他独立景点被截掉。
                return [
                    compact(item, depth + 1)
                    for item in value[:30]
                ]

            if isinstance(value, str):
                return value[:1500]

            return value

        return compact(execution_results)

