# ctOS 2.0

一个 FastAPI + LangGraph 搭建的多模块 AI 应用。同一个 FastAPI app 挂载多个能力模块，共用一套静态资源与会话接口。

> **线上地址：<https://ctos2.cn>**（也可用 `www.ctos2.cn`），打开页面会先进入访客空间，注册账号后可跨设备保留记录。
> 没有绑定任何本地端口，线上走 Cloudflare 提供的 HTTPS。

> **本文是给智能客服模块检索用的知识库文档**，比项目根目录的 `README.md` 更详细。
> 根目录那份面向第一次接触项目的人，问答尽量短；本文则把「怎么用、有哪些模块、数据存在哪、
> 接口长什么样、出了问题怎么排查」都写全，方便客服回答问题。
> 两者的口径以代码为准，如有出入以本文和系统手册 `ctOS2_manual.md` 为准。

## 模块

**四个能力模块都已接入 Web 页面**，页面顶栏有三个标签（闲聊 / 智能出行 / 智能客服），
角色扮演挂在「闲聊」里，从侧栏的「角色扮演」菜单进入：

| 模块 | 路由 | 说明 |
| --- | --- | --- |
| 闲聊 / 对话 | `/chat` | 基于 LangGraph 的对话图，流式返回纯文本 |
| 角色扮演 | `/chat`（带 `role_id`）+ `/roleplay/*` | 预设角色、自己写角色、AI 帮我查；会话复用闲聊的表 |
| 智能出行 | `/trip/chat` | 一个 Agent：自己答 / 调路线 / 调攻略，SSE 事件流 |
| 智能客服 | `/customer/chat` | RAG 三层检索问答（关键词 → 向量 → 混合），SSE 事件流 |

出行和客服都不是独立 app，它们是 ctOS 的能力。

智能出行内部有两项能力（`modules/trip/` 下的 `route/` 和 `guide/` 下的路线规划和旅游攻略），
它们是 Agent 手里的工具，不是用户能选的模式。

每个业务模块各有一张 LangGraph 图，互不干扰：

- 闲聊：`START → chat_node → END`，最简单的一张图
- 角色扮演：不走图，直接拼提示词调模型流式输出（`modules/chat/roleplay/stream.py`）
- 智能出行：`START → agent → END`，一个节点做判断，再按判断去调下面两张子图
  - 路线规划（子图）：`START → collect_routes → ask_user（暂停等选方案）→ compare_routes → decide_route → write_tips → END`
  - 旅游攻略（子图）：`START → weather → spots_agent →（工具循环）→ ask_spots（暂停等勾选）→ planner → advice → END`
- 客服：`START → retrieve → generate → END`，一条直线

一个重要区别：**闲聊、角色扮演和出行会把我说的内容存进数据库**，左侧栏能翻到历史记录；
**智能客服问答本身不写数据库**（但会把最近 3 轮对话带上，用来理解追问），刷新页面就没了。

### 后端接口一览

除 `/auth/*`、`/health`、`/trip/ping`、`/guide/ping`、`/customer/ping`、`/notice`、`/feedback` 和静态资源外，
**所有接口都要先登录**，请求头带 `Authorization: Bearer <token>`。

