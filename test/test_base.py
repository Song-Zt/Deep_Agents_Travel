
from tools.base import success_result, error_result


def test_success_result():
    result = success_result(
        "search_places",
        [{"name": "故宫博物院"}]
    )

    assert result["success"] is True
    assert result["tool"] == "search_places"
    assert result["data"][0]["name"] == "故宫博物院"
    assert result["error"] is None


def test_error_result():
    error = ValueError("搜索关键词不能为空")

    result = error_result("search_places", error)

    assert result["success"] is False
    assert result["tool"] == "search_places"
    assert result["data"] is None
    assert result["error"]["type"] == "ValueError"
    assert result["error"]["message"] == "搜索关键词不能为空"



