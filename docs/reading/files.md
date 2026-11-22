# ctOS 2.0 文件职责清单

> **每个文件做什么。** 想知道某段代码在哪，先看这里。
>
> 原则：文件名要能猜出内容；猜不出的，这里写清楚。

---

## 一、根目录

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `README.md` | 239 | 项目说明：线上地址、四个模块、怎么装、怎么跑、怎么用 |
| `LICENSE` | 17 | MIT 协议 |
| `.gitignore` | 76 | 哪些文件不进 git（密钥、产物、向量库、检查点、缓存） |
| `.env` | — | **所有密钥和连接配置**（不进 git）。模板在 `config/.env.example` |
| `requirements.txt` | 24 | Python 依赖清单 |

> **配置只有一份**：根目录的 `.env`。代码用 `load_dotenv` 读它。

---

## 二、`api/` —— HTTP 接口层

**只做一件事：把 HTTP 请求转成业务调用，返回响应。**
每个模块一个路由文件，`main.py` 只负责装配。

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `main.py` | 60 | **只做装配**：建 app、挂静态文件、把 11 个路由 include 进来。`NoCacheStaticFiles` 给静态文件发 `no-cache`，避免 CDN 缓存旧样式 |
| `deps.py` | 46 | **路由们共用**：`tenant_of()`（取租户，数据隔离入口）、`resolve_images()`（校验图片归属）、`sse_headers()`、`clean_text()` |
| `routes/auth.py` | 118 | 注册、登录、查当前用户。`current_tenant()` 是所有接口的数据隔离入口 |
| `routes/trial.py` | 90 | **访客账号**：`POST /auth/trial` 自动建访客账号并登录（见下方说明） |
| `routes/chat.py` | 130 | `/chat`（闲聊 + 角色扮演，按 `role_id` 分流）、`/chat/attachment` 上传/取图 |
| `routes/trip.py` | 104 | `/trip/chat` 唯一入口、`/trip/route/choose`、`/trip/route/place`、`/trip/list`、`/trip/{id}`、批量删除 |
| `routes/guide.py` | 32 | `/guide/spots`（勾完景点继续）、`/guide/ping` |
| `routes/roleplay.py` | 181 | `/roleplay/*`：角色列表/详情/删除/搜索/创建、开始、会话回查、记忆查看/清空 |
| `routes/customer.py` | 28 | `/customer/chat`、`/customer/ping` |
| `routes/sessions.py` | 26 | `/sessions`：列出、读消息、删除（闲聊和角色扮演共用） |
| `routes/presence.py` | 31 | `/presence/ping` 心跳、`/presence/online` 在线人数 |
| `routes/feedback.py` | 65 | `/feedback` 提交反馈（含按 IP 限流） |
| `routes/system.py` | 63 | `/notice` 公告、`/health` 健康检查、`/` 首页入口 |

**读代码的顺序**：先看 `main.py` 的 include 顺序，知道有哪些接口，再按路径第一段跳进对应的 `routes/xxx.py`。

> 接口路径的第一段基本就是文件名，例如 `/roleplay/*` 在 `routes/roleplay.py`。
> 唯一例外：`/chat` 和角色扮演相关但分在两个文件——`routes/chat.py` 管对话本身（含 `role_id` 分支），
> `routes/roleplay.py` 管角色的增删查和记忆。

### `routes/trial.py`：访客账号（可整块删除）

让访客打开网址就能用的入口。页面首次打开、浏览器里没有 token 时，
前端自动调用 `POST /auth/trial`；登录弹层里的「不登录，直接以访客身份使用」也走这里。
后端新建一个独立账号（统一邮箱 `trial_<16位随机>@ctos-trial.local`）并直接返回 token。

它**不碰任何现有逻辑**：账号走的是 `create_user()`，所以租户隔离、会话读写全部照常工作。

**不需要了怎么删**（四处引用）：

1. `api/routes/trial.py`：整个文件
2. `api/main.py`：`from api.routes import (...)` 里去掉 `trial`，并删掉 `app.include_router(trial.router)` 那一行
3. `web/src/shared/auth/authStore.ts`：`guestLogin()` 和 `ensureSession()` 里的访客分支
4. `web/src/shared/auth/AuthDialog.vue`：登录弹层里的「不登录，直接以访客身份使用」按钮

