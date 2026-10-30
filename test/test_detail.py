
import asyncio
import json

from tools.amap_client import call_tool


async def main():

    print("开始查询故宫博物院详情...\n")

    result = await call_tool(
        tool_name="maps_search_detail",
        arguments={
            "id": "B000A8UIN8"
        }
    )

    print("\n========== 故宫详情 ==========")

    for item in result.content or []:
        if hasattr(item, "text"):
            try:
                data = json.loads(item.text)

                print(json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                ))

                # 尝试提取 POI 信息
                pois = data.get("pois", [])

                for poi in pois:
                    print("\n景点名称：", poi.get("name"))
                    print("POI ID：", poi.get("id"))
                    print("地址：", poi.get("address"))
                    print("坐标：", poi.get("location"))

            except json.JSONDecodeError:
                print(item.text)


if __name__ == "__main__":
    asyncio.run(main())