| 方法 | 路径 | 所属模块 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | 认证 | 注册邮箱 + 密码，自动创建一个专属租户，直接返回 token |
| `POST` | `/auth/login` | 认证 | 登录，返回 token |
| `GET` | `/auth/me` | 认证 | 查当前登录用户，前端刷新页面时用来验证 token |
| `POST` | `/auth/trial` | 认证 | 免注册建一个访客账号并直接登录（页面首次打开自动调用） |
| `POST` | `/chat` | 闲聊 | 请求 `{"messages": "...", "session_id": 可选, "role_id": 可选}`，返回 `text/plain` 流，响应头带 `X-Session-Id` |
| `GET` | `/sessions` | 闲聊 | 会话列表，每条带 `role_id`（角色会话才有值） |
| `GET` | `/sessions/{id}/messages` | 闲聊 | 某个会话的全部消息 |
| `DELETE` | `/sessions/{id}` | 闲聊 | 删除会话，消息级联删除 |
| `GET` | `/roleplay/roles` | 角色扮演 | 预设角色 + 自己写的角色 |
| `GET` | `/roleplay/roles/{id}` | 角色扮演 | 一个角色的完整档案 |
| `POST` | `/roleplay/roles` | 角色扮演 | 保存自己写的 / AI 查出来的角色 |
| `POST` | `/roleplay/roles/search` | 角色扮演 | AI 帮我查，生成角色草稿（不存库） |
| `DELETE` | `/roleplay/roles/{id}` | 角色扮演 | 删除自定义角色（预设角色不能删） |
| `POST` | `/roleplay/start` | 角色扮演 | 选一个角色开始：建会话、绑角色、存开场白 |
| `GET` | `/roleplay/session/{id}` | 角色扮演 | 这个会话是哪个角色（普通聊天返回 `role: null`） |
| `GET` | `/roleplay/memory/{role_id}` | 角色扮演 | 这个角色记住了什么 |
| `POST` | `/roleplay/memory/clear` | 角色扮演 | 清空这个角色的记忆 |
| `POST` | `/trip/chat` | 出行·路线 | 请求 `{"query": "...", "history": [...], "chat_id": 可选}`，返回 SSE |
| `POST` | `/guide/chat` | 出行·攻略 | 同上 |
| `POST` | `/trip/route/choose` | 出行·路线 | 路线暂停后，用户选了哪个方案，继续写结论 |
| `POST` | `/guide/spots` | 出行·攻略 | 攻略暂停后，用户勾掉/补充了哪些景点，继续排行程 |
| `GET` | `/trip/ping` | 出行·路线 | 存活检测 |
| `GET` | `/guide/ping` | 出行·攻略 | 存活检测 |
| `GET` | `/trip/list` | 出行 | 最近的出行记录，默认最多 50 条（带 `last_kind`） |
| `GET` | `/trip/{id}` | 出行 | 单条出行记录，含各段产出和用户原话 |
| `DELETE` | `/trip/{id}` | 出行 | 删除出行记录，子表级联删除 |
| `POST` | `/trip/delete-batch` | 出行 | 批量删除，请求 `{"ids": [...]}` |
| `POST` | `/customer/chat` | 客服 | 请求 `{"query": "...", "history": [...]}`，返回 SSE |
| `GET` | `/customer/ping` | 客服 | 存活检测 |
| `POST` | `/feedback` | 反馈 | 提交评价 + 文字反馈，同一 IP 每分钟最多 3 条，不强制登录 |
| `GET` | `/notice` | —— | 更新公告，内容来自 `config/notice.json` |
| `GET` | `/health` | —— | 健康检查，返回数据库名和连接用户 |
| `GET` | `/` | —— | 前端页面 `static/index.html` |

SSE 事件名统一是：`SAY`、`START`、`STEP`、`TOKEN`、`DONE`、`CHAT`、`ERROR`，出行结束时还会发一条 `SAVED`（带 `chat_id`）。
出行模块还会发几个“等你操作”的事件：`ASK_PLACE`（地名有歧义，先挑一个）、`ASK`（选路线方案）、
`ASK_SPOTS`（勾选景点）、`ASK_ROUTE`（问要不要查真实路线）。
客服模块只用到 `START` / `TOKEN` / `DONE` / `ERROR`。

## 界面预览

**闲聊模式**（`/chat`）——流式纯文本对话：

![闲聊模式](../../screenshot/ctOS_chat.png)

**智能出行**（`/trip/chat`）——两种模式，中途都会暂停让你确认：

![智能出行](../../screenshot/ctOS_trip01.png)

线上可以直接看：<https://ctos2.cn>（点顶栏切换模块，角色扮演在左侧菜单里）。

## 目录结构

项目按职责分成八层，依赖方向单向（api → cli → modules → common → databases）。

