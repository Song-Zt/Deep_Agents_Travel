---
name: travel-planner
name_en: Travel Planner
name_zh: 旅行行程规划
description: Generate complete day-by-day travel itineraries from natural language trip requirements (origin, destination, days, budget, dining budget, travel mode, daily drive limit). Researches attractions, food, lodging and transport in parallel, collects ticket prices and booking rules, builds geo-optimized hourly timelines, recommends real restaurants within dining budget with backups, obtains one local photo per attraction (web images downloaded first, modest-size AI generation as fallback), renders each day under a compact pure-CSS gradient banner showing local weather (right side) and the day theme, annotates every leg with distance/mode/duration and Baidu map navigation links, adds a one-click Export-PDF button (print-optimized CSS), and outputs a polished HTML guide. Self-drive mode adds a route overview map (Leaflet + Amap tiles), fuel and toll estimates, and daily driving-time limits. Use when the user asks for travel planning, itinerary, trip guide, 旅行攻略, 行程规划, 自驾游规划, or 出行安排.
description_en: Generate complete day-by-day travel itineraries from natural language trip requirements (origin, destination, days, budget, dining budget, travel mode, daily drive limit). Researches attractions, food, lodging and transport in parallel, collects ticket prices and booking rules, builds geo-optimized hourly timelines, recommends real restaurants within dining budget with backups, obtains one local photo per attraction (web images downloaded first, modest-size AI generation as fallback), renders each day under a compact pure-CSS gradient banner showing local weather (right side) and the day theme, annotates every leg with distance/mode/duration and Baidu map navigation links, adds a one-click Export-PDF button (print-optimized CSS), and outputs a polished HTML guide. Self-drive mode adds a route overview map (Leaflet + Amap tiles), fuel and toll estimates, and daily driving-time limits. Use when the user asks for travel planning, itinerary, trip guide, 旅行攻略, 行程规划, 自驾游规划, or 出行安排.
description_zh: 根据自然语言旅行需求（出发地、目的地、天数、预算、餐饮预算、出行方式、每日驾驶上限）自动生成逐日行程攻略。并行调研景点、美食、住宿、交通信息，查询门票价格与预约规则，按地理位置就近编排精确到小时的逐日时间轴，在餐饮预算内推荐真实餐馆（含备选店），为每个景点获取一张本地照片（优先下载网图，无网图才 AI 生成小尺寸兜底图），每日行程以低高度纯 CSS 渐变横幅展示天气（右侧）与当日主题，每段路程标注距离、出行方式、预计时间并附百度地图导航链接，内置一键导出 PDF 按钮（打印优化样式），自驾模式含 Leaflet + 高德瓦片路线总览地图、油费过路费估算与每日驾驶时长限制。用户提到旅行攻略、行程规划、自驾游规划、出行安排时使用。
argument-hint: Describe the trip - origin, destination, days, budget, dining budget, travel mode (self-drive or public transit), travelers, and preferences
argument-hint-en: Describe the trip - origin, destination, days, budget, dining budget, travel mode (self-drive or public transit), travelers, and preferences
argument-hint-zh: 描述旅行需求——出发地、目的地、天数、总预算、餐饮预算、出行方式（自驾或公共交通）、人数及偏好
user-invocable: true
---

# 旅行行程规划（Travel Planner）

## 引用文件与必读规则

本文件只保留**红线、总览与每步核心规则**；专项细则外置到 docs/，**对应步骤执行前必须 Read 引用文件，禁止凭记忆跳过**：

| 文件                                     | 内容                                                                      | 何时必读                                            |
| ---------------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------- |
| [docs/operations.md](docs/operations.md) | 超时与重试策略、批次策略、性能预算、模式 B 离线规则                       | Step 2 / Step 3 / Step 4b 执行前                    |
| [docs/self-drive.md](docs/self-drive.md) | 自驾专项：驾驶上限、中途城市、油费过路费、路线图                          | `travel_mode=self-drive` 时，Step 1 / Step 4 执行前 |
| [docs/dining.md](docs/dining.md)         | 餐饮预算口径换算、选店与备选店规则                                        | Step 5 执行前                                       |
| [HTML_TEMPLATE.md](HTML_TEMPLATE.md)     | **HTML 组装唯一模板**（十大板块完整骨架 + CSS + 占位符对照表 + 其他规则） | Step 7 执行前                                       |
| [README.md](README.md)                   | 使用说明、itinerary.json Schema、武汉→威海完整示例                        | 需要查 Schema 字段时                                |

## 硬性质量红线（MANDATORY，违反任何一条不得交付）

