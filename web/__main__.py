"""启动 Web 服务：python -m web"""

import os
import sys

import uvicorn


def main():
    # Windows 控制台默认 GBK，中文日志容易乱码
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    host = os.getenv("WEB_HOST", "127.0.0.1")
    port = int(os.getenv("WEB_PORT", "8000"))

    print(f"旅行助手已启动：http://{host}:{port}")

    uvicorn.run(
        "web.app:app",
        host=host,
        port=port,
        reload=os.getenv("WEB_RELOAD", "0") == "1",
    )


if __name__ == "__main__":
    main()
