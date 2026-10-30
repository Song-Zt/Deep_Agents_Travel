
import asyncio
import sys
from pathlib import Path

# 将项目根目录加入 Python 模块搜索路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conversation import ConversationManager, ConversationRunner
from tools.amap_client import close_mcp


# 多轮对话脚本：第二轮和第三轮都依赖前文才能理解
TURNS = [
    "推荐几个北京经典景点，简单一点就好。",
    "那上海呢？",
    "从故宫到天坛怎么走？",
]


async def main():
    runner = None

    try:
        manager = ConversationManager()

        runner = ConversationRunner(
            manager=manager,
            session_id="demo",
        )

        for index, user_input in enumerate(TURNS, 1):
            print(f"\n========== 第 {index} 轮 ==========")
            print(f"用户：{user_input}")

            result = await runner.chat(user_input)

            print(f"改写后请求：{result.get('resolved_input')}")
            print(f"任务类型：{result.get('task_type')}")
            print(f"回答：\n{result.get('answer')}")
            print(f"当前历史条数：{len(runner.session.turns)}")

        print("\n========== 会话历史 ==========")

        for turn in runner.session.turns:
            print(f"[{turn.role}] {turn.content[:80]}")

    finally:
        if runner is not None:
            await runner.close()

        await close_mcp()


if __name__ == "__main__":
    asyncio.run(main())
