# ctOS 2.0 文件职责清单

> **每个文件做什么。** 想知道某段代码在哪，先看这里。
>
> 原则：文件名要能猜出内容；猜不出的，这里写清楚。

---

## 一、根目录

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `README.md` | 182 | 项目说明：线上地址、怎么装、怎么跑、怎么用 |
| `LICENSE` | 17 | MIT 协议 |
| `Dockerfile` | 40 | 怎么把项目打包成镜像（Python 环境、装依赖、启动命令） |
| `docker-compose.yml` | 69 | 怎么把「应用 + 数据库」两个容器组起来跑 |
| `.dockerignore` | 39 | 构建镜像时排除哪些文件（venv、密钥、数据库） |
| `.gitignore` | 73 | 哪些文件不进 git（密钥、数据库、缓存） |

> **配置只有一份**：`config/.env`。根目录不放 `.env`，
> Docker 用 `--env-file config/.env` 指定，代码用 `load_dotenv` 读同一份。

---

## 二、`api/` —— HTTP 接口层

**只做一件事：把 HTTP 请求转成业务调用，返回响应。**

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `main.py` | 192 | **唯一入口**。定义所有路由（`/chat`、`/trip/*`、`/customer/*`、`/sessions`、`/health`），挂载静态文件。每个业务接口都从这里取 `tenant_id` 做隔离。`NoCacheStaticFiles` 给静态文件发 `no-cache`，避免 CDN 缓存旧样式 |
| `routes/auth.py` | 118 | 注册、登录、查当前用户。`current_tenant()` 是所有接口的数据隔离入口 |
| `routes/trial.py` | 71 | **访客账号**：`POST /auth/trial` 自动建访客账号并登录（见下方说明） |

**读代码的顺序**：先看 `main.py` 的路由列表，知道有哪些接口，再按需跳进去。

### `routes/trial.py`：访客账号（可整块删除）

让面试官/访客打开网址就能用的入口。页面首次打开、浏览器里没有 token 时，
前端自动调用 `POST /auth/trial`；登录弹层里的「不登录，直接以访客身份使用」也走这里。
后端新建一个独立账号（统一邮箱 `trial_<16位随机>@ctos-trial.local`）并直接返回 token。

它**不碰任何现有逻辑**：账号走的是 `create_user()`，所以租户隔离、会话读写全部照常工作。

**不需要了怎么删**（三处引用）：

1. `api/main.py`：`from api.routes.trial import ...` 那一行 + `app.include_router(trial_router)` 那一行
2. `static/js/common/auth.js`：`guestLogin()` 和 `ensureSession()` 里的访客分支
3. `static/index.html`：登录弹层里的「不登录，直接以访客身份使用」按钮

删完项目行为和加这个文件之前完全一样。访客账号以后要清理的话：
`DELETE FROM users WHERE email LIKE '%@ctos-trial.local'`。

---

## 三、`core/` —— 跨模块公用

**三个模块都要用的东西。和具体业务无关。**

| 文件 | 行数 | 职责 | 什么时候看 |
| --- | --- | --- | --- |
| `llm.py` | 46 | **全项目唯一的 `get_llm()`**。决定用哪个模型、温度、是否思考 | 想换模型、调温度、加超时 |
| `db.py` | 122 | 数据库连接和通用操作（`query` / `execute` / `transaction`）。也负责 `.env` 加载 | 想知道怎么连库、怎么执行 SQL |
| `auth.py` | 72 | 密码哈希（bcrypt）、JWT 签发与校验 | 改 token 有效期、改密码规则 |
| `sse.py` | 8 | SSE 事件打包（`data: {...}\n\n`） | 改流式输出格式 |

**注意**：`db.py` 里的 `_conninfo()` 用 dict 传参而不是拼 DSN 字符串，因为密码里有反斜杠会出问题。

---

## 四、`databases/` —— 数据表和读写

**每个文件对应一组表。只写 SQL，不写业务逻辑。**