删完项目行为和加这个文件之前完全一样。访客账号以后要清理的话：
`DELETE FROM users WHERE email LIKE '%@ctos-trial.local'`（或跑 `databases.tools.clean`）。

---

## 三、`common/` —— 公共层

**启动入口 + 全局依赖。**

| 文件 | 行数 | 职责 | 什么时候看 |
| --- | --- | --- | --- |
| `main.py` | 35 | **项目总启动入口**：`python -X utf8 -m common.main`。读 HOST/PORT 环境变量，拉起 uvicorn | 改端口、改监听地址、改启动行为 |
| `llm.py` | 33 | **全项目唯一的 `get_llm()`**。决定用哪个模型、温度、是否思考 | 想换模型、调温度、加超时 |

> 其他曾经放在 `common/` 的文件，按「谁在用」归位了：
> - `db.py` → `databases/conn.py`（连数据库属于数据库层）
> - `auth.py` → `api/security.py`（只有接口层用）
> - `sse.py` → `modules/trip/sse.py` + `modules/customer/sse.py`（两个模块各一份）
> - `checkpoints.py` → `modules/trip/checkpoints.py`（只有出行用）

---

## 四、`databases/` —— 数据库层

**每个文件对应一组表。只写 SQL，不写业务逻辑。**
按「公共 / 各模块 / 运维工具」分成三组。

### 连接与建库

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `conn.py` | 160 | **连接 + 通用操作**：`get_conn()` / `query()` / `query_one()` / `execute()` / `transaction()` / `check_connection()`。所有 `db_*.py` 都走它 |
| `schema.sql` | 223 | **所有建表 / 补列 / 索引语句**。13 张表都在这里，全是 `IF NOT EXISTS`，跑在已有数据的库上安全 |
| `schema.py` | 61 | 建库入口：`python -X utf8 -m databases.schema` 执行 schema.sql；也可以直接 `psql -f databases/schema.sql` |

> `conn.py` 里的 `_conninfo()` 用 dict 传参而不是拼 DSN 字符串，因为密码里有反斜杠会出问题。

### `common/` —— 公共部分

| 文件 | 行数 | 对应的表 | 职责 |
| --- | --- | --- | --- |
| `db_tenant.py` | 40 | `tenants` | **全局身份表**：查询租户。不属于任何业务模块，users / sessions / trip_* 都外键引用它 |

### `modules/` —— 各模块独立的表

| 文件 | 行数 | 对应的表 | 职责 |
| --- | --- | --- | --- |
| `db_auth.py` | 110 | `users` | 用户注册（同一事务里建租户 + 用户）、按邮箱/ID 查人、记录最后登录时间 |
| `db_chat.py` | 170 | `sessions` `messages` `message_images` | 闲聊会话、消息、图片附件 |
| `db_trip.py` | 195 | `trip_chats` `trip_sessions` `trip_user_inputs` `trip_ai_outputs` | 出行会话、每一轮、用户原话、AI 四段产出 |
| `db_roleplay.py` | 190 | `role_play_sessions` `role_play_memories` `role_play_roles` | 记录「哪个聊天会话用的是哪个角色」、每个角色记住的事，以及用户自己写的角色 |
| `db_feedback.py` | 90 | `feedback` | 存用户反馈 + 统计（按评价 / 按模块 / 按日期） |

### 建库

| 文件 | 职责 |
| --- | --- |
| `schema.sql` | **所有建表 / 补列 / 索引语句**。13 张表都在这里，全是 `IF NOT EXISTS`，跑在已有数据的库上安全 |
| `schema.py` | 建库入口：`python -X utf8 -m databases.schema` 执行 schema.sql；也可以直接 `psql -f databases/schema.sql` |

**表结构都在 `databases/schema.sql`。** `db_*.py` 只负责增删改查，不再有 `CREATE_*_TABLE` 常量。
加一张表：往 `schema.sql` 加建表语句，再新建 `databases/modules/db_xxx.py` 写增删改查。

### `tools/` —— 运维 CLI（不参与 Web 服务）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `view.py` | 279 | **查看数据**：用户、会话、出行、搜索、统计 |
| `clean.py` | 302 | **清理数据**：访客账号、某个账号的数据、全部闲聊/出行/反馈 |
| `feedback_view.py` | 79 | **查看反馈**（列表 / `stats`），不对外开接口 |