1. **导航零缺失**：每两个相邻地点之间（酒店→景点→餐馆→下一景点→…→酒店）都必须有距离、出行方式、预计耗时、百度地图导航链接，**一段都不能少**。
2. **景点照片零缺失（硬约束，缺图不得交付），来源网图直链优先**：每个景点一张照片（`attractions[].image`），一个都不能少。**来源优先级：① 网图直链——从搜索/景点页面提取真实实景图 URL 直接引用（零下载、零生成成本，优先用，不考虑离线场景）；② 无可用网图（无直链/访问失败）才 AI 生成兜底，规格「大小合适、清晰即可」（4:3、短边 ≤512px，不用高清，减少 token 与耗时），直链或落盘均可**。**选图硬标准：必须与景点实际相符（地标特征可辨认），禁止选用明显过度精修/广告渲染图（一眼 P 图、过饱和、仙境感）——优先真实游记实拍、Wikimedia Commons、官方实景照；拿不准宁走 AI 兜底**。重试策略见 [docs/operations.md](docs/operations.md)。缺图一律 validate ERROR——禁止用渐变/占位图代替，禁止不获取就交付；网图与生图均不可用时向用户明确说明并阻塞等待（或由用户提供照片）。onerror 降级仅作为直链失效的兜底防线。
3. **封面与日横幅不用图片（纯 CSS 渐变 + 固定高度）**：封面桌面端高 240px（移动端媒体查询自适应 320px）、每日横幅高 110px，均为模板内置的 CSS 渐变背景（禁止生成/引用任何封面、横幅图片，禁止加高）；横幅右侧玻璃实时天气栏由模板内置。**图片只产景点实景图**（红线 2），产出压力最小化。
4. **门票零缺失**：每个景区都有门票信息——确切价格、或「免费」、或「需人工核实」三选一，**禁止留空，禁止编造价格**；隐藏消费（`ticket.extra_fees`）与好玩点（`highlights`）同样禁止留空。
5. **餐馆预算硬约束**：所有推荐餐馆（含备选店）人均价格 ≤ 人均预算上限（换算公式见 [docs/dining.md](docs/dining.md)），**超了必须换店，不得例外**。
6. **图片引用规则**：HTML 中景点图可直接引用**稳定可访问的在线直链**（优先 Wikimedia Commons / 官方站点等长期图源，无需下载落盘、不考虑离线场景）或本地 `images/` 文件（AI 兜底图落盘时）；**避免明显易失效的临时 URL**；每张图挂 onerror 降级（骨架内置）。
7. Step 6.5 预组装校验**必须全部通过**才能进入 HTML 组装；未通过最多修复 2 轮，仍不通过时：**缺图（红线 2）与导航缺失（红线 1）不得交付，必须继续修复**；其余 ERROR/WARNING（含经用户问询确认的驾驶超限）须在交付说明中逐项列明后方可交付。
8. **每日驾驶 ≤5 小时（硬上限，超限必须先问用户）**：任一天全部 drive 路段 `duration_min` 合计 ≤300 分钟（约 450km）；超限时**禁止擅自改方案，也禁止擅自超限**——必须用 AskUserQuestion 给用户四个选项：① 增加行程天数；② 插入中途停留城市拆分长途；③ 改公共交通（或高铁 + 当地租车）；④ 用户在明知疲劳驾驶风险的前提下坚持超限。仅当用户明确选 ④ 才允许超限：记录 `brief.drive_over_limit_confirmed=true`，HTML 贴士加显著疲劳驾驶警示，validate 降为 WARNING。
9. **住宿数据零缺失 + 酒店进时间轴**：`itinerary.json` 的 `lodging[]` 必须覆盖每一晚住宿（末日返程无过夜除外），每条含 day / city / area / hotel / est_price / **reason（为什么推荐一句话）** / **backup（备选酒店：name + est_price + 替补理由）**；HTML「住宿汇总」板块逐晚列明晚次 / 城市 / 商圈 / 参考酒店 / 预估价并给出合计；**同时，每个入住日的时间轴内必须有一条酒店入住条目**（type=`hotel`）：酒店名 + **每晚价格** + **推荐理由** + **备选酒店（名称/价格/理由）** + 距上一地点导航，缺一不可。
10. **每日作息时间窗（硬约束 + 特批问询）**：每天时间轴**首条活动开始不得早于 07:30**（起床不早于 7 点半，早餐/出发均从 07:30 起排），**末条活动结束不得晚于 23:00**（夜景/夜市可以安排晚一些，但一律 23:00 前收尾回酒店）。**例外问询**：若编排中发现早于 07:30 出发有**可核实的实质收益**（如抢景区头批入园避排队、限行时段前进入、赶上首批索道/日出等），**禁止擅自早排，也禁止默默放弃**——必须用 AskUserQuestion 问用户二选一：① 特批当天早起（记录 `brief.early_start_confirmed_days=[该日]`，仅列入的天生效，validate 降 WARNING，HTML 该日注明「已确认早起」）；② 保持 07:30 起床（接受人流/排队代价，行程顺延）。未问询不得交付。

