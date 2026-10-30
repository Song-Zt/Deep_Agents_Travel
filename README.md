# 旅行助手 · Deep Agents

一个面向中文用户的**旅行规划多 Agent 助手**：由总调度 Agent 理解需求并拆分任务，交给景点、路线、预算、行程审查四个业务 Agent 执行，工具层通过 **高德地图 MCP** 获取真实 POI、路线与天气数据，最终汇总成可直接使用的旅行方案。

同时提供：

- 基于 **SQLite** 的多轮会话持久化
- 带**流式输出**的 Web 对话界面
- 实时展示**工具调用过程**（工具名、参数、耗时、成功/失败）

---

## 功能特性

| 能力 | 说明 |
| --- | --- |
| 多 Agent 调度 | 自动识别 `sightseeing` / `route` / `budget` / `itinerary`，可拆分为多个子任务依次执行 |
| 景点推荐 | 多关键词搜索 + 去重 + 类型过滤 + LLM 相关性过滤 + 景区归属分组 + 营业状态检查 |
| 路线规划 | 地址/地名自动地理编码，支持步行、驾车、公交、骑行与距离计算 |
| 预算估算 | 从自然语言中抽取人数、天数、城市、档次等参数，计算并分配预算 |
| 行程审查 | 抽取行程结构，检查节奏、交通、时间安排是否合理 |
| 多轮会话 | 省略式追问（如「那上海呢？」）会被改写成独立请求后再执行 |
| 会话持久化 | SQLite 单文件存储，支持多会话列表、切换、删除；也可切换为 JSON 文件或纯内存 |
| 流式界面 | SSE 增量推送，边生成边展示；工具调用与执行阶段实时可见 |
| 并发保护 | 高德接口全局限流（并发 2）+ 指数退避重试，规避 `CUQPS_HAS_EXCEEDED_THE_LIMIT` |

---

## 系统架构

```
用户 / Web 前端
      │  SSE（stage / tool / delta / done …）
      ▼
┌──────────────────────────────────────────┐
│              SupervisorAgent             │
│   查询改写 → 意图分类 → 调度执行 → 汇总   │
└───────────────────┬──────────────────────┘
                    │
   ┌────────────────┼────────────────┬──────────────────┐
   ▼                ▼                ▼                  ▼
SightseeingAgent  RouteAgent    BudgetAgent   ItineraryReviewAgent
   └────────────────┴────────────────┴──────────────────┘
                    │  9 个工具，统一参数 / 结果 / 事件
                    ▼
          ┌───────────────────┐      MCP      ┌────────────────┐
          │     工具注册表     │ ────────────► │   高德地图 MCP  │
          └───────────────────┘  Streamable   └────────────────┘
                                    HTTP
```

### 景点推荐管线

```
关键词生成
  → 多关键词并发搜索
  → 去重
  → 非景点类型过滤（typecode 白名单 11/14 + 名称黑名单）
  → LLM 相关性过滤
  → 景区归属分组（核心景区 / 内部附属 POI / 可能独立的景区）
  → 营业 / 建设状态检查
  → 最终推荐候选列表
```

- **类型过滤**：只保留风景名胜（11）与科教文化（14）类 POI，同时按名称排除酒店、车站、票务处、寄存点、办公楼等。
- **相关性过滤**：由 LLM 判断搜索结果是否与用户需求相关，返回异常时降级为「全部保留」，避免误杀。
- **景区归属**：识别核心景区内部的附属 POI（如颐和园的德和园、后湖），把它们作为核心景区的补充信息，而不是独立推荐项。
- **状态检查**：剔除「暂停营业」「建设中」「未开放」等 POI，并在结果中记录被剔除的原因。

### 流式事件

`SupervisorAgent.run_stream()` 依次产出以下事件，Web 层原样转发为 SSE：

