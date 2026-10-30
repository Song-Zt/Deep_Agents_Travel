
import sys
import asyncio
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.amap_client import connect_mcp, close_mcp
from agents.sub_agents import RouteAgent



async def main():
    agent = None

    test_cases = [
        ("步行", "从北京故宫步行到天坛"),
        ("驾车", "从北京故宫开车到天坛"),
        ("公交", "从北京站乘坐公共交通到颐和园"),
        ("骑行", "从北京故宫骑自行车到天坛"),
        ("距离", "计算北京故宫到天坛的距离"),
    ]

    try:
        print("正在连接高德 MCP...")
        await connect_mcp()
        print("高德 MCP 连接成功！")

        agent = RouteAgent()

        for name, user_input in test_cases:
            print(f"\n{'=' * 20} 测试{name}路线 {'=' * 20}")
            print(f"用户输入：{user_input}")

            try:
                result = await agent.plan_route(user_input)

                print(json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2
                ))

                if result.get("success"):
                    print(f"\n{name}路线测试成功！")
                else:
                    print(f"\n{name}路线测试失败：{result.get('error')}")

            except Exception as exc:
                print(
                    f"\n{name}路线发生异常："
                    f"{type(exc).__name__}: {exc}"
                )

    except Exception as exc:
        print(
            f"\n联调发生异常："
            f"{type(exc).__name__}: {exc}"
        )

    finally:
        if agent is not None:
            await agent.close()

        await close_mcp()
        print("\n高德 MCP 资源已关闭。")


if __name__ == "__main__":
    asyncio.run(main())



if __name__ == "__main__":
    asyncio.run(main())