**运行产物（不入 git）**：

| 位置 | 是什么 |
| --- | --- |
| `databases/checkpoints/route_checkpoints.sqlite` | 出行的 LangGraph 暂停现场。路线决策和攻略共用，靠线程号区分（攻略以 `guide-` 开头） |
| `databases/images/` | 用户上传的图片，按租户分目录 |
| `modules/customer/data/chroma/` | 客服的 Chroma 向量库 |

**`tools/view.py` 用法**：
```bash
python -X utf8 -m databases.tools.view            # 用户 + 会话列表
python -X utf8 -m databases.tools.view stats      # 统计
python -X utf8 -m databases.tools.view trips      # 出行列表
python -X utf8 -m databases.tools.view show 5     # 某个会话的对话
python -X utf8 -m databases.tools.view trip 3     # 某个出行会话
python -X utf8 -m databases.tools.view search 端口 # 搜关键词
```

**`tools/feedback_view.py` 用法**：
```bash
python -X utf8 -m databases.tools.feedback_view             # 最近 20 条
python -X utf8 -m databases.tools.feedback_view -n 50       # 最近 50 条
python -X utf8 -m databases.tools.feedback_view --contact   # 只看留了联系方式的
python -X utf8 -m databases.tools.feedback_view stats       # 统计
```

**`tools/clean.py` 用法**：
```bash
python -X utf8 -m databases.tools.clean              # 清 .env 里配的那套库
python -X utf8 -m databases.tools.clean --port 5433  # 清 127.0.0.1:5433 那套库
```

菜单里可以选：查看现状、清理访客账号、清理某个账号的聊天/出行、删除某个账号、
清理全部闲聊/出行/反馈。删除前会显示条数，并要求输入确认词。

---

## 五、`modules/` —— 模块层

目录按**子集 / 并集 / 交集**组织：

```
modules/
├── chat/          闲聊（父）
│   └── roleplay/     └─ 子集：角色扮演（复用闲聊的会话表）
├── trip/          智能出行（父）
│   ├── route/        ├─ 子集：路线规划
│   └── guide/        └─ 子集：旅游攻略
├── customer/      独立：智能客服
└── imagegen/      交集：生图（与 chat/ trip/ 同级，在建）
```

### 每个模块都是同一套结构

```
modules/<模块名>/
├── graph.py       图怎么连（节点和边）
├── node.py        节点里干什么（调模型、调工具）
├── state.py       图的状态定义（TypedDict）
├── prompts.py     所有提示词
└── stream.py      对外出口（转成 SSE/文本流）
```

**改什么地方去哪找**：

| 想改 | 去 |
| --- | --- |
| 流程顺序、加节点 | `graph.py` |
| 某个节点怎么处理 | `node.py` |
| 提示词怎么写 | `prompts.py` |
| 前端收到什么事件 | `stream.py` |
| 状态里有哪些字段 | `state.py` |

---

### `modules/chat/` —— 闲聊

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `graph.py` | 16 | 图：`START → chat_node → END`，一条直线 |
| `node.py` | 18 | 唯一节点：拼系统提示词，调一次模型 |
| `state.py` | 7 | 状态：只有 `messages` |
| `prompts.py` | 4 | 系统提示词（就一句话） |
| `stream.py` | 22 | 对外出口 `run_graph()`，逐块吐文本 |
| `sessions.py` | 225 | **会话读写中间层**：在 `db_chat.py` 之上包一层，数据库出错不拖垮聊天 |
| `attachments.py` | 165 | **图片附件**：存盘（按租户分目录）、取图、转成模型的块数组 |

---

### `modules/chat/roleplay/` —— 角色扮演（闲聊的子集）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `presets.py` | 61 | 预设角色：名字、性格、说话方式、边界、开场白（**代码里的常量**，不进数据库） |
| `roles.py` | 38 | 统一找角色：预设从代码找，自定义从数据库找；`DEFAULT_ROLE_BOUNDARIES` 统一边界 |
| `prompts.py` | 49 | 把角色档案拼成提示词，以及整理记忆的提示词 |
| `stream.py` | 26 | 角色对话的流式出口（温度 0.8） |
| `openings.py` | 50 | 从补充说明取开场白；没有就让 AI 生成一句 |
| `search.py` | 98 | AI 帮我查：联网搜索后整理成角色草稿，**不存库** |
| `memory.py` | 31 | 每 6 轮把对话压缩成 200 字以内的记忆摘要 |