```
ctOS2.0/
├── api/                        # ③ 接口层：每个模块一个路由文件
│   ├── main.py                 # ★ FastAPI 入口，只做装配（建 app + 挂静态 + include_router）
│   ├── deps.py                 # 路由共用：取租户 tenant_of / 校验图片 / SSE 响应头
│   └── routes/
│       ├── auth.py             # /auth/register、/auth/login、/auth/me
│       ├── trial.py            # 访客账号 /auth/trial（独立文件，可整块删）
│       ├── chat.py             # /chat（含角色扮演分支）+ /chat/attachment
│       ├── trip.py             # /trip/*：出行唯一入口 + 路线选择 + 会话管理
│       ├── guide.py            # /guide/spots：勾完景点继续
│       ├── roleplay.py         # /roleplay/*：角色增删查 + 记忆
│       ├── customer.py         # /customer/chat
│       ├── sessions.py         # /sessions：列出 / 读消息 / 删除
│       ├── presence.py         # /presence/*：在线人数
│       ├── feedback.py         # /feedback
│       └── system.py           # /notice、/health、/
├── cli/                        # ④ 本地层：每个能独立跑完的 agent 一个终端入口
│   ├── chat.py                 # 对话：python -m cli.chat
│   ├── trip.py                 # 出行主 Agent（自己判断走哪条路）：python -m cli.trip
│   ├── route.py                # 路线规划子 Agent：python -m cli.route
│   ├── guide.py                # 旅游攻略子 Agent：python -m cli.guide
│   ├── customer.py             # 智能客服：python -m cli.customer
│   └── prompts.py              # 提示词生成：python -m cli.prompts
├── common/                     # ② 公共层：跨模块共用
│   ├── llm.py                  # 唯一的模型客户端 get_llm()，也负责加载 .env
│   ├── db.py                   # PostgreSQL 连接 + 建表总入口 create_all_tables()
│   ├── auth.py                 # 密码 bcrypt 哈希 + JWT 签发与校验
│   ├── sse.py                  # SSE 事件打包 + 把同步生成器放进工作线程
│   ├── checkpoints.py          # LangGraph 暂停现场（路线和攻略共用一个 sqlite）
│   └── tools/                  # 外部数据工具
│       ├── search.py           # 联网搜索
│       ├── weather.py          # 天气（Open-Meteo）
│       └── amap.py             # 高德地图
├── databases/                  # ⑥ 数据库层：公共 / 各模块 / 运维工具
│   ├── common/
│   │   ├── db.py               # 连接 + 通用操作 + 建表总入口
│   │   └── db_tenant.py        # 全局身份表 tenants
│   ├── modules/
│   │   ├── db_auth.py          # 用户 users
│   │   ├── db_chat.py          # sessions / messages / message_images
│   │   ├── db_trip.py          # 出行 4 张表
│   │   ├── db_roleplay.py      # 角色扮演 3 张表
│   │   └── db_feedback.py      # 反馈 feedback
│   └── tools/                  # 运维 CLI，不参与 Web 服务
│       ├── view.py             # 查看数据
│       ├── clean.py            # 清理数据
│       └── feedback_view.py    # 查看反馈
├── modules/                    # ① 模块层：按子集 / 交集组织
│   ├── chat/                   # 闲聊（父）
│   │   ├── graph / node / state / prompts / stream / sessions / attachments
│   │   └── roleplay/           # ← 子集：角色扮演（复用闲聊的会话表）
│   ├── trip/                   # 智能出行（父）
│   │   ├── agent.py            # 编排：判断该自己答 / 走路线 / 做攻略
│   │   ├── graph / node / state / prompts / stream
│   │   ├── route/              # ← 子集：路线规划
│   │   └── guide/              # ← 子集：旅游攻略
│   ├── customer/               # 智能客服（RAG）
│   │   ├── graph / node / state / prompts / stream
│   │   ├── rag_config.py       # 语料目录、向量库目录、集合名、向量模型
│   │   ├── rag_store.py        # 知识库加载（全进程只加载一次）
│   │   ├── rag_search.py       # 三层检索：关键词 / 向量 / 混合
│   │   ├── rag_ingest.py       # 入库脚本
│   │   ├── rag_eval.py         # 检索测评脚本（40 题）
│   │   ├── embedding.py        # 向量化（本机 Ollama）
│   │   ├── eval/golden.json    # 检索测评题库
│   │   └── data/chroma/        # 向量库落盘（运行产物，不入 git）
│   └── imagegen/               # ← 交集：生图（在建，尚未接入路由）
├── docs/                       # ⑧ 文档层
│   ├── reading/                # 给人读：架构、文件清单、部署、主题、生图
│   ├── planning/               # 规划稿与排查记录
│   └── corpus/                 # RAG 语料（本文就在这里）
├── config/                     # ⑦ 配置层：.env、配置模板、requirements.txt、公告
├── static/                     # 前端（无构建步骤）
│   ├── index.html              # 入口页：读偏好 + 判断屏幕宽度，跳到 themeA 或 themeB
│   ├── themeA/                 # 经典版：左侧栏 + 顶栏 tab + 气泡对话（3 种风格）
│   ├── themeB/                 # 指挥台版：图标导轨 + 右侧控制台（仅宽屏，2 种风格）
│   └── shared/                 # 两套共用
├── scripts/                    # 构建与运维脚本
└── screenshot/                 # README 用的界面截图
```