## 运行模式

开始前判定模式，默认 **模式 A（AI 全自动，推荐）**，工具不可用时降级到 **模式 B（本地脚本离线 fallback）**：

| 模式            | 触发条件                | 信息来源                                           | 图片来源                                                                                          |
| --------------- | ----------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| A：AI 全自动    | WebSearch 和联网可用    | 实时网络搜索（Step 2/3/5 的搜索模板照常执行）      | **网图直链优先（真实实景）+ AI 生成小尺寸兜底**（Step 4b）                                        |
| B：本地脚本离线 | 无网络 / 搜索工具不可用 | 模型内置知识，所有无法核实的数据标注「需人工核实」 | AI 生成兜底或用户提供的照片；**两者均不可用时，景点图缺图即 ERROR，不得交付、禁止渐变占位图代替** |

模式 B 的距离估算与补充规则见 [docs/operations.md](docs/operations.md)。

## 输出位置（权限友好，必须遵守，实测教训）

行程产物文件夹（`itinerary.json`、`images/`、`route_map.html`、攻略 HTML）**默认创建在当前工作区目录下**（`{工作区}/{行程名}/`），**不要放在桌面（Desktop）、用户主目录等位置**——AI 终端的沙箱白名单通常只放行工作区，向桌面写入/覆盖文件会被「访问被拒绝」拦截，反复报错浪费时间。

- **优先用专用文件工具（Write/Edit）写文本文件**；仅当 AI 兜底图需要落盘时才用 Python `urllib.request` 直写工作区路径（PowerShell 的 `Copy-Item`/`Invoke-WebRequest -OutFile` 更易被沙箱拦截，避免依赖）
- **禁止覆盖已存在文件**：落盘前先确认目标不存在（或先删除旧文件），沙箱常对「覆盖」单独拦截
- 用户明确要求桌面等其他位置时：先在工作区生成完毕，再告知用户自行移动，或请用户把该路径加入 Trae 沙箱白名单（设置 → 会话 → 自定义沙箱配置），**不要反复重试被拦的写入**

## 输入参数

| 参数                             | 必填                           | 默认值                     | 说明                                                                                                                                                                                          |
| -------------------------------- | ------------------------------ | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `origin` 出发地                  | 是                             | 无，必问                   | 自驾模式下决定路线起点和油费里程                                                                                                                                                              |
| `destination` 目的地             | 是                             | 无，必问                   |                                                                                                                                                                                               |
| `days` 天数                      | 是                             | 无，必问                   |                                                                                                                                                                                               |
| `budget` 总预算                  | 是                             | 无，必问                   | 只给总额时按 住宿 35% / 餐饮 30% / 门票 25% / 交通 10% 拆分（餐饮部分以 `dining_budget` 为准，若用户提供则覆盖）                                                                              |
| `dining_budget` 餐饮预算         | 是（Step 1 必问）              | 无                         | 必须确认口径，仅三种：**每餐预算**（如「每餐 100」）/ **每日预算**（如「每天 300」）/ **全程总额**（如「吃饭一共 2000」），口径直接决定 Step 5 人均上限公式                                   |
| `travelers` 出行人数             | 是（Step 1 必问）              | 无                         | 影响人均上限计算、门票/住宿费用                                                                                                                                                               |
| `preferences` 偏好               | 是（Step 1 必问，**多选**）    | 无                         | AskUserQuestion 开启 multiSelect 让用户同时勾选多项（如：自然风光 / 人文历史 / 美食 / 亲子 / 小众），**全部勾选项都纳入景点筛选**，不得只取其一                                               |
| `travel_dates` 出行日期          | 否                             | 相对日期「Day N」          | 影响天气、节假日、淡旺季门票                                                                                                                                                                  |
| `travel_mode` 出行方式           | 否                             | 公共交通                   | `self-drive`（自驾）或 `transit`（公共交通）                                                                                                                                                  |
| `daily_drive_limit` 每日驾驶上限 | 否（自驾模式 Step 1 建议确认） | 5 小时（约 450km），硬上限 | 自驾模式专用，决定是否插入中途停留城市；**默认不可放宽**——用户要求 >5 小时必须先按红线 8 问询四选一，仅用户明确坚持（选④）才允许超限并记录 `drive_over_limit_confirmed=true`，否则维持 5 小时 |

## 工作流总览

复制此清单跟踪进度：