角色扮演**没有自己的图**，直接拼提示词调模型。
它复用闲聊的 `sessions` / `messages`，只在 `role_play_sessions` 里记「这个会话是哪个角色」。
改预设角色直接改 `presets.py`，重启服务生效。

---

### `modules/trip/` —— 智能出行

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `stream.py` | 31 | 模块对外出口：回一句「收到」→ 把同步流程放进工作线程 → 转发事件 |
| `agent.py` | 91 | **服务编排**：跑 Agent 图拿判断，按 answer / route / guide 分派 |
| `graph.py` | 18 | Agent 图：`START → agent → END`（一个节点，和闲聊那张图同构） |
| `node.py` | 95 | Agent 唯一的节点：调一次模型，判断 + 该答的顺手答了 |
| `state.py` | 13 | Agent 状态：`messages`（+ 预留的 node_path / extra_context） |
| `prompts.py` | 46 | Agent 的判断提示词：三个动作、判断要点、示例 |
| `route/` | — | 子集：路线规划，见下面一小节 |
| `guide/` | — | 子集：旅游攻略，见下面一小节 |

**关键细节**：
- 判断和回答合在**一次模型调用**里：要答的那类本来就得生成文字，没必要判一次再答一次
- 判断结论挂在 `AIMessage.additional_kwargs` 上，所以状态仍然只有 `messages`
- 天气问题先查真实数据（`answer_weather`）再交给 Agent 组织语言，不然会编气温
- Agent 图现在**不带检查点**：它不暂停、也不需要跨轮恢复；子图的暂停由子图自己管

> **目录约定**：按子集 / 并集 / 交集组织。
> - **子集**（某模块专有）：收进父模块下面，例如 `modules/trip/route/`
> - **交集**（多个模块都能用）：与父模块同级，例如 `modules/imagegen/`
> - **并集**（所有模块共用）：放 `common/`
>
> 判断依据是**实际依赖**：路线和攻略只被 `trip/agent.py` 调用；角色扮演复用闲聊的会话表且 `chat/` 不反向引用它。

### `modules/trip/route/` —— 路线规划

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `need.py` | 141 | **需求解析**：`parse_route_need(query, history)` 出 JSON、`check_need` 校验、`find_places` 查地点、拼需求确认文本 |
| `graph.py` | 253 | 路线决策图：`collect → interrupt → compare → decide → tips` |
| `stream.py` | 403 | 路线出口：SSE、暂停恢复、存库 |
| `tools.py` | 302 | 推荐打分和排版（不调模型、不发网络请求） |
| `prompts.py` | 178 | 路线 4 个提示词：解析（含 history 合并）、对比、推荐、提醒 |

**关键细节**：
- 需求解析把 `history` 一起喂给模型，所以"改成8点出发"这类补充一次调用就能接上，不用先合并再解析
- `tools.py` 只剩业务判断：跨城只查驾车、带老人不推荐走路、下雨不推荐骑车、按偏好打分
- 路线决策的 HITL：图停在 `ask_user`，用 `interrupt` 保存现场；用户选完走 `/trip/route/choose`，用 `Command(resume=...)` 继续
- 暂停现场由 `modules/trip/checkpoints.py` 统一管（路线和攻略共用一个 sqlite 文件，靠线程号前缀区分）；文件打不开时自动退回内存

### `modules/trip/guide/` —— 旅游攻略

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `graph.py` | 41 | 攻略图：`weather → spots_agent ⇄ tools → ask_spots → planner → advice` |
| `stream.py` | 215 | 出口：开始、暂停、勾完继续、存库 |
| `node.py` | 143 | 四个节点：天气、景点 ReAct 循环、排行程、写游玩建议 |
| `prompts.py` | 231 | 攻略提示词（含"给几行简短介绍"的 DESCRIBE_PROMPT） |
| `state.py` | 34 | 攻略状态：目的地、天数、四段产出、消息列表 |
| `conditions.py` | 15 | 条件路由：景点搜够了就去 planner，没够就继续搜 |
| `ask.py` | 23 | 景点清单的暂停节点 |
| `quick.py` | 36 | 只问天气的快捷回答 + 简短介绍（给「自己答」用） |