| 事件 | 含义 |
| --- | --- |
| `session` | 本次对话所属会话 ID |
| `stage` | 当前阶段（改写 / 分类 / 子任务 / 汇总） |
| `rewritten` | 省略式追问被改写后的独立请求 |
| `classified` | 任务类型、子任务与判断理由 |
| `tool` | 工具调用开始 / 结束（参数、耗时、结果摘要） |
| `subtask_done` | 某个子 Agent 执行完成 |
| `delta` | 最终回答的增量文本 |
| `done` | 完整结果（含分类、子任务输出、最终回答） |
| `error` | 执行异常 |

---

## 快速开始

### 1. 环境要求

- Python **3.12+**
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- 一个兼容 OpenAI 协议的模型服务（DeepSeek / Qwen 等）
- 高德开放平台的 **Web 服务 Key**

### 2. 安装

```bash
git clone https://github.com/Song-Zt/Deep_Agents_Travel.git
cd Deep_Agents_Travel

# 方式一：uv（推荐）
uv sync

# 方式二：pip（依赖版本已在 requirements.txt 中锁定）
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> `requirements.txt` 由 `uv export` 从 `uv.lock` 生成，包含全部间接依赖及固定版本；
> 修改依赖后请用 `uv add` / `uv remove` 并重新导出，避免两份清单不一致。

### 3. 配置 `.env`

在项目根目录创建 `.env`：

```dotenv
# 模型服务（兼容 OpenAI 协议）
OPENAI_API_KEY=sk-xxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
MODEL=deepseek-chat

# 高德地图 Web 服务 Key
AMAP_API_KEY=xxxxxxxxxxxxxxxx

# 可选：Web 服务配置
# WEB_HOST=127.0.0.1
# WEB_PORT=8000
# CONVERSATION_DB=agent_files/conversations.db
```

### 4. 启动 Web 界面

```bash
uv run python -m web
# 或者
.venv/Scripts/python.exe -m web      # Windows
.venv/bin/python -m web              # macOS / Linux
```

打开 <http://127.0.0.1:8000> 即可对话。前端为原生 HTML / CSS / JS，无构建步骤。

页面左侧是会话列表（新建 / 切换 / 删除），右侧是对话区：

- 回答逐字流式显示
- 每条回答上方的「执行过程」面板会实时记录查询改写、任务类型、每次工具调用的参数与耗时
- 顶部状态标签显示当前阶段，出错时显示具体原因

### 5. 命令行体验

```bash
# 多轮会话（会真实调用模型与高德接口）
uv run python test/run_conversation_integration.py

# 其他集成脚本
uv run python test/run_sightseeing_integration.py
uv run python test/run_route_integration.py
uv run python test/run_supervisor_integration.py
```

---

## 代码中使用

### 同步调用

```python
import asyncio

from conversation import ConversationManager, ConversationRunner
from tools.amap_client import close_mcp


async def main():
    manager = ConversationManager(
        database_path="agent_files/conversations.db",  # 不传则仅内存
    )
    runner = ConversationRunner(manager=manager, session_id="demo")

    result = await runner.chat("推荐几个北京经典景点，简单一点就好")
    print(result["answer"])

    await runner.close()
    await close_mcp()


asyncio.run(main())
```

### 流式调用

在同一个 `runner` 上继续流式对话即可（需在 `async` 函数内）：

```python
async for event in runner.chat_stream("那上海呢？"):
    if event["event"] == "delta":
        print(event["data"]["text"], end="", flush=True)
    elif event["event"] == "tool":
        print(f"\n[tool] {event['data']}")