| 文件 | 行数 | 对应的表 | 职责 |
| --- | --- | --- | --- |
| `db_tenant.py` | — | `tenants` | **全局身份表**：建表 + 确保默认租户存在。不属于任何业务模块，users / sessions / trip_* 都外键引用它 |
| `db_auth.py` | 91 | `users` | 用户注册、按邮箱/ID 查人、记录最后登录时间 |
| `db_chat.py` | 112 | `sessions` `messages` | 闲聊会话的增删改查、消息读写（**不再建 tenants**） |
| `db_trip.py` | 218 | `trip_chats` `trip_sessions` `trip_user_inputs` `trip_ai_outputs` | 出行会话、每一轮、用户原话、AI 四段产出 |
| `db_roleplay.py` | — | `role_play_sessions` `role_play_memories` `role_play_roles` | 记录“哪个聊天会话用的是哪个角色”、每个角色记住的事，以及用户自己写的角色 |
| `db_view.py` | 283 | 全部 | **命令行查看工具**，不参与 Web 服务 |
| `clean_db.py` | 300+ | 全部 | **命令行清理工具**：访客账号、某个账号的数据、全部闲聊/出行/反馈 |

**表结构在哪**：每个文件顶部有 `CREATE_*_TABLE` 常量，建表语句就在那儿。

**`db_view.py` 用法**：
```bash
python -X utf8 -m databases.db_view            # 用户 + 会话列表
python -X utf8 -m databases.db_view stats      # 统计
python -X utf8 -m databases.db_view trips      # 出行列表
python -X utf8 -m databases.db_view show 5     # 某个会话的对话
python -X utf8 -m databases.db_view trip 3     # 某个出行会话
python -X utf8 -m databases.db_view search 端口 # 搜关键词
```

**`clean_db.py` 用法**：
```bash
python -X utf8 -m databases.clean_db            # 清理本机 5432
python -X utf8 -m databases.clean_db --docker   # 清理 Docker 5433（8080 页面用的库）
docker exec -it ctos2-app python -m databases.clean_db   # 在容器里清理
```

菜单里可以选：查看现状、清理访客账号、清理某个账号的聊天/出行、删除某个账号、
清理全部闲聊/出行/反馈。删除前会显示条数，并要求输入确认词。

---

## 五、`modules/` —— 三个业务模块

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
| `graph.py` | 12 | 图：`START → chat_node → END`，一条直线 |
| `node.py` | 14 | 唯一节点：拼系统提示词，调一次模型 |
| `state.py` | 5 | 状态：只有 `messages` |
| `prompts.py` | 2 | 系统提示词（就一句话） |
| `stream.py` | 12 | 对外出口 `run_graph()`，逐块吐文本 |
| `sessions.py` | 87 | **会话读写中间层**：在 `db_chat.py` 之上包一层，数据库出错不拖垮聊天 |

---

### `modules/trip/` —— 智能出行（最复杂）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `graph.py` | 48 | 攻略图：`weather → spots_agent ⇄ tools → ask_spots → planner → route_agent` |
| `guide_ask.py` | 28 | 景点清单的暂停节点：收用户的勾选结果，整理成排行程要用的字段 |
| `guide_stream.py` | 401 | 攻略出口：跑图、暂停、确认后继续、跑完问要不要查真实路线 |
| `node.py` | 165 | 攻略四个节点的实现（天气、景点 ReAct 循环、排行程、查路线） |
| `state.py` | 27 | 攻略状态：目的地、天数、四段产出、消息列表 |
| `prompts.py` | 373 | 攻略提示词 + 意图分流提示词 |
| `tools.py` | 362 | **三个外部工具**：`get_weather`（Open-Meteo）、`web_search`（DeepSeek）、`get_directions`（高德） |
| `route.py` | 21 | 攻略条件路由：景点搜够了就去 planner，没够就继续搜 |
| `stream.py` | 189 | 对外出口 `trip_stream()`：分流（路线/攻略/闲聊）→ 线程跑图 → SSE |
| **`understand.py`** | 32 | **需求解析**：判断「这句是路线、攻略还是闲聊」，合并多轮需求 |
| `cli.py` | 93 | **终端调试入口**，只有手动运行才用到（路线决策请在网页用） |
| `route_decision_tools.py` | 675 | 路线数据：地点、驾车、公交、步行、骑行、推荐打分 |
| `route_decision_prompts.py` | 100 | 路线 4 个提示词：解析、对比、推荐、提醒 |
| `route_decision_graph.py` | 265 | 路线决策图：`collect → interrupt → compare → decide → tips` |
| `route_decision_stream.py` | 391 | 路线出口：解析/校验/SSE/暂停恢复/存库 |