**关键细节**：
- 攻略**不碰地图**：没有查逐日路线那一段，需要精确路线时交给路线规划
- 只有一个暂停点（勾景点），勾完一路跑到「游玩建议」再入库
- `resume_guide()` 会校验 `tenant_id`，拿别人的暂停现场续不上
- 进来就说明 Agent 已经判断过该做攻略，这里不再做"走错门"判断

### `tools/` —— 外部数据工具（两个以上模块在用）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `search.py` | 77 | `web_search`：DeepSeek Search，攻略搜景点、角色扮演 AI 帮我查 |
| `imagesproduct.py` | 77 | `imageProduct`：需求 → 提示词 agent → 生图 → 存盘；chat 和 trip 共用 |

> 只有单个模块用的工具不放这里，跟着模块走：
> `modules/trip/amap.py`（高德）、`modules/trip/weather.py`（天气）。


### `modules/customer/` —— RAG 智能客服

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `graph.py` | 58 | 图：`START ─┬→ greet / └→ rewrite → retrieve ─┬→ generate / └→ refuse` |
| `node.py` | 196 | 四个节点：改写+范围判断、检索、生成、寒暄/拒答 |
| `state.py` | 15 | 状态：原问题、历史、改写后的检索句、范围判断、命中、答案 |
| `prompts.py` | 38 | 两份提示词：改写（含范围判断）、回答；外加拒答话术 |
| `stream.py` | 100 | 对外出口 `customer_stream()`；固定话术会补发 TOKEN |
| `rag_config.py` | 38 | **配置**：文档目录、向量库目录、集合名、向量模型与地址 |
| `rag_store.py` | 85 | 知识库加载（全进程只加载一次）、jieba 分词、标题路径 |
| `rag_search.py` | 103 | **三层检索**：关键词（BM25）、向量（Chroma cosine）、加权混合 |
| `rag_ingest.py` | 197 | **入库脚本**：读 `data/docs/*.md` → 切块（带标题路径）→ 向量化 → 写 Chroma |
| `rag_eval.py` | 190 | **检索测评**：跑 40 题题库，统计命中率 |
| `embedding.py` | 87 | 向量化：调本机 Ollama（入库和检索共用这一份） |
| `data/docs/` | — | 知识库源文件（3 个 .md：`README.md`、`ctOS2_manual.md`、`ctOS2_features.md`） |
| `data/chroma/` | — | 向量库（运行产物，不进 git） |
| `eval/golden.json` | — | 测评题库（40 题，四类） |

**改了文档要做什么**：重跑 `python -X utf8 -m modules.customer.rag_ingest`，然后重启服务。

**调参前先测**：`MAX_CHUNK_CHARS`、混合权重、相关性阈值这几个数都是拿
`rag_eval` 的 40 题扫出来的，改之前先跑一遍对比，别凭感觉调。

---

## 六、前端

**前端全在 `web/` 下，源码是 Vue 3 + TypeScript。**

```
web/
├── src/              源码（53 个文件，全部手写）
│   ├── features/     按业务分：chat（含 roleplay）/ trip / customer
│   ├── shared/       共用：api / auth / attachments / components / lib / styles / types
│   ├── App.vue       根组件
│   ├── AppShell.vue  布局骨架（顶栏 + 侧栏）
│   ├── main.ts       挂载 app
│   └── router.ts     路由表
├── dist/             构建产物（npm run build 生成，不进 git）
├── public/           favicon
├── scripts/          接口契约检查 + 假后端
├── index.html        页面骨架
├── vite.config.ts    构建配置（产物输出到 dist/，base 是 /static/）
└── package.json      依赖清单
```

**改完前端必须构建**，否则浏览器看到的还是旧产物：

```powershell
cd web
npm run build        # 输出到 web/dist/
```

**后端怎么提供**：`api/main.py` 把 `web/dist` 挂到 `/static` 前缀，
`api/routes/system.py` 的 `/` 返回 `web/dist/index.html`。

> 线上走 Cloudflare，`.js`/`.css` 会被缓存 4 小时。
> 改完前端要跑 `node scripts/stamp-static.js` 给引用加版本号。

**详细说明见 `docs/frontend.md`。**

---

## 七、根目录 / `config/` / `docs/` / `scripts/`

### 根目录