```
任务进度：
- [ ] Step 1   确认参数 + 预检 → travel_brief（自驾：必读 docs/self-drive.md）
- [ ] Step 2   目的地调研（并行搜索，必读 docs/operations.md）→ candidates.json
- [ ] Step 3   门票查询（七要素，含隐藏消费）→ candidates.json 补全 ticket 字段
- [ ] Step 4   行程规划（自驾：必读 docs/self-drive.md）→ itinerary.json 时间轴 + 路段 + lodging
- [ ] Step 4b  景点图片获取（网图直链优先，AI 小尺寸兜底；必读 docs/operations.md）→ attractions[].image
- [ ] Step 5   餐馆推荐（必读 docs/dining.md）→ itinerary.json 补全餐饮节点
- [ ] Step 6   ~~封面/横幅图~~（已取消：纯 CSS 渐变，无需图片）
- [ ] Step 6.5 预组装校验（闸门，必须全过）
- [ ] Step 7   HTML 组装（必读 HTML_TEMPLATE.md）→ {目的地}{天数}日游攻略.html
- [ ] Step 8   输出交付
```

所有中间数据统一写入 `itinerary.json`（Schema 见 [README.md](README.md)，可用 `python travel-planner.py init mytrip/` 生成模板骨架），各步骤围绕这一个文件流转。

---

## Step 1：确认参数

- **输入**：用户自然语言描述
- **输出**：`travel_brief`——上表全部参数 + 参数口径说明（预算拆分、餐饮预算口径、日期口径）
- **做法**：
  1. 先从用户描述中提取所有能提取的参数。
  2. **以下三项即使用户没提也必须主动询问**：`dining_budget`（餐饮预算）、`travelers`（人数）、`preferences`（偏好）。
  3. 其余缺失的必填项（出发地、目的地、天数、总预算）一并询问；**禁止假设出发地、目的地、天数**。
  4. 用 AskUserQuestion **一次性**问完所有缺失项，不要拆成多轮打断用户。
  5. 选填项采用默认值时，在攻略开头的参数摘要中显式声明（如「未指定日期，按 Day 1-N 相对日期编排」）。
- **预检（参数齐备后必须执行，发现的问题与缺失项合并进同一次 AskUserQuestion）：**
  - **往返可行性预检**（自驾硬规则）：估算总往返里程（去程 + 返程）；若 `总往返里程 > 天数 × 5 小时对应里程（约 450km/天）`，**必须用 AskUserQuestion 让用户四选一**（选项同红线 8）。**不问不改方案，不问不超限交付。** 公共交通模式跳过。
  - **节假日影响预检**：日期确定后必须核对是否跨法定节假日（春节/国庆/中秋等连休）。跨节假日时在攻略开头声明三项影响：**住宿价格上浮**（影响区间内预估上浮 50-100%）、**热门景区预约收紧**（列出需提前抢票的核心景区）、**高速免费窗口**（免费时段内的自驾过路费计 ¥0，需按当年官方公告核实并标注「以公告为准」）。
  - **换酒店顺序预检（仅公共交通）**：行程含跨城换酒店时，默认执行「行李先行」（抵达新城先入住/寄存再玩）；若发现先玩后入住有明显收益（如酒店无法提前入住、赶头批入园），用 AskUserQuestion 问用户二选一，用户明确选后者才记录 `brief.baggage_first=false`。自驾模式无此限制，不问。
- **注意事项**：
  - `travel_dates` 明确后记录星期，用于校验博物馆闭馆日（多数博物馆周一闭馆）。
  - `dining_budget` 必须确认口径（每餐 / 每日 / 全程总额三选一），这直接决定 Step 5 的人均上限（换算见 docs/dining.md）。
  - 自驾模式：`daily_drive_limit` 与油耗确认要点见 [docs/self-drive.md](docs/self-drive.md)。

## Step 2：目的地调研

- **输入**：`travel_brief`
- **输出**：`candidates.json`——候选景点（名称 / GCJ-02 坐标 / 建议游玩时长 / 开放时间 / 类型 / 评分 / **highlights 好玩点**）、住宿商圈建议、市内交通概况、城际交通方案、天气与穿衣建议
- **做法**：按维度搜索，**每维度 1 搜**（多关键词模板只发第一条，结果不佳再补第二条），**每批 ≤6 路并行发送**（批次与超时规则见 [docs/operations.md](docs/operations.md)，执行前必读），批次间不空等：