**关键细节**：
- `understand.py` 是业务逻辑（被 `stream.py` 用），不是调试代码
- `tools.py` 里 `_city_name_variants()` 处理城市名后缀变体（实测救回 22% 查不到的城市）
- `node.py` 里 `route_agent_node` 的 for 循环是隐藏的 ReAct
- 路线决策的 HITL：图停在 `ask_user`，用 `interrupt` 保存现场；用户选完走 `/trip/route/choose`，用 `Command(resume=...)` 继续
- 暂停现场存在 `databases/route_checkpoints.sqlite`（LangGraph 检查点，运行产物，已 gitignore）

---

### `modules/roleplay/` —— 角色扮演

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `presets.py` | — | 预设角色：名字、性格、说话方式、边界、开场白 |
| `roles.py` | — | 统一找角色：预设从代码找，自定义从数据库找 |
| `openings.py` | — | 从补充说明取开场白；没有就让 AI 生成一句 |
| `search.py` | — | AI 帮我查：联网搜索后整理成角色草稿 |
| `prompts.py` | — | 把角色档案拼成提示词，以及整理记忆的提示词 |
| `stream.py` | — | 角色对话的流式出口 |
| `memory.py` | — | 每 6 轮把对话压缩成 200 字以内的记忆摘要 |

角色扮演复用闲聊的 `sessions` / `messages`，只在 `role_play_sessions` 里记“这个会话是哪个角色”。
改预设角色直接改 `presets.py`，重启服务生效。

---

### `modules/customer/` —— RAG 智能客服

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `graph.py` | 23 | 图：`START → retrieve → generate → END` |
| `node.py` | 76 | 两个节点：三层检索、生成答案。**检索时用「上一轮问题 + 当前问题」拼查询** |
| `state.py` | 13 | 状态：问题、历史、三层命中、答案 |
| `prompts.py` | 23 | 唯一提示词：只许照资料答，查不到就说没找到 |
| `stream.py` | 80 | 对外出口 `customer_stream()` |
| `rag_config.py` | 36 | **配置**：文档目录、向量库目录、embedding 模型、智谱密钥 |
| `rag_store.py` | 69 | 知识库加载（全进程只加载一次）、jieba 分词 |
| `rag_search.py` | 78 | **三层检索**：关键词（BM25）、向量（Chroma）、混合加权 |
| `rag_ingest.py` | 104 | **入库脚本**：读 `data/docs/*.md` → 切块 → 向量化 → 写 Chroma |
| `rag_eval.py` | 184 | **检索测评**：跑 40 题题库，统计命中率 |
| `data/docs/` | — | 知识库源文件（4 个 .md） |
| `data/chroma/` | — | 向量库（运行产物，不进 git） |
| `eval/golden.json` | — | 测评题库（40 题，四类） |

**改了文档要做什么**：重跑 `python -X utf8 -m modules.customer.rag_ingest`，然后重启服务。

---

## 六、`static/` —— 前端

**没有构建步骤，改完刷新浏览器就生效。**

### 页面和样式

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `index.html` | — | 页面结构（登录弹层 + 主界面 + 手机端汉堡按钮 + 主题切换） |
| `css/style.css` | 145 | 模板原样式：光标光晕、呼吸滚动条、全息光幕 |
| `css/modules.css` | — | 模板之外新增：出行卡片、客服气泡、登录弹层、多选操作条，末尾一整段是**手机端适配**（全部包在媒体查询里） |
| `css/theme.css` | — | 三套主题：clean / street / cyber 的变量和组件覆盖 |

主题在右上角「主题」按钮切换，选择存 `localStorage` 的 `ctos_theme`，默认 `clean`。
`index.html` 头部有内联脚本，在 CSS 之前先把 `data-theme` 设好，避免刷新闪一下。

