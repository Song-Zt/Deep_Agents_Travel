from typing import Any

from llm import LLMClient


class BaseAgent:
    """
    所有旅行 Agent 的基础类。

    提供：
    1. Agent 身份和角色提示词
    2. LLM 模型调用
    3. 多轮对话历史管理
    4. 对话重置
    5. 客户端资源关闭
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm_client: LLMClient | None = None,
    ):
        if not name:
            raise ValueError("Agent 名称不能为空")

        if not system_prompt:
            raise ValueError("System Prompt 不能为空")

        self.name = name
        self.system_prompt = system_prompt

        # 是否由当前 Agent 自己创建 LLM 客户端
        self._owns_llm = llm_client is None

        # 支持多个 Agent 共享同一个 LLM 客户端
        self.llm = llm_client or LLMClient()

        # 初始化对话历史
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]

    async def run(self, user_input: str) -> str:
        """
        接收用户输入，调用 LLM 并返回回复。
        """

        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("用户输入不能为空")

        # 保存用户消息
        self.messages.append({
            "role": "user",
            "content": user_input.strip(),
        })

        try:
            # 调用统一 LLM 客户端
            response = await self.llm.chat(
                messages=self.messages
            )

            if not isinstance(response, str):
                raise TypeError("LLM 返回结果必须是字符串")

            response = response.strip()

            # 保存模型回复
            self.messages.append({
                "role": "assistant",
                "content": response,
            })

            return response

        except Exception:
            # 调用失败时，移除本次未完成的用户消息
            self.messages.pop()
            raise

    def reset(self):
        """
        清空对话历史，但保留 Agent 的角色提示词。
        """

        self.messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]

    async def close(self):
        """
        关闭 LLM 客户端。

        如果客户端由外部传入，说明可能被其他 Agent 共享，
        当前 Agent 不负责关闭它。
        """

        if self._owns_llm:
            await self.llm.close()