| 维度       | 搜索关键词模板                                                                                                                                          | 产出                                                                                                                                         |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| 经典景点   | `{目的地}必去景点排行`、`{目的地}{天数}日游经典路线`                                                                                                    | 核心景点清单                                                                                                                                 |
| 偏好景点   | `{目的地} {偏好} 景点推荐`（如 `{目的地} 亲子 景点`）；**多选偏好时逐项覆盖或合并搜索**（如 `{目的地} 自然风光 人文 景点`），每个勾选偏好都要有候选产出 | 个性化补充（全部勾选偏好）                                                                                                                   |
| 小众备选   | `{目的地}小众景点 本地人推荐`                                                                                                                           | 拥挤时的替补                                                                                                                                 |
| 特色美食   | `{目的地}必吃美食清单`、`{目的地}本地人推荐餐馆`                                                                                                        | 餐饮候选池                                                                                                                                   |
| 住宿商圈   | `{目的地}住哪个区域方便 交通 景点`                                                                                                                      | 住宿定位（选交通枢纽、居中于景点聚类的商圈）                                                                                                 |
| 市内交通   | `{目的地}地铁线路图`、`{目的地}公交 地铁 支付方式`                                                                                                      | 出行方式依据                                                                                                                                 |
| 城际交通   | transit：`{出发地}到{目的地}高铁 时刻 票价`；self-drive：`{出发地}到{目的地}自驾路线 高速 距离`                                                         | 首末日时间占排、自驾总里程                                                                                                                   |
| 天气       | `{目的地}{月份}天气 穿衣`；日期临近（15 天内）加查 `{目的地}15天天气预报`                                                                               | **逐日天气**（写入每天 `weather` 字段：现象 + 气温区间，作为实时天气失败时的回落文本）、当日城市代表坐标（横幅实时天气请求用）、贴士穿衣建议 |
| 节假日活动 | `{目的地}{月份}活动 展演 限流`                                                                                                                          | 避坑（景区限流、涨价）                                                                                                                       |

- **注意事项**：
  - 候选景点数量 ≥ 每日 3 个 × 天数 + 20% 余量，给 Step 4 挑选空间。
  - **坐标必须 GCJ-02**（高德坐标系），从搜索结果或高德坐标拾取器获取；无坐标的景点不得进入编排。
  - 每个景点记录建议游玩时长和开放时间，这是 Step 4 排时间轴的依据。
  - **顺手记录图片线索**：搜索结果命中的景点页面（百科/官方站/攻略页）记下 URL，供 Step 4b 直接提取网图直链，避免二次搜索。
  - **每个景点必须记录 `highlights` 好玩点（2-4 条）**：经典玩法 / 必打卡机位 / 独特体验（如「晨雾梯田空镜」「登塔俯瞰全城」「摇橹船穿芦苇荡」），来自景点攻略类搜索结果；写不出具体玩点的景点不得进入编排——这是「景点好不好玩」的决策依据，也是 HTML 景点卡片「🎢 好玩点」行的数据源。
  - 首访用户优先必去地标；用户偏好决定次级筛选权重。

## Step 3：门票查询

- **输入**：`candidates.json` 中每个候选景点
- **输出**：每个景点的 `ticket` 字段，**逐项查询以下七要素**：

| 要素           | 字段                   | 查不到时                                                                                                                                                                                           |
| -------------- | ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 全票价格       | `price`                | 填 null + `price_note` 给参考区间（标注「参考区间」）                                                                                                                                              |
| 优惠政策       | `concessions`          | 学生/老人/儿童半价等，可省略                                                                                                                                                                       |
| 是否需预约     | `reservation_required` | 不得省略，必须查                                                                                                                                                                                   |
| 预约渠道       | `booking`              | 官方公众号名称 / 官网 / 携程 / 美团                                                                                                                                                                |
| 提前放票规则   | `advance_days`         | 热门景区放票时间和提前天数                                                                                                                                                                         |
| 当天能否现场买 | `walkup_available`     | 「仅预约制」景区此项决定行程成败                                                                                                                                                                   |
| **隐藏消费**   | `extra_fees`           | 不得省略，必须查：门票之外的所有二次消费——停车费/索道缆车/景区观光车/游船摇橹船/玻璃栈道/夜场灯展/讲解器/寄存等，逐项列「名称 + 价格」；核实确实没有的填「无」；查不到的填「需人工核实」，禁止留空 |

- **搜索关键词模板**：
  - 价格：`{景点名}门票价格 多少钱`
  - 预约：`{景点名}预约 官方公众号 怎么约`
  - 放票：`{景点名}提前几天放票 预约攻略`
  - 现场票：`{景点名}当天能现场买票吗 不预约能进吗`
  - 隐藏消费：`{景点名} 隐性收费 索道 观光车 停车费 一共花多少钱`（可与其他关键词合并搜索）
