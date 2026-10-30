
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents import SupervisorAgent
from tools.amap_client import connect_mcp, close_mcp


async def main():
    supervisor = None
    mcp_connected = False

    try:
        print("=" * 60)
        print("旅行助手 Multi-Agent 真实联调")
        print("=" * 60)

        # 第一步：连接高德 MCP
        print("\n[1/5] 正在连接高德 MCP...")

        await connect_mcp()
        mcp_connected = True

        print("高德 MCP 连接成功")

        # 第二步：创建 Supervisor
        print("\n[2/5] 正在初始化 SupervisorAgent...")

        supervisor = SupervisorAgent()

        print("SupervisorAgent 初始化成功")

        # 第三步：输入旅行需求
        user_input = (
            "我计划去北京旅游两天，有两个人。"
            "请推荐几个经典旅游景点，"
            "帮我规划故宫到天坛的交通路线，"
            "并且估算一下这次旅行的总预算。"
        )

        print("\n[3/5] 用户需求：")
        print(user_input)

        # 第四步：执行完整工作流
        print("\n[4/5] 正在执行旅行助手任务...")

        result = await supervisor.run(user_input)

        print("\n任务执行完成")

        # 第五步：输出结果
        print("\n[5/5] 执行结果")
        print("=" * 60)

        print("\n任务类型：")
        print(result.get("task_type"))

        print("\n任务分类：")
        print(
            json.dumps(
                result.get("classification"),
                ensure_ascii=False,
                indent=2,
            )
        )

        print("\n各子 Agent 执行结果：")

        for index, item in enumerate(
            result.get("execution_results", []),
            start=1,
        ):
            print(f"\n子任务 {index}")
            print("任务类型：", item.get("task"))
            print("执行状态：", item.get("success"))

            if item.get("error"):
                print("错误：", item.get("error"))

            if item.get("answer"):
                print("业务结果：", item.get("answer"))

        print("\n最终旅行方案：")
        print("=" * 60)
        print(result.get("answer"))

        print("\n整体执行状态：", result.get("success"))

        if result.get("error"):
            print("汇总错误：", result["error"])

    except Exception as exc:
        print("\n联调发生异常：")
        print(type(exc).__name__, str(exc))

        raise

    finally:
        print("\n正在释放资源...")

        if supervisor is not None:
            await supervisor.close()

        if mcp_connected:
            await close_mcp()

        print("资源释放完成")


if __name__ == "__main__":
    asyncio.run(main())
