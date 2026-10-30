
import asyncio
import json

from tools.place_tools import (
    search_places,
    get_place_detail,
    geocode,
)


async def main():

    # 1. 测试景点搜索
    print("\n========== 1. 景点搜索 ==========")

    places = await search_places(
        keywords="故宫博物院",
        city="北京",
    )

    for place in places[:3]:
        print(json.dumps(
            place,
            ensure_ascii=False,
            indent=2,
        ))

    # 2. 测试景点详情
    print("\n========== 2. 景点详情 ==========")

    detail = await get_place_detail("B000A8UIN8")

    print(json.dumps(
        detail,
        ensure_ascii=False,
        indent=2,
    ))

    # 3. 测试地址转坐标
    print("\n========== 3. 地理编码 ==========")

    location = await geocode(
        address="天坛公园",
        city="北京",
    )

    print(json.dumps(
        location,
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    asyncio.run(main())