- **提速规则（合并搜索）**：Step 2 搜索结果已覆盖门票七要素的景点直接复用，不重复查询；缺字段的景点**每 4 个合并为 1 次搜索**，仍缺再单查；**禁止默认逐景点逐关键词搜索**（性能预算详见 docs/operations.md）。
- **注意事项**：
  - **硬性规则：查不到确切价格时填「需人工核实」，禁止编造价格数字**。
  - **隐藏消费是预算失真的头号来源**：索道/游船/观光车类二次消费常与门票同价甚至更贵（如「门票+往返索道」套票制景区必须写明套票口径），逐项计入预算表门票行明细。
  - 热门景点（故宫、陕历博、国博等）的「是否必须预约」是行程成败关键，必须查到明确结论。
  - 门票总费用 × travelers 汇入预算表；与总预算冲突时反馈并建议调整（换免费景点 / 淡季出行）。

## Step 4：行程规划

- **输入**：`candidates.json`（含坐标、时长、开放时间、门票、highlights）
- **输出**：`itinerary.json` 的 `days` 数组——逐日时间轴条目（`start`/`end`，30 分钟粒度）+ 每日 `weather`（`cond` 天气现象 / `temp` 气温区间，来自 Step 2）+ 每日 `city`/`city_lat`/`city_lng`（当日城市代表坐标，Step 7 天气栏 `data-lat/lng` 用）+ 每日 `segments` 路段骨架；同时把逐晚住宿写入 `lodging[]`（day / city / area / hotel / est_price / note / **reason / backup**——backup 结构为 `{name, est_price, reason}`）。**每个入住日（住宿第一天或换酒店日）的时间轴必须插入一条 type=`hotel` 条目**，字段：`start`/`end`、`hotel`（店名）、`price`（每晚价）、`reason`（推荐理由一句话）、`backup`（`{name, est_price, reason}`）、地址/商圈与距上一地点导航写在 highlight/desc 中；连住日不重复插入。
- **排布原则**：
  1. **就近聚类**：按坐标把景点聚类分天（k = 有效游玩天数），同一天内按最近邻排序，**严禁跨城折返**。
  2. **时间轴骨架**：早餐 07:30-08:30 → 09:00 出发 → 上午景点（建议时长 + 30 分钟缓冲）→ 午餐 12:00-13:30 → 下午景点 → 晚餐 18:00-19:30 → 可选夜景 → 回酒店。
  3. **作息时间窗（红线 10，硬约束 + 特批问询）**：每天首条活动 `start ≥ 07:30`、末条活动 `end ≤ 23:00`；若当天早于 07:30 出发有可核实的实质收益（头批入园/避限行/首批索道等），先用 AskUserQuestion 问用户「特批早起」还是「保持 07:30」，未问询不得早排。
  4. 每天景点 2-4 个、总游玩 ≤8 小时；第一天和最后一天预留城际交通时间。
  5. **开放时间校验**：闭馆日景点必须避开；夜间项目排在晚餐后。
  6. **自驾模式**（`travel_mode=self-drive` 时必读 [docs/self-drive.md](docs/self-drive.md)）：驾驶上限、中途停留城市、油费过路费、路线图规则全部在该文件。
- **注意事项**：时间轴条目之间的移动时间必须与 `segments` 的 `duration_min` 一致；`segments` 数量 = 当日地点序列的相邻对数（含回到酒店）。

## Step 4b：景点图片获取（网图直链优先，AI 小尺寸兜底）

- **输入**：编排完成后的每日景点列表 + Step 2/3 搜索中顺手记录的景点页面/图片线索
- **输出**：`attractions[].image` 逐景点补全（在线直链 URL 或 AI 兜底图），一个都不能少；**无需下载落盘，无需考虑离线打开场景**
- **规格**：比例 4:3 或 1:1；**AI 兜底生成不用高清——短边 ≤512px（如 640×480），大小合适、清晰即可，减少生成耗时与 token**
- **获取优先级（先网图，后 AI）**：
  1. **网图直链优先（零下载零生成成本，优先用）**：
     - 复用 Step 2/3 已搜索到的景点页面（百科/官方站/Wikimedia/攻略页），提取 `og:image` 或正文大图直链；
     - 缺图景点可补搜一次 `{景点名} 实景照片`，从结果页面提取图片直链；
     - **选图硬标准（红线 2）**：必须与景点实际相符、地标特征可辨认；**禁止选用明显过度精修/广告渲染图**（一眼 P 图、过饱和、仙境感）——优先真实游记实拍、Wikimedia Commons、官方实景照；拿不准宁走 AI 兜底；
     - 直链优先选长期稳定图源（Wikimedia Commons、官方站点）；明显易失效的临时 URL 不用，直接进 AI 兜底清单，不要反复折腾。
  2. **AI 生成兜底**：仅对无可用网图的景点调用生图工具，提示词模板：`{景点名称}，{城市}，真实摄影风格，{Step 2 查到的当季天气/时段}，广角构图，游客视角`——追求实景感，避免艺术渲染感；**明确要求小尺寸（4:3、短边 ≤512px），不要求高清**；生成结果直接引用返回的直链即可（落盘为可选）。
