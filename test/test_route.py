import asyncio
import json

from tools.route_tools import (
    plan_walking_route,
    plan_driving_route,
    plan_transit_route,
    plan_bicycling_route,
    calculate_distance
)


# 故宫博物院
FORBIDDEN_CITY = "116.397029,39.917839"

# 天坛公园
TEMPLE_OF_HEAVEN = "116.410829,39.881913"


def print_result(title, result):
    print(f"\n========== {title} ==========")

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ))


async def main():

    # 1. 步行路线
    walking = await plan_walking_route(
        origin=FORBIDDEN_CITY,
        destination=TEMPLE_OF_HEAVEN
    )

    print_result("1. 步行路线", walking)

    # 2. 驾车路线
    driving = await plan_driving_route(
        origin=FORBIDDEN_CITY,
        destination=TEMPLE_OF_HEAVEN
    )

    print_result("2. 驾车路线", driving)

    # 3. 公共交通路线
    transit = await plan_transit_route(
        origin=FORBIDDEN_CITY,
        destination=TEMPLE_OF_HEAVEN,
        city="北京",
        cityd="北京"
    )

    print_result("3. 公共交通路线", transit)

    # 4. 骑行路线
    bicycling = await plan_bicycling_route(
        origin=FORBIDDEN_CITY,
        destination=TEMPLE_OF_HEAVEN
    )

    print_result("4. 骑行路线", bicycling)

    # 5. 距离计算
    distance = await calculate_distance(
        origins=FORBIDDEN_CITY,
        destination=TEMPLE_OF_HEAVEN,
        distance_type=1
    )

    print_result("5. 驾车距离", distance)


if __name__ == "__main__":
    asyncio.run(main())