| 文件 | 职责 |
| --- | --- |
| `.env` | **所有密钥和连接配置**（不进 git） |
| `requirements.txt` | Python 依赖清单（langgraph / langchain 等版本已钉） |

### `config/` —— 配置

改完不用动代码、不用重启的东西放这里。

| 文件 | 职责 |
| --- | --- |
| `.env.example` | 配置模板。复制成根目录的 `.env` 再填自己的值 |
| `notice.json` | **更新公告**：id、标题、日期、正文、条目；改完刷新页面生效 |

### `docs/` `scripts/`

| 文件 | 职责 |
| --- | --- |
| `docs/architecture.md` | 请求地图：用户点一下，代码经过哪些文件 |
| `docs/files.md` | **本文档**：每个文件做什么 |
| `docs/deployment.md` | 部署说明：线上实例、本地运行、环境变量、上线流程 |
| `docs/frontend.md` | 前端怎么组织、怎么构建、怎么验证 |
| `docs/themes.md` | 前端样式：scoped 样式、tokens.css、手机端适配 |
| `docs/design-preview/` | 界面定稿截图 |
| `docs/corpus/` | 客服知识库源文件（RAG 语料） |
| `scripts/check_online.ps1` | 连续访问线上关键资源，判断是否间歇性超时 |
| `scripts/stamp-static.js` | 给构建产物加版本号（防 Cloudflare 4 小时缓存） |

---

## 八、常见需求：改这里

| 我想… | 改哪个文件 |
| --- | --- |
| 换模型 / 调温度 | `common/llm.py` |
| 改提示词 | 对应模块的 `prompts.py` |
| 加一个新接口 | 新建 `api/routes/xxx.py`，再到 `api/main.py` 加一行 `include_router` |
| 加一张表 | 往 `databases/schema.sql` 加建表语句，跑 `python -X utf8 -m databases.schema`；再新建 `databases/modules/db_xxx.py` 写增删改查 |
| 改流式事件格式 | 对应模块的 `stream.py`（打包函数在 `modules/trip/sse.py`） |
| 加外部工具 | 两个以上模块用 → `tools/`；只有单个模块用 → 放那个模块里 |
| 改预设角色 | `modules/chat/roleplay/presets.py`（重启生效） |
| 改记忆规则 | `modules/chat/roleplay/memory.py`（每 6 轮、200 字上限） |
| 改前端样式 | 对应组件的 `<style scoped>`；配色改 `web/src/shared/styles/tokens.css` |
| 改前端逻辑 | `web/src/features/<模块>/`，共用组件在 `web/src/shared/` |
| 改更新公告 | `config/notice.json` |
| 看用户反馈 | `python -X utf8 -m databases.tools.feedback_view` |
| 检查线上是否可访问 | `scripts/check_online.ps1` |
| 加公用前端组件 | `web/src/shared/components/` |
| 改完前端（线上） | `cd web && npm run build`，再跑 `node scripts/stamp-static.js`（防 Cloudflare 4 小时缓存） |
| 改端口 | 环境变量 `PORT` |
| 改数据库连接 | `.env` 的 `PG_*` 变量 |
| 上线 / 更新线上 | 见 `deployment.md` 第六节 |

---

## 九、文件行数排行（找最大的文件）

**前端最大的几个**（`.vue` 文件包含模板 + 脚本 + 样式三部分）：

| 文件 | 行数 |
| --- | --- |
| `web/src/features/chat/SessionList.vue` | 613 |
| `web/src/features/chat/roleplay/RoleFormPanel.vue` | 552 |
| `web/src/features/trip/TripList.vue` | 551 |
| `web/src/features/chat/ChatView.vue` | 495 |
| `web/src/features/trip/TripView.vue` | 473 |

**后端最大的几个**：

| 文件 | 行数 |
| --- | --- |
| `modules/trip/amap.py` | 600 |
| `modules/trip/route/stream.py` | 505 |
| `modules/trip/route/tools.py` | 379 |
| `databases/tools/clean.py` | 368 |

**如果一个文件超过 500 行，考虑拆分。**
注意 `.vue` 文件的行数包含 HTML 和 CSS，不是纯逻辑量。

> 注：这里的行数是按物理行统计的。
> 想重新算：`Get-ChildItem -Recurse -Include *.py | ... Measure-Object -Line`。