- **执行规则**：硬约束不变（红线 2）——**每个景点一个 `image` 值，缺图 = validate ERROR，禁止占位图代替**。网图直链提取无并发限制可批量进行；AI 生成仍按批次细则执行（每批 ≤3、短等待轮询 ≤120s、失败换角度重试 3 次）见 [docs/operations.md](docs/operations.md)（执行前必读）；等待期间穿插推进 Step 5 餐馆数据 / 导航链接等不依赖图片的工作。
- **版权声明**：网图优先选官方/自由版权来源；攻略核实清单统一注明「配图来自网络公开图片或 AI 生成示意图，版权归原作者所有，仅作行程参考」。

## Step 5：餐馆推荐

- **输入**：`itinerary.json`（每日地理位置与时段）、`dining_budget`、`travelers`
- **输出**：每个午餐/晚餐节点：主推荐餐馆 + **至少 1 家备选店**
- **执行规则**：预算口径换算（人均上限公式）、选店要求（主推/备选要素）、就近原则、服务区简餐豁免等**全部见 [docs/dining.md](docs/dining.md)（执行前必读）**；硬约束只有一条：主推与备选店人均都 ≤ 上限（红线 5）。

## Step 6：（已取消）封面与横幅图

- **本步骤不再生成任何图片**：封面（240px）与每日横幅（110px）均为模板内置的 CSS 渐变背景，横幅右侧玻璃实时天气栏（Open-Meteo，红字提示「越远越不准确」）由模板 JS 自动填充。`images/` 内**只放景点实景图**（Step 4b 已全部完成）。直接进入 Step 6.5 校验。

## Step 6.5：预组装校验（闸门，全部通过才能进入 Step 7）

- **输入**：`itinerary.json`、`images/` 目录
- **做法**：先运行自动化脚本 `python travel-planner.py validate itinerary.json`，再逐项人工复核：