## 数据存储

所有业务数据存在 PostgreSQL 数据库 `ctos2` 里，共 13 张表：

| 表 | 所属模块 | 说明 |
| --- | --- | --- |
| `tenants` | 全局 | 租户，一个注册用户对应一个租户；所有业务表都外键引用它 |
| `users` | 认证 | 账号，邮箱唯一，密码存 bcrypt 哈希 |
| `sessions` | 闲聊 | 一次会话，主键 `id`（角色扮演复用这张表） |
| `messages` | 闲聊 | 会话里的消息，外键 `session_id` → `sessions.id` |
| `trip_chats` | 出行 | 一次出行对话（左侧列表的一条） |
| `trip_sessions` | 出行 | 一轮出行规划，主键 `id` |
| `trip_user_inputs` | 出行 | 用户输入，外键 `trip_id` → `trip_sessions.id` |
| `trip_ai_outputs` | 出行 | AI 各段产出，外键 `trip_id` → `trip_sessions.id` |
| `role_play_sessions` | 角色扮演 | 哪个聊天会话用的是哪个角色（外键 `session_id` → `sessions.id`） |
| `role_play_memories` | 角色扮演 | 每个角色记住的事，按「租户 + 角色」存一篇 200 字以内摘要 |
| `role_play_roles` | 角色扮演 | 用户自己写的角色，id 形如 `custom_12` |
| `feedback` | 反馈 | 用户提交的评价和意见 |

外键都设了 `ON DELETE CASCADE`：删掉主记录，子记录自动跟着删。

**所有业务表都有 `tenant_id`**，每个请求由 API 层从登录 token 里解析出当前租户传下去，
查询时一律带上它，所以不同账号之间看不到对方的数据。

智能客服是一问一答，**不写数据库**，所以没有自己的表。它的「知识」只落在本地 Chroma 目录里。

除了这 13 张表，还有两处**运行产物、不入 git**：

- `databases/checkpoints/route_checkpoints.sqlite`：出行的 LangGraph 暂停现场（SQLite）
- `modules/customer/data/chroma/`：客服的向量库

几个字段值得知道：

- `sessions.title`：会话标题，取用户第一句话的前 14 个字
- `sessions.updated_at`：每次追加消息都会刷新，会话列表按它倒序排
- `messages.role`：只能是 `user` 或 `assistant`
- `trip_sessions.turn_kind`：`ROUTE` 表示路线决策，`TRAVEL` 表示旅游攻略，`CHAT` 表示被判为闲聊、只回了一句话
- `trip_sessions.destination / days / start_date`：从需求里解析出来的出行要素
- `trip_ai_outputs`：攻略四段 `weather` / `spots` / `itinerary` / `route_plan`；
  路线决策四段 `route_need` / `route_compare` / `route_decision` / `route_tips`；再加 `chat_reply`
- `role_play_memories.rounds`：这个角色聊了几轮，每满 6 轮整理一次记忆
- `feedback.rating`：存中文原文（很满意 / 满意 / 一般 / 不太满意），不存数字

