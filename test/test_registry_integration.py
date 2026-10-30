import asyncio
import sys
from pathlib import Path

# 获取项目根目录：D:\python\Deep_Agents
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 将项目根目录加入 Python 模块搜索路径
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from tools.registry import (
    get_registered_tools,
    execute_tool,
    get_tool_schemas,
)
from tools.amap_client import connect_mcp, close_mcp


async def main():
    try:
        # 1. 建立 MCP 连接
        await connect_mcp()
        print("高德 MCP 连接成功！")

        # 2. 检查注册工具
        print("已注册工具：", get_registered_tools())

        # 3. 检查 Schema
        print("Schema 数量：", len(get_tool_schemas()))

        # 4. 调用工具
        result = await execute_tool(
            "search_places",
            {
                "keywords": "故宫",
                "city": "北京",
            },
        )

        print("\n工具调用结果：")
        print(result)

    finally:
        # 5. 在同一个异步任务中关闭连接
        await close_mcp()
        print("\n高德 MCP 已关闭")


if __name__ == "__main__":
    asyncio.run(main())