| 检查项                | 检查方法                                                                                                                                                       | 通过标准                                                                                                                    |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 景点照片覆盖率        | 脚本自动：逐景点检查 `image` 字段非空——在线直链（http/https）直接通过，本地路径比对 `images/` 文件存在性                                                       | 景点数 = image 数，0 缺失（硬约束，缺图一律 ERROR 不得交付，禁止渐变/占位图代替）                                           |
| 住宿数据              | 脚本检查 `lodging[]`：每一晚（末日返程除外）各一条，含城市/商圈/预估价/**reason/backup**；并检查每个入住日时间轴含 type=`hotel` 条目（含 price/reason/backup） | 0 缺失；缺失为 WARNING，进入组装前必须补全（红线 9）                                                                        |
| 逐日天气              | 脚本检查每天 `weather.cond` / `weather.temp`                                                                                                                   | 0 缺失；缺失为 WARNING，横幅实时天气失败时无回落文本                                                                        |
| 导航链接覆盖率        | 遍历每天 `segments`，检查每段的 `nav_url` 格式合法（百度地图 direction 接口 + origin/destination/coord_type=gcj02 参数齐全）；段数 = 当日相邻地点对数          | 0 缺失、0 格式错误                                                                                                          |
| 门票信息              | 遍历 `attractions[]`，`price` / `price_note`（免费或需人工核实）至少一项非空；**`ticket.extra_fees` 非空（「无」或逐项清单）；`highlights` 有 2-4 条好玩点**   | 0 缺失（extra_fees / highlights 缺失为 WARNING，组装前必须补全）                                                            |
| 餐馆预算              | 脚本自动：遍历全部午餐/晚餐 `restaurant` 与 `backup`，`avg_price ≤ 人均上限`（`brief.per_meal_cap` > 0 时）；主推与备选店名不同                                | 0 超标，0 缺备选                                                                                                            |
| 时间轴完整性          | 检查无重叠、无负时长、每日首尾衔接酒店、开放时间不冲突；路段数少于当日地点序列相邻对数时给 WARNING（核对红线 1）                                               | 全部通过                                                                                                                    |
| 作息时间窗（红线 10） | 脚本自动：逐日检查首条活动 `start ≥ 07:30`、末条活动 `end ≤ 23:00`                                                                                             | 全部通过；早起违反且该日在 `brief.early_start_confirmed_days` 中（已问询特批）降 WARNING，否则 ERROR；晚于 23:00 一律 ERROR |
| 每日驾驶时长（自驾）  | 脚本自动：逐日合计 mode=drive 路段的 `duration_min`                                                                                                            | 每天 ≤300 分钟（5 小时）；超限且 `brief.drive_over_limit_confirmed=true`（用户已问询确认）降为 WARNING，否则 ERROR          |

- **注意事项**：不通过 → 修复后重跑，**最多 2 轮**；仍不通过时按红线 7 执行——缺图（红线 2）与导航缺失（红线 1）不得交付、必须继续修复，其余 ERROR/WARNING 逐项列明后方可交付。

## Step 7：HTML 组装

- **输入**：`itinerary.json`（全部字段已补全）、`images/`、`route_map.html`（自驾）
- **输出**：`{目的地}{天数}日游攻略.html`，景点图直接引用 `attractions[].image`（在线直链或本地 `images/` 路径）
- **执行规则**：**以 [HTML_TEMPLATE.md](HTML_TEMPLATE.md) 为唯一事实源（执行前必读）**——整体复制完整骨架后仅替换 `{{占位符}}` 与数据行，**禁止增删板块、禁止改动类名 / DOM 结构 / CSS**。板块顺序、各条目结构（含景点「🎢 好玩点」行、「💰 隐藏消费」行、酒店入住条目、三餐时间轴条目）、百度地图导航链接格式、免费窗口过路费分段列示等全部以模板「占位符对照表」与「其他规则」章节为准，**本文件不再重复维护这些细节**。
- **导出 PDF 按钮（必须保留）**：骨架内置右下角固定「⬇ 导出 PDF」按钮（`window.print()` + `@media print` 打印优化样式：隐藏按钮、颜色保真、逐日卡片不跨页断裂），且带防呆 JS——等全部景点图片加载完成后才亮起可用（初始禁用态「⬇ 图片加载中…」，在线直链图片未加载完就导出会导致 PDF 空白图），组装时**禁止删除按钮、防呆 JS 与打印样式**；交付说明中告知用户「按钮亮起即可打印/另存为 PDF，生成的 PDF 已内嵌图片、无需联网」。
- **组装后结构自检（闸门，必须执行）**：组装完成后运行 `python travel-planner.py validate itinerary.json --html {攻略文件}.html`——脚本会校验攻略 HTML 十大板块齐全且顺序正确、`day-card`/`weather-bar` 数量与天数一致、无已废除的 meal-cards 三餐小结卡；未通过必须按报错修复 HTML 后重跑，全过才允许进入 Step 8（每次生成结果与模板不一致多半源于漏板块/加错板块/顺序漂移，此闸门用于自动拦截）。

## Step 8：输出交付

- **输入**：全部产物
- **输出**（交付给用户三样东西，全部落在「输出位置」规定的可写目录内）：
  1. `{目的地}{天数}日游攻略.html`——最终攻略（景点图为在线直链引用，需联网查看；内置右下角「⬇ 导出 PDF」按钮，浏览器打印/另存为 PDF）
  2. `itinerary.json`——结构化行程数据（含 `attractions[].image` 直链/路径），供用户二次修改或重新生成
  3. `images/` 目录——仅当 AI 兜底图落盘时才有内容（可选）
- **交付动作**：用文件卡片展示 HTML，摘要控制在 3 句以内：行程亮点、总预算 vs 用户预算、需人工核实项数量；并提示「点击攻略右下角『⬇ 导出 PDF』按钮即可导出/打印 PDF」。
- **必须附带的提示**：「价格、预约规则和营业信息以查询时点为准，出发前请按攻略末尾核实清单复核；配图来自网络公开图片或 AI 生成示意图，实际景色以现场为准。」

## 参考文件

- [docs/operations.md](docs/operations.md)：超时与重试策略、批次策略、性能预算、模式 B 离线规则
- [docs/self-drive.md](docs/self-drive.md)：自驾模式专项规则（驾驶上限 / 中途城市 / 油费过路费 / 路线图）
- [docs/dining.md](docs/dining.md)：餐饮推荐与预算口径换算规则
- [HTML_TEMPLATE.md](HTML_TEMPLATE.md)：**HTML 组装唯一模板**——十大板块完整骨架 + 全套 CSS + 渐变横幅（含天气）+ 占位符对照表 + 导航链接格式，Step 7 必须以此为准
- [README.md](README.md)：使用说明、itinerary.json Schema、武汉→威海完整示例
- `travel-planner.py`：本地 CLI（`init` 生成模板 / `validate` 质量校验 / `map` 路线地图与距离估算，模式 B 依赖）