连接层 `databases/conn.py` 的 `get_conn()` 每个操作开一个短连接，用完自动关，
出错自动回滚；`transaction()` 把多条写入包成一个事务。
**不要另写第二份开连接的代码**，所有 SQL 都走 `databases/conn.py` 提供的 `query` / `query_one` / `execute`。

查看数据库内容（不用装任何工具）：

```bash
python -X utf8 -m databases.tools.view            # 列出所有会话
python -X utf8 -m databases.tools.view show 3     # 看某个会话的完整对话
python -X utf8 -m databases.tools.view trips      # 出行列表
python -X utf8 -m databases.tools.view stats      # 统计
python -X utf8 -m databases.feedback_view      # 用户反馈
```

> `databases/tools/view.py` 用命令行查看闲聊的几张表。线上服务器上的数据用
> `psql -U ctos_app ctos2` 可以直接进去查。

## 快速开始

### 1. 安装依赖

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r config/requirements.txt
```

依赖分几组：Web（fastapi / uvicorn / python-dotenv）、
Agent 编排（langgraph / langchain 系列 / openai / httpx）、
客服模块（chromadb / jieba / rank-bm25）、
数据库（psycopg）、认证（python-jose / bcrypt）。
其中 `langgraph-checkpoint-sqlite` 是出行暂停现场用的——`modules/trip/route/graph.py`
用它把 interrupt 的状态落到 `databases/checkpoints/`；业务数据本身仍然走 PostgreSQL。

### 2. 配置环境变量

复制模板并填入自己的值：

```bash
cp config/YOUR_config.env config/.env
```

`config/.env` 需要填写：

```
DEEPSEEK_API_KEY=      # DeepSeek 密钥，对话、图上推理、联网搜索都用它
DEEPSEEK_BASE_URL=     # DeepSeek 接口地址
DEEPSEEK_MODEL=        # 模型名

AMAP_KEY=              # 高德地图密钥，智能出行算路线用

ZHIPU_API_KEY=         # 智谱密钥，智能客服 RAG 向量化用（必填）

# 数据库（PostgreSQL）
PG_HOST= / PG_PORT= / PG_DBNAME= / PG_USER= / PG_PASSWORD=

# 认证：登录 token 的签名密钥，用 python -c "import secrets; print(secrets.token_urlsafe(48))" 生成
JWT_SECRET_KEY=
```

`ZHIPU_API_KEY` 对客服模块是**必需**的：加载知识库时会先检查它，取不到就直接抛错。
也就是说没配这个密钥，智能客服模块用不了（其它模块不受影响）。

**项目本身不含任何密钥**，clone 下来必须自己申请并填写，否则跑不起来。
几个密钥的用途、必要性、申请地址：

| 密钥 | 用途 | 必要性 | 去哪申请 |
| --- | --- | --- | --- |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | 所有对话和推理，出行搜景点也复用这个密钥 | 必需，缺了闲聊、角色扮演和出行都不能用 | platform.deepseek.com |
| `ZHIPU_API_KEY` | 智能客服向量化 | 必需，缺了客服模块用不了 | open.bigmodel.cn |
| `AMAP_KEY` | 出行模块算路线 | 出行要用，缺了只能走攻略流程 | lbs.amap.com |
| `JWT_SECRET_KEY` | 登录 token 签名 | 必需，缺了启动就报错 | 自己生成 |

这些外部 API 大多需要注册账号，部分需要付费或有免费额度限制，具体以各家官网为准。

只想先试一个模块的话，最少需要配：

- 只看闲聊 / 角色扮演：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`JWT_SECRET_KEY`
- 加智能出行：再补 `AMAP_KEY`（联网搜索复用 DeepSeek 密钥，不用另外申请）
- 加智能客服：再补 `ZHIPU_API_KEY`

> `config/.env` 已被 `.gitignore` 忽略，**不要**提交真实密钥。

### 3. 初始化数据库

```bash
python -X utf8 -m databases.schema
```

会建好全部 13 张表（`tenants` / `users` / `sessions` / `messages` / `trip_chats` /
`trip_sessions` / `trip_user_inputs` / `trip_ai_outputs` / `role_play_sessions` /
`role_play_memories` / `role_play_roles` / `feedback`），已存在则跳过，不会动已有数据。
**没建表的话注册登录会直接报错。**
升级代码之后也建议再跑一次，它会补上新增的表和字段（`ADD COLUMN IF NOT EXISTS`）。

### 4. 智能客服入库（第一次使用前跑一次）

智能客服依赖本地向量库，需要先把 `docs/corpus/` 里的文档切块、向量化、入库：

```bash
python -X utf8 -m modules.customer.rag_ingest
```

注意几点：

- 入库用的是**本机 Ollama**，不需要密钥；但要保证 Ollama 在跑，并且拉过模型
- 只处理 `docs/corpus/` 下的 `*.md` 文件（不含子目录）
- 按 Markdown 标题切块，每块带「文件名 › 一级标题 › 二级标题」的标题路径；
  代码块里的 `#` 不算标题，也不会把代码块切断
