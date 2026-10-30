
import asyncio
import json
import sys
from pathlib import Path

# 将项目根目录加入 Python 模块搜索路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from agents.sub_agents import SightseeingAgent
from tools.amap_client import connect_mcp, close_mcp


async def main():
    agent = None

    try:
        # 1. 连接高德 MCP
        print("\n========== 连接高德 MCP ==========")
        await connect_mcp()
        print("高德 MCP 连接成功！")

        # 2. 创建景点推荐 Agent
        agent = SightseeingAgent()

        # 3. 输入旅行需求
        user_input = "推荐几个北京值得去的旅游景点，最好包含经典文化景点。"

        print("\n========== 用户需求 ==========")
        print(user_input)

        # 4. 执行景点推荐
        print("\n========== 开始执行景点推荐 ==========")
        result = await agent.recommend(user_input)

        # 5. 展示结果
        print("\n========== 景点推荐结果 ==========")
        print("执行状态：", result["success"])
        print("任务类型：", result["task"])
        print("搜索参数：")
        print(json.dumps(
            result["search_params"],
            ensure_ascii=False,
            indent=2,
        ))

        print("\n高德返回的 POI 数量：", len(result["places"]))

        print("\n高德返回的 POI 数据：")
        print(json.dumps(
            result["places"],
            ensure_ascii=False,
            indent=2,
        ))

        rejected = result.get("rejected_places") or []

        print("\n被剔除的景点：", len(rejected))
        print(json.dumps(
            rejected,
            ensure_ascii=False,
            indent=2,
        ))

        print("\nLLM 生成的推荐内容：")
        print(result["answer"])

        if not result["success"]:
            print("\n景点推荐执行失败：")
            print(result["error"])

    except Exception as exc:
        print("\n联调过程中发生异常：")
        print(type(exc).__name__, str(exc))
        raise

    finally:
        # 6. 按照资源生命周期关闭客户端
        if agent is not None:
            await agent.close()

        await close_mcp()
        print("\n高德 MCP 已关闭。")


if __name__ == "__main__":
    asyncio.run(main())
