
import asyncio
import json

from tools.amap_client import call_tool


async def main():
    print("开始搜索北京故宫博物院...\n")

    # result = await call_tool(
    #     tool_name="maps_text_search",
    #     arguments={
    #         "keywords": "故宫博物院",
    #         "city": "北京",
    #         "citylimit": True
    #     }
    # )
    result = await call_tool(
        tool_name="maps_text_search",
        arguments={
            "keywords": "天坛公园",
            "city": "北京",
            "citylimit": True
        }
    )

    print("\n========== 搜索结果 ==========")

    # 打印结构化结果（如果服务端提供）
    structured = getattr(result, "structuredContent", None)

    if structured is not None:
        print(json.dumps(
            structured,
            ensure_ascii=False,
            indent=2,
            default=str
        ))

    # 打印文本结果
    for item in result.content or []:
        if hasattr(item, "text"):
            print(item.text)


if __name__ == "__main__":
    asyncio.run(main())
