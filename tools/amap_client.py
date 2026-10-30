
import asyncio
import json
import os
from contextlib import AsyncExitStack
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

load_dotenv()


def get_mcp_url() -> str:
    """获取高德官方 MCP 地址。"""
    api_key = os.getenv("AMAP_API_KEY", "").strip()

    if not api_key:
        raise ValueError("请在 .env 中配置 AMAP_API_KEY")

    return f"https://mcp.amap.com/mcp?key={api_key}"


# 高德 Web 服务免费配额对并发 QPS 有限制，多个 Agent 并发查询时容易触发
# CUQPS_HAS_EXCEEDED_THE_LIMIT。这里统一限流，并对限流错误做退避重试。
MAX_CONCURRENT_CALLS = 2
MAX_CALL_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.8

# 只有这类错误才值得重试，配额耗尽、参数错误重试没用
RETRYABLE_ERROR_MARKERS = (
    "CUQPS",
    "QPS_HAS_EXCEEDED",
    "TIMEOUT",
)


class AmapMCPClient:
    """
    高德 MCP 客户端。

    负责：
    1. 建立和关闭 MCP 连接
    2. 初始化 MCP Session
    3. 缓存 MCP 工具列表
    4. 复用 Session 调用多个工具
    5. 限制并发并重试限流错误
    """

    def __init__(self):
        self._session: ClientSession | None = None

        self._tools: dict[str, Any] = {}

        # 防止多个协程同时重复初始化连接
        self._connect_lock = asyncio.Lock()

        # 持有 MCP 连接生命周期的常驻任务
        self._owner_task: asyncio.Task | None = None
        self._ready: asyncio.Event | None = None
        self._stop_event: asyncio.Event | None = None
        self._startup_error: BaseException | None = None

        # 调用限流，按事件循环惰性创建
        self._call_semaphore: asyncio.Semaphore | None = None
        self._semaphore_loop: asyncio.AbstractEventLoop | None = None

    async def connect(self):
        """建立 MCP 连接并初始化 Session。"""

        async with self._connect_lock:
            # 已经连接，不重复初始化
            if self._session is not None:
                return

            loop = asyncio.get_running_loop()

            self._ready = asyncio.Event()
            self._stop_event = asyncio.Event()
            self._startup_error = None

            # MCP 的 AsyncExitStack 必须在创建它的同一个任务中关闭，
            # 因此连接由一个常驻任务持有，其他协程只发起调用。
            self._owner_task = loop.create_task(
                self._serve_session()
            )

            await self._ready.wait()

            if self._startup_error is not None:
                error = self._startup_error
                await self._shutdown_owner()
                raise error

    async def _serve_session(self):
        """在常驻任务中持有 MCP 连接，直到收到关闭信号。"""

        try:
            async with AsyncExitStack() as exit_stack:
                url = get_mcp_url()

                # 建立 Streamable HTTP 连接
                streams = await exit_stack.enter_async_context(
                    streamable_http_client(url)
                )

                read_stream, write_stream = streams[0], streams[1]

                # 初始化 MCP Session
                session = await exit_stack.enter_async_context(
                    ClientSession(
                        read_stream,
                        write_stream
                    )
                )

                await session.initialize()

                # 获取并缓存工具列表
                result = await session.list_tools()

                self._tools = {
                    tool.name: tool
                    for tool in result.tools
                }

                self._session = session
                self._ready.set()

                print("高德 MCP 连接成功！")
                print(f"已加载工具数量：{len(self._tools)}")

                await self._stop_event.wait()

        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                self._startup_error = RuntimeError("MCP 连接任务被取消")
            else:
                self._startup_error = exc

            if self._ready is not None:
                self._ready.set()

            raise

        finally:
            self._session = None
            self._tools = {}

    async def list_tools(self) -> list:
        """获取已缓存的 MCP 工具列表。"""

        await self.connect()

        return list(self._tools.values())

    @staticmethod
    def _format_error_detail(result) -> str:
        """提取 MCP 工具返回的错误详情，便于定位问题。"""

        detail = "".join(
            item.text
            for item in (result.content or [])
            if getattr(item, "text", "")
        ).strip()

        if not detail and getattr(result, "structured_content", None):
            detail = json.dumps(
                result.structured_content,
                ensure_ascii=False,
                default=str
            )

        return detail

    def _get_call_semaphore(self) -> asyncio.Semaphore:
        """获取当前事件循环下的调用信号量。"""

        loop = asyncio.get_running_loop()

        if self._call_semaphore is None or self._semaphore_loop is not loop:
            self._call_semaphore = asyncio.Semaphore(
                MAX_CONCURRENT_CALLS
            )
            self._semaphore_loop = loop

        return self._call_semaphore

    @staticmethod
    def _is_retryable(detail: str) -> bool:
        """判断错误是否值得重试。"""

        detail = (detail or "").upper()

        return any(
            marker in detail
            for marker in RETRYABLE_ERROR_MARKERS
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict
    ):
        """调用指定的 MCP 工具。"""

        await self.connect()

        if tool_name not in self._tools:
            raise ValueError(
                f"不存在该 MCP 工具：{tool_name}"
            )

        if self._session is None:
            raise RuntimeError("MCP Session 尚未初始化")

        session = self._session

        detail = ""
        result = None

        async with self._get_call_semaphore():
            for attempt in range(1, MAX_CALL_ATTEMPTS + 1):
                result = await session.call_tool(
                    tool_name,
                    arguments
                )

                if not result.is_error:
                    return result

                detail = self._format_error_detail(result)

                if (
                    attempt < MAX_CALL_ATTEMPTS
                    and self._is_retryable(detail)
                ):
                    await asyncio.sleep(
                        RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    )
                    continue

                break

        params = json.dumps(
            arguments,
            ensure_ascii=False,
            default=str
        )

        message = f"MCP 工具调用失败：{tool_name}，参数：{params}"

        if detail:
            message += f"，服务端返回：{detail}"

        raise RuntimeError(message)

    async def _shutdown_owner(self):
        """通知常驻任务退出并等待其释放连接。"""

        task = self._owner_task
        stop_event = self._stop_event

        self._owner_task = None
        self._stop_event = None
        self._ready = None
        self._session = None
        self._tools = {}

        if task is None:
            return

        if stop_event is not None:
            stop_event.set()

        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            task.cancel()
        except asyncio.CancelledError:
            # 常驻任务自身被取消属于正常关闭；当前任务被取消则继续抛出
            if not task.cancelled():
                raise
        except Exception:
            # 启动失败时异常已经在 connect() 中抛出
            pass

    async def close(self):
        """关闭 MCP 连接并释放资源。"""

        async with self._connect_lock:
            await self._shutdown_owner()

            print("高德 MCP 连接已关闭")

    async def __aenter__(self):
        """支持 async with 使用方式。"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """退出上下文时自动关闭连接。"""
        await self.close()


# 创建全局 MCP 客户端实例
amap_client = AmapMCPClient()


async def connect_mcp():
    """初始化全局 MCP 客户端。"""
    await amap_client.connect()


async def close_mcp():
    """关闭全局 MCP 客户端。"""
    await amap_client.close()


async def list_tools():
    """获取高德 MCP 工具列表并打印。"""

    tools = await amap_client.list_tools()

    print("\n高德 MCP 可用工具")
    print("=" * 60)

    for index, tool in enumerate(tools, 1):
        print(f"\n{index}. 工具名称：{tool.name}")
        print(f"描述：{tool.description or '暂无描述'}")

        print("参数 Schema：")
        print(
            json.dumps(
                tool.input_schema,
                ensure_ascii=False,
                indent=2,
                default=str
            )
        )

    return tools


async def call_tool(
    tool_name: str,
    arguments: dict
):
    """
    统一调用高德 MCP 工具。

    兼容原有业务工具层的调用方式。
    """
    return await amap_client.call_tool(
        tool_name,
        arguments
    )


if __name__ == "__main__":

    async def main():
        try:
            await list_tools()

        except Exception as exc:
            print(f"\n程序发生异常：{exc}")

        finally:
            await close_mcp()

    asyncio.run(main())