```

---

## Web API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | 对话页面 |
| `GET` | `/static/*` | 前端静态资源 |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/sessions` | 会话列表（标题、消息数、更新时间） |
| `POST` | `/api/sessions` | 新建会话 |
| `GET` | `/api/sessions/{session_id}` | 会话详情与全部消息 |
| `DELETE` | `/api/sessions/{session_id}` | 删除会话 |
| `POST` | `/api/chat` | 发送消息，返回 `text/event-stream` |

请求示例：

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "demo", "message": "从故宫到天坛怎么走"}'
```

> `session_id` 省略时会自动创建新会话，并通过首个 `session` 事件返回。

---

## 工具列表

工具通过 [tools/registry.py](tools/registry.py) 注册，参数 Schema 由函数签名自动生成。

| 工具 | 作用 |
| --- | --- |
| `search_places` | 按关键词和城市搜索地点 |
| `get_place_detail` | 按 POI ID 查询地点详情 |
| `geocode` | 地址 / 地名转经纬度 |
| `plan_walking_route` | 步行路线 |
| `plan_driving_route` | 驾车路线 |
| `plan_transit_route` | 公共交通路线 |
| `plan_bicycling_route` | 骑行路线 |
| `calculate_distance` | 多点距离计算 |
| `get_weather` | 城市天气预报 |

---

## 目录结构

```
Deep_Agents/
├── agents/
│   ├── base_agent.py              # Agent 基类（LLM 客户端、关闭逻辑）
│   ├── supervisor_agent.py        # 总调度：改写、分类、执行、汇总、流式
│   └── sub_agents/
│       ├── sightseeing_agent.py   # 景点推荐与多层过滤管线
│       ├── route_agent.py         # 路线规划
│       ├── budget_agent.py        # 预算估算
│       └── itinerary_review_agent.py
├── tools/
│   ├── amap_client.py             # 高德 MCP 客户端（限流、重试、生命周期）
│   ├── registry.py                # 工具注册表、Schema 生成、事件埋点
│   ├── place_tools.py             # 地点搜索 / 详情 / 地理编码
│   ├── route_tools.py             # 各类路线与距离
│   ├── weather_tools.py           # 天气
│   └── events.py                  # ContextVar 工具事件广播
├── llm/
│   ├── client.py                  # 异步 LLM 客户端（含流式）
│   └── config.py                  # 环境变量配置
├── conversation/
│   ├── session.py                 # 会话与消息模型
│   ├── storage.py                 # SQLite / JSON 存储后端
│   └── conversation_manager.py    # 会话管理与 Runner（含流式）
├── web/
│   ├── app.py                     # Starlette 服务与 SSE 接口
│   ├── __main__.py                # python -m web 启动入口
│   └── static/                    # 前端页面（原生 HTML / CSS / JS）
├── test/                          # 单元测试 + 真实接口集成脚本
├── skills/                        # 技能说明（代码审查、旅行规划）
├── agent_files/                   # 运行时生成：会话数据库等
├── pyproject.toml                 # 项目配置与直接依赖
├── uv.lock                        # uv 锁定的完整依赖版本
└── requirements.txt               # 由 uv export 生成，供 pip 使用
```

> 仓库中的 `基础、/` 目录为 Python 基础语法练习脚本，与主程序无关，可忽略或自行删除。

---

## 测试

```bash
uv run pytest test -q
```

- 绝大多数用例通过打桩运行，不访问网络，覆盖 Agent 分类、工具注册、结果过滤、会话存储、流式事件、Web 接口等。
- 少数用例会真实调用外部服务：`test/test_weather.py::test_real_weather` 需要 `AMAP_API_KEY`。
- `test/run_*.py` 与 `test/test_amap.py`、`test/test_place.py` 等是手动脚本（pytest 不会收集到用例），运行前请先配置 `.env`。

### 已知问题

- `test/test_llm_metadata.py::test_chat_with_metadata` 使用伪造的 `SimpleNamespace` 响应，缺少 `response.model` 字段，当前会失败，属于测试桩与真实响应结构不一致，需要修正测试用例。
- 高德接口存在 QPS 限制。客户端已做全局并发 2 与退避重试，极端情况下仍可能出现单次调用失败。
- Web 端同一时间只执行一个对话（全局锁），避免共享客户端被并发请求压垮。

---

## 开发约定

- 所有对外函数使用中文文档字符串，注释解释「为什么」而非「做什么」。
- 工具统一返回 `{"success": bool, "data": ..., "error": ...}` 结构。
- LLM 结构化输出必须校验后再使用；校验失败时降级而不是直接崩溃。
- 提示词与解析逻辑分离，解析失败抛出可读的中文异常。
