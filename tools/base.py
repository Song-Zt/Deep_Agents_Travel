
from typing import Any


def success_result(tool: str, data: Any) -> dict:
    """统一成功返回格式"""
    return {
        "success": True,
        "tool": tool,
        "data": data,
        "error": None
    }


def error_result(tool: str, error: Exception) -> dict:
    """统一失败返回格式"""
    return {
        "success": False,
        "tool": tool,
        "data": None,
        "error": {
            "type": type(error).__name__,
            "message": str(error)
        }
    }