- 单块超过 800 字符（`MAX_CHUNK_CHARS`）再按段落切开，短于 40 字符的碎片丢掉
- 向量化会自动分批：接口限制一次最多 64 条，脚本分批提交，
  所以文档块数超过 64 也能一次跑完
- 重复入库是安全的：每次会先删掉同名集合再重建
- **改了文档后要重新跑一次，并重启服务**，否则检索到的还是旧内容

### 5. 启动服务

```bash
python -X utf8 app.py
```

打开 <http://127.0.0.1:8080/> 即为前端页面。线上对应的是 <https://ctos2.cn/>。

> 默认监听 `127.0.0.1:8080`，由 `api/main.py` 末尾 `uvicorn.run(app, host=..., port=...)` 决定，
> `HOST` / `PORT` 两个环境变量可以覆盖。
> 前端用相对路径请求后端（同源），所以换端口只改这一处即可。
>
> 要让局域网内其它设备访问，把 `HOST` 设成 `0.0.0.0`。

## 前端开发

前端**没有任何构建步骤**：改代码保存后刷新浏览器即可生效。

| 文件 | 负责 |
| --- | --- |
| `static/index.html` | 入口页：读主题偏好 + 判断屏幕宽度，分流到 themeA / themeB |
| `static/shared/js/common/` | 两套共用：偏好、在线人数、配置、工具、认证、公告、反馈、SSE、打字机 |
| `static/themeA/js/app.js` | 经典版核心：状态、侧边栏、闲聊、角色扮演、模块切换 |
| `static/themeA/js/trip.js` | 智能出行（四段卡片、出行历史、人工确认面板） |
| `static/themeA/js/customer.js` | 智能客服（问答渲染） |
| `static/themeA/css/style.css` | 模板原样式 |
| `static/themeA/css/modules.css` | 出行卡片、客服气泡、登录页等新增样式 |
| `static/themeA/css/theme.css` | 三套风格的颜色和组件覆盖 |
| `static/themeB/js/console.js` | 指挥台版右侧控制台（目录、操作日志、系统负载） |

前端分成两套独立主题：`themeA`（经典版，手机端只用它）和 `themeB`（指挥台版，仅宽屏）。
两套之间不互相引用，只有 `shared/` 是共用的。

`common/` 里的文件最先加载，然后 `app.js`，最后 `trip.js` / `customer.js`。
后加载的依赖先加载的全局变量，**调整加载顺序会导致报错**。详见 `docs/themes.md`。

## 单独调试各模块

出行模块可以脱离 Web 服务在终端直接跑：

```bash
python -X utf8 -m cli.guide
```

> Windows 控制台默认 GBK，不加 `-X utf8` 中文可能乱码。

单独检查知识库是否就绪（不启动对话）：

```bash
python -X utf8 -m modules.customer.rag_store
```

单独跑一遍客服的流式封装（用一条固定问题验证 SSE 事件能正常吐出）：

```bash
python -X utf8 -m modules.customer.stream
```

检测检索质量（40 题题库，分原词 / 同义改写 / 跨章节 / 库外四类）：

```bash
python -X utf8 -m modules.customer.rag_eval
```

## 智能客服是怎么工作的

