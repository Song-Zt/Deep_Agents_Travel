import sys
from pathlib import Path

# 将项目根目录添加到模块搜索路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio

from llm import LLMClient


async def main():
    llm = LLMClient()

    try:
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的旅行规划助手。"
            },
            {
                "role": "user",
                "content": "请用三句话介绍北京故宫。"
            }
        ]

        print("正在调用 LLM...")

        response = await llm.chat(messages)

        print("\n模型回复：")
        print(response)

        print("\nLLM 调用成功！")

    finally:
        await llm.close()


if __name__ == "__main__":
    asyncio.run(main())