### `js/common/` —— 跨模块公用

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `config.js` | 24 | API 地址、视图顺序、状态文案、打字机参数 |
| `utils.js` | 53 | `$`、`esc`、`now`、`scrollDown`、`getJson`、`bindEnter` |
| `announcement.js` | 64 | **更新公告前端**：从 `GET /notice` 拉内容，记录本浏览器看过的版本 |
| `auth.js` | 154 | token 存取、访客会话引导、登录弹层逻辑、带认证的 fetch |
| `abort.js` | 28 | 请求中断控制（同一时刻只跑一个流） |
| `sse.js` | 57 | SSE 事件解析器 |
| `typer.js` | 128 | 打字机渲染 |
| `selection.js` | 92 | 列表多选删除（闲聊和出行共用） |
| `sticky.js` | 25 | 吸顶高度同步 |
| `aura.js` | 23 | 光标光晕特效 |
| `theme.js` | — | 主题切换、localStorage 记忆、主题菜单 |

### `js/` —— 三个模块

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `app.js` | 1682 | **闲聊 + 角色扮演 + 视图切换 + 启动**。全局 `state` 也定义在这里；末尾有手机端抽屉开关 |
| `trip.js` | 1568 | 出行：四段卡片、进度条、出行记录 |
| `customer.js` | 246 | 客服：一问一答，本地维护上下文 |

---

## 七、`config/` 和 `docs/`

| 文件 | 职责 |
| --- | --- |
| `config/.env` | **所有密钥和连接配置**（不进 git） |
| `config/YOUR_config.env` | 配置模板，告诉别人要填什么 |
| `config/notice.json` | **更新公告**：id、标题、日期、正文、条目；改完刷新页面生效 |
| `config/requirements.txt` | Python 依赖清单 |
| `docs/architecture.md` | 请求地图：用户点一下，代码经过哪些文件 |
| `docs/files.md` | **本文档**：每个文件做什么 |
| `docs/tunnel-check.md` | 线上隧道副本排查、`scripts/check_online.ps1` 使用说明 |
| `docs/deployment.md` | 部署说明：线上实例、Docker、本地运行、上线流程 |
| `eval/cases.json` | 测评题库：32 条，覆盖闲聊/角色/客服/出行/平台 |
| `eval/run_eval.py` | 跑测评、自动检查、生成 JSON + Markdown 报告 |
| `eval/results/` | 每次测评的报告，保留最新一版基线 |
| `eval/README.md` | 怎么跑、怎么加题、怎么读结果 |

---

## 八、常见需求：改这里

| 我想… | 改哪个文件 |
| --- | --- |
| 换模型 / 调温度 | `core/llm.py` |
| 改提示词 | 对应模块的 `prompts.py` |
| 加一个新接口 | `api/main.py` |
| 加一张表 | 新建 `databases/db_xxx.py`，并在 `core/db.py` 的 `create_all_tables()` 里加一行 `("databases.db_xxx", "create_xxx_tables")` |
| 改流式事件格式 | 对应模块的 `stream.py` |
| 加外部工具 | `modules/trip/tools.py` |
| 改前端样式 | `static/css/modules.css` |
| 改前端逻辑 | `static/js/app.js`（闲聊）/ `trip.js` / `customer.js` |
| 改更新公告 | `config/notice.json` |
| 跑 Agent 测评 | `eval/run_eval.py`，题库在 `eval/cases.json` |
| 检查线上隧道 | `scripts/check_online.ps1`，排查步骤见 `docs/tunnel-check.md` |
| 加公用前端函数 | `static/js/common/` 下新建文件，并在 `index.html` 里按顺序引入 |
| 改端口 | 环境变量 `PORT`（容器/线上）/ `api/main.py` 底部（本地） |
| 改数据库连接 | `config/.env` 的 `PG_*` 变量 |
| 上线 / 更新线上 | 见 [deployment.md](deployment.md) 第九节 |

---

## 九、文件行数排行（找最大的文件）

| 文件 | 行数 |
| --- | --- |
| `static/css/modules.css` | 848 |
| `static/js/trip.js` | 616 |
| `static/js/app.js` | 457 |
| `modules/trip/tools.py` | 293 |
| `databases/db_view.py` | 279 |
| `modules/trip/prompts.py` | 271 |
| `databases/db_trip.py` | 212 |
| `docs/architecture.md` | 195 |
| `modules/customer/rag_eval.py` | 188 |
| `modules/trip/stream.py` | 180 |
| `api/main.py` | 164 |
| `static/index.html` | 178 |

**如果一个文件超过 500 行，考虑拆分。** 目前只有两个前端文件超标（`trip.js`、`modules.css`，都是历史积累），后端都在合理范围。