这一段是客服模块自己的说明，方便被问到「智能客服怎么工作」时能直接答。

- **三层检索**：关键词（jieba 分词 + BM25）→ 向量（本机 Ollama + Chroma）→ 混合（分数归一化后按权重相加，取前 4 条）
- **只答知识库里的内容**：检索不到就回「这个问题我在知识库里没有找到相关资料」+ 说明它能回答哪些范围 + 建议怎么继续问
- **不编造**：提示词里写死「回答只能来自参考资料」，不许用模型自己的知识补充
- **不闲聊，但寒暄会引导**：问「你好」「谢谢」这类，回一句「我是 ctOS 的智能客服，只负责回答项目相关的问题……」，不查资料、不调模型；其余闲聊不接，聊天功能由闲聊模块承担
- **不写库**：问答不落数据库，刷新页面就没了
- **能接追问**：前端把最近几轮对话一起带过来，由改写节点把「那它怎么配」
  补成一句自包含的检索查询，再去检索

检索不到资料时**不会调用模型**，直接由代码返回固定拒答话术，几毫秒就回。
判断「不在知识范围」时，会先让检索结果当第二道关：只有模型说库外、检索也没找到强结果，才拒答。

## 技术栈

- **Web**：FastAPI、Uvicorn、Pydantic
- **编排**：LangGraph、LangChain、langchain-openai
- **模型**：DeepSeek（对话与推理）、本机 Ollama qwen3-embedding（客服向量化）
- **工具**：DeepSeek Search 联网搜索、高德地图、Open-Meteo 天气
- **存储**：PostgreSQL 17（会话与出行记录，多租户）；Chroma 存 RAG 向量
- **检索**：jieba + rank-bm25 与向量混合
- **认证**：JWT + bcrypt
- **部署**：uvicorn 直接拉起服务（`python app.py`），线上 <https://ctos2.cn> 由 Cloudflare 提供域名和 HTTPS
- **配置**：python-dotenv

## 常见问题

**为什么客服不跟我闲聊？**（寒暄会回一句引导）
这是刻意设计。客服的职责是「查资料回答问题」，不是聊天。聊天由闲聊模块承担。
不过问「你好」「谢谢」「在吗」这类寒暄时，它会回一句引导语，告诉你该问什么。

**为什么客服总说没找到答案？**
先确认要问的内容是否已经写进 `docs/corpus/` 下的文档；改完文档要重新跑入库脚本并重启服务。
如果文档里有但还答不出，可能是问法差异太大，可以换个说法。

**对话记录会丢吗？**
不会。闲聊、角色扮演和出行都存在 PostgreSQL 数据库 `ctos2` 里，重启服务和刷新页面都还在。
只有智能客服不留记录。

**要注册才能用吗？**
不用。打开 <https://ctos2.cn> 会先自动进入一个**访客空间**（独立租户，记录只存在当前浏览器），
想跨设备保留记录再点侧栏底部「账号登录」注册或登录。每个账号的数据是隔离的，互相看不到。
访客账号的邮箱统一是 `trial_xxx@ctos-trial.local`，可用 `databases/tools/clean.py` 清理。

**线上地址是什么？**
<https://ctos2.cn>，`www.ctos2.cn` 也能访问，两个地址的页面完全一样。

**端口可以改吗？**
可以，用环境变量 `PORT`，前端不用动。也可以直接改 `api/main.py` 末尾 `uvicorn.run(...)` 里的端口。

## 安全说明

- 所有密钥均从 `config/.env` 读取，代码中不写死任何凭据。
- 数据库是 PostgreSQL，密码同样在 `config/.env` 里；默认只监听本机，不对公网开放端口。
- 接口都要登录：所有业务路由都从 `Authorization: Bearer <token>` 解析租户，未登录返回 401。
  例外是 `/auth/*`、`/health`、两个 `ping`、`/notice`、`/feedback` 和静态资源。
- `.gitignore` 已排除 `config/.env`、`*.env`、`venv/`、`__pycache__/`、`*.sql`、`*.db`、向量库目录、测评结果等。
- 若曾误提交密钥，请立即在对应平台轮换（删除文件并不能让密钥失效）。
