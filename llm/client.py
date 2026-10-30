import inspect
from typing import Any

from openai import AsyncOpenAI

from llm.config import get_llm_config


class LLMClient:
    """
    统一的异步 LLM 客户端。

    支持：
    1. 普通文本对话
    2. 自定义 system prompt
    3. Function Calling
    4. 获取原始模型响应
    """

    def __init__(self):
        config = get_llm_config()

        self.model = config.model

        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        """
        调用模型，返回完整响应对象。

        保留完整响应是为了后续处理 Function Calling。
        """

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools is not None:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = await self.client.chat.completions.create(
            **kwargs
        )

        return response

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        普通文本对话，直接返回模型生成的文本。
        """

        response = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content

        return content or ""

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        """
        流式对话，逐段返回模型生成的文本。

        供前端边生成边展示使用。
        """

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        try:
            async for chunk in stream:
                choices = getattr(chunk, "choices", None)

                if not choices:
                    continue

                content = getattr(choices[0].delta, "content", None)

                if content:
                    yield content

        finally:
            # 客户端提前断开时，及时释放流
            for name in ("close", "aclose"):
                close = getattr(stream, name, None)

                if close is None:
                    continue

                try:
                    result = close()

                    if inspect.isawaitable(result):
                        await result

                except Exception:
                    pass

                break

    async def close(self):
        """
        关闭模型客户端连接。
        """

        await self.client.close()

    async def chat_with_metadata(
            self,
            messages: list[dict[str, Any]],
            temperature: float = 0.7,
            max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """普通文本对话，同时返回模型响应元信息。"""

        response = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        print("\n========== LLM 原始响应调试 ==========")
        print("模型名称：", response.model)
        print("响应 ID：", response.id)
        print("Choices 数量：", len(response.choices))

        if not response.choices:
            print("警告：模型没有返回任何 choices")
            print("======================================\n")
            return {
                "content": "",
                "finish_reason": None,
                "usage": None,
            }

        choice = response.choices[0]

        print("Finish reason：", choice.finish_reason)
        print("Message role：", choice.message.role)
        print("Message content：", repr(choice.message.content))
        print("Tool calls：", choice.message.tool_calls)

        usage = (
            response.usage.model_dump()
            if response.usage is not None
            else None
        )

        print("Token usage：", usage)
        print("======================================\n")

        return {
            "content": choice.message.content or "",
            "finish_reason": choice.finish_reason,
            "usage": usage,
        }