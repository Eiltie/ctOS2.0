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
| `Dockerfile` | 40 | 怎么把项目打包成镜像（Python 环境、装依赖、启动命令） |
| `docker-compose.yml` | 97 | 怎么把「应用 + 数据库」两个容器组起来跑；挂载 static / notice / chroma / checkpoints |
| `.dockerignore` | 43 | 构建镜像时排除哪些文件（venv、密钥、数据库） |
| `.gitignore` | 76 | 哪些文件不进 git（密钥、数据库、向量库、检查点、缓存） |
| `清理数据库-Docker.bat` | 14 | 双击清 Docker 库（5433） |
| `清理数据库-本机.bat` | 14 | 双击清本机库（5432） |

> **配置只有一份**：`config/.env`。根目录不放 `.env`，
> Docker 用 `--env-file config/.env` 指定，代码用 `load_dotenv` 读同一份。

---

## 二、`api/` —— HTTP 接口层

**只做一件事：把 HTTP 请求转成业务调用，返回响应。**

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `main.py` | 777 | **唯一入口**。定义所有路由（`/chat`、`/trip/*`、`/customer/*`、`/roleplay/*`、`/sessions`、`/feedback`、`/notice`、`/health`），挂载静态文件。每个业务接口都从这里取 `tenant_id` 做隔离。`NoCacheStaticFiles` 给静态文件发 `no-cache`，避免 CDN 缓存旧样式 |
| `routes/auth.py` | 156 | 注册、登录、查当前用户。`current_tenant()` 是所有接口的数据隔离入口 |
| `routes/trial.py` | 117 | **访客账号**：`POST /auth/trial` 自动建访客账号并登录（见下方说明） |

**读代码的顺序**：先看 `main.py` 的路由列表，知道有哪些接口，再按需跳进去。

> `main.py` 已经 777 行，比 `docs/files.md` 之前记的 192 行多了四倍多。
> 如果再长，可以考虑把「角色扮演」和「反馈」两块拆成 `api/routes/roleplay.py`、`api/routes/feedback.py`。

### `routes/trial.py`：访客账号（可整块删除）

让访客打开网址就能用的入口。页面首次打开、浏览器里没有 token 时，
前端自动调用 `POST /auth/trial`；登录弹层里的「不登录，直接以访客身份使用」也走这里。
后端新建一个独立账号（统一邮箱 `trial_<16位随机>@ctos-trial.local`）并直接返回 token。

它**不碰任何现有逻辑**：账号走的是 `create_user()`，所以租户隔离、会话读写全部照常工作。

**不需要了怎么删**（三处引用）：

1. `api/main.py`：`from api.routes.trial import ...` 那一行 + `app.include_router(trial_router)` 那一行
2. `static/shared/js/common/auth.js`：`guestLogin()` 和 `ensureSession()` 里的访客分支
3. `static/index.html`：登录弹层里的「不登录，直接以访客身份使用」按钮

删完项目行为和加这个文件之前完全一样。访客账号以后要清理的话：
`DELETE FROM users WHERE email LIKE '%@ctos-trial.local'`（或跑 `clean_db.py`）。

---

## 三、`core/` —— 跨模块公用

**四个模块都要用的东西。和具体业务无关。**

| 文件 | 行数 | 职责 | 什么时候看 |
| --- | --- | --- | --- |
| `llm.py` | 59 | **全项目唯一的 `get_llm()`**。决定用哪个模型、温度、是否思考 | 想换模型、调温度、加超时 |
| `db.py` | 170 | 数据库连接和通用操作（`query` / `execute` / `transaction`），以及建表总入口 `create_all_tables()` | 想知道怎么连库、怎么执行 SQL、怎么加表 |
| `auth.py` | 95 | 密码哈希（bcrypt）、JWT 签发与校验 | 改 token 有效期、改密码规则 |
| `sse.py` | 53 | SSE 事件打包（`data: {...}\n\n`）+ `stream_from_thread()` | 改流式输出格式 |

**注意**：`db.py` 里的 `_conninfo()` 用 dict 传参而不是拼 DSN 字符串，因为密码里有反斜杠会出问题。

**`sse.py` 里有两个东西**：`sse()` 负责打包；`stream_from_thread()` 把同步的 LangGraph
放到工作线程里跑，边跑边把 SSE 字符串送回来，并带 8 秒心跳（防止用户长时间看不到任何字）。

---

## 四、`databases/` —— 数据表和读写

**每个文件对应一组表。只写 SQL，不写业务逻辑。**

| 文件 | 行数 | 对应的表 | 职责 |
| --- | --- | --- | --- |
| `db_tenant.py` | 56 | `tenants` | **全局身份表**：建表 + 确保默认租户存在。不属于任何业务模块，users / sessions / trip_* 都外键引用它 |
| `db_auth.py` | 117 | `users` | 用户注册（同一事务里建租户 + 用户）、按邮箱/ID 查人、记录最后登录时间 |
| `db_chat.py` | 138 | `sessions` `messages` | 闲聊会话的增删改查、消息读写（**不再建 tenants**） |
| `db_trip.py` | 323 | `trip_chats` `trip_sessions` `trip_user_inputs` `trip_ai_outputs` | 出行会话、每一轮、用户原话、AI 四段产出 |
| `db_roleplay.py` | 298 | `role_play_sessions` `role_play_memories` `role_play_roles` | 记录「哪个聊天会话用的是哪个角色」、每个角色记住的事，以及用户自己写的角色 |
| `db_feedback.py` | 135 | `feedback` | 存用户反馈 + 统计（按评价 / 按模块 / 按日期） |
| `db_view.py` | 349 | 全部 | **命令行查看工具**，不参与 Web 服务 |
| `clean_db.py` | 375 | 全部 | **命令行清理工具**：访客账号、某个账号的数据、全部闲聊/出行/反馈 |
| `feedback_view.py` | 118 | `feedback` | **命令行查看反馈**（列表 / `stats`），不对外开接口 |

**表结构在哪**：每个文件顶部有 `CREATE_*_TABLE` 常量，建表语句就在那儿。
**一共 12 张表**，建表顺序由 `core/db.py` 的 `create_all_tables()` 决定（`tenants` 必须最先）。

**运行产物（不入 git）**：

| 位置 | 是什么 |
| --- | --- |
| `databases/checkpoints/route_checkpoints.sqlite` | 出行的 LangGraph 暂停现场。路线决策和攻略共用，靠线程号区分（攻略以 `guide-` 开头） |
| `modules/customer/data/chroma/` | 客服的 Chroma 向量库 |

**`db_view.py` 用法**：
```bash
python -X utf8 -m databases.db_view            # 用户 + 会话列表
python -X utf8 -m databases.db_view stats      # 统计
python -X utf8 -m databases.db_view trips      # 出行列表
python -X utf8 -m databases.db_view show 5     # 某个会话的对话
python -X utf8 -m databases.db_view trip 3     # 某个出行会话
python -X utf8 -m databases.db_view search 端口 # 搜关键词
```

**`feedback_view.py` 用法**：
```bash
python -X utf8 -m databases.feedback_view             # 最近 20 条
python -X utf8 -m databases.feedback_view -n 50       # 最近 50 条
python -X utf8 -m databases.feedback_view --contact   # 只看留了联系方式的
python -X utf8 -m databases.feedback_view stats       # 统计
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

## 五、`modules/` —— 四个业务模块

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
| `sessions.py` | 115 | **会话读写中间层**：在 `db_chat.py` 之上包一层，数据库出错不拖垮聊天 |

---

### `modules/roleplay/` —— 角色扮演（复用闲聊的会话表）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `presets.py` | 61 | 预设角色：名字、性格、说话方式、边界、开场白（**代码里的常量**，不进数据库） |
| `roles.py` | 52 | 统一找角色：预设从代码找，自定义从数据库找；`DEFAULT_ROLE_BOUNDARIES` 统一边界 |
| `prompts.py` | 61 | 把角色档案拼成提示词，以及整理记忆的提示词 |
| `stream.py` | 26 | 角色对话的流式出口（温度 0.8） |
| `openings.py` | 73 | 从补充说明取开场白；没有就让 AI 生成一句 |
| `search.py` | 123 | AI 帮我查：联网搜索后整理成角色草稿，**不存库** |
| `memory.py` | 44 | 每 6 轮把对话压缩成 200 字以内的记忆摘要 |

角色扮演**没有自己的图**，直接拼提示词调模型。
它复用闲聊的 `sessions` / `messages`，只在 `role_play_sessions` 里记「这个会话是哪个角色」。
改预设角色直接改 `presets.py`，重启服务生效。

---

### `modules/trip/` —— 智能出行

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `stream.py` | 20 | 模块对外出口：回一句「收到」→ 把同步流程放进工作线程 → 转发事件 |
| `agent.py` | 92 | **服务编排**：跑 Agent 图拿判断，按 answer / route / guide 分派 |
| `graph.py` | 28 | Agent 图：`START → agent → END`（一个节点，和闲聊那张图同构） |
| `node.py` | 88 | Agent 唯一的节点：调一次模型，判断 + 该答的顺手答了 |
| `state.py` | 19 | Agent 状态：`messages`（+ 预留的 node_path / extra_context） |
| `prompts.py` | 62 | Agent 的判断提示词：三个动作、判断要点、示例 |
| `suggest.py` | 47 | 纯关键词的辅助判断（已经没人用了，下一步删） |
| `capabilities/` | — | 这个模块的**能力**（子图），见下面两小节 |

**关键细节**：
- 判断和回答合在**一次模型调用**里：要答的那类本来就得生成文字，没必要判一次再答一次
- 判断结论挂在 `AIMessage.additional_kwargs` 上，所以状态仍然只有 `messages`
- 天气问题先查真实数据（`answer_weather`）再交给 Agent 组织语言，不然会编气温
- Agent 图现在**不带检查点**：它不暂停、也不需要跨轮恢复；子图的暂停由子图自己管

> **目录约定**：`modules/` 底下每一项都是 ctOS 的一个**模块**（chat / roleplay / trip / customer），
> 层级一致。模块自己的能力和子图放在 `capabilities/` 里，因为只有这个模块用；
> 多个模块共用的（搜索、天气、地图）才放 `core/tools/`。

### `modules/trip/capabilities/route/` —— 路线规划

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `need.py` | 173 | **需求解析**：`parse_route_need(query, history)` 出 JSON、`check_need` 校验、`find_places` 查地点、拼需求确认文本 |
| `graph.py` | 321 | 路线决策图：`collect → interrupt → compare → decide → tips` |
| `stream.py` | 411 | 路线出口：SSE、暂停恢复、存库 |
| `tools.py` | ~320 | 推荐打分和排版（不调模型、不发网络请求） |
| `prompts.py` | ~110 | 路线 4 个提示词：解析（含 history 合并）、对比、推荐、提醒 |

**关键细节**：
- 需求解析把 `history` 一起喂给模型，所以"改成8点出发"这类补充一次调用就能接上，不用先合并再解析
- `tools.py` 只剩业务判断：跨城只查驾车、带老人不推荐走路、下雨不推荐骑车、按偏好打分
- 路线决策的 HITL：图停在 `ask_user`，用 `interrupt` 保存现场；用户选完走 `/trip/route/choose`，用 `Command(resume=...)` 继续
- 暂停现场由 `core/checkpoints.py` 统一管（路线和攻略共用一个 sqlite 文件，靠线程号前缀区分）；文件打不开时自动退回内存

### `modules/trip/capabilities/guide/` —— 旅游攻略

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `graph.py` | 49 | 攻略图：`weather → spots_agent ⇄ tools → ask_spots → planner → advice` |
| `stream.py` | 292 | 出口：开始、暂停、勾完继续、存库 |
| `node.py` | 196 | 四个节点：天气、景点 ReAct 循环、排行程、写游玩建议 |
| `prompts.py` | 273 | 攻略提示词（含"给几行简短介绍"的 DESCRIBE_PROMPT） |
| `state.py` | 48 | 攻略状态：目的地、天数、四段产出、消息列表 |
| `conditions.py` | 22 | 条件路由：景点搜够了就去 planner，没够就继续搜 |
| `ask.py` | 31 | 景点清单的暂停节点 |
| `quick.py` | 55 | 只问天气的快捷回答 + 简短介绍（给「自己答」用） |
| `cli.py` | 118 | **终端调试入口**，跑的是攻略图（路线要暂停选方案，得在网页里用） |

**关键细节**：
- 攻略**不碰地图**：没有查逐日路线那一段，需要精确路线时交给路线规划
- 只有一个暂停点（勾景点），勾完一路跑到「游玩建议」再入库
- `resume_guide()` 会校验 `tenant_id`，拿别人的暂停现场续不上
- 进来就说明 Agent 已经判断过该做攻略，这里不再做"走错门"判断

### `core/tools/` —— 外部数据工具（谁都能用）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `search.py` | 105 | `web_search`：DeepSeek Search，攻略搜景点、角色扮演 AI 帮我查 |
| `weather.py` | 205 | `get_weather`：Open-Meteo，含城市名后缀变体（实测救回 22% 查不到的城市） |
| `amap.py` | ~450 | 高德：`find_place`、驾车/公交/步行/骑行候选、给模型用的 `get_directions` |
| `suggest.py` | 55 | 判断"这句更像路线还是攻略"，纯关键词、不调模型 |
---

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

## 六、`static/` —— 前端

**没有构建步骤，改完刷新浏览器就生效。**
但线上走 Cloudflare，改完要跑 `node scripts/stamp-static.js` 加版本号。
主题结构细节见 `docs/themes.md`。

```
static/
├── index.html      入口页：读偏好 + 判断屏幕宽度 → 跳 themeA 或 themeB
├── themeA/         经典版（左侧栏 + 气泡对话）
├── themeB/         指挥台版（图标导轨 + 右侧控制台），仅宽屏
└── shared/         两套共用：prefs / presence / config / auth / sse / 图片
```

### 入口页

| 文件 | 职责 |
| --- | --- |
| `index.html` | 只做分流：读 `ctos_layout` 偏好 + 判断屏幕宽度，用 `location.replace()` 跳转。**手机端强制 themeA** |

### `themeA/` —— 经典版（3 种风格）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `index.html` | — | 页面结构（登录弹层 + 主界面 + 手机端汉堡按钮 + 主题/风格菜单 + 公告 + 反馈） |
| `css/style.css` | 168 | 模板原样式：光标光晕、呼吸滚动条、全息光幕 |
| `css/modules.css` | 3843 | 模板之外新增的全部组件样式 |
| `css/theme.css` | 1973 | 三套风格的变量定义与组件覆盖 |
| `css/ui.css` | 3237 | 视觉层：圆角、阴影、气泡、排版细化 |
| `css/theme-ui.css` | — | 「主题 / 风格」两个菜单 |
| `css/presence.css` | — | 侧栏底部在线人数 |
| `css/mobile.css` | — | **手机端适配**，最后加载，≤768px 生效 |

脚本见下方 `themeA/js/`。

### `themeB/` —— 指挥台版（2 种风格）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `index.html` | — | 页面结构；窄屏会自检并送回 themeA |
| `css/base.css` | 168 | 复用旧版布局骨架（自 themeA 复制） |
| `css/components.css` | — | 复用旧版弹窗/组件类（自 themeA 复制） |
| `css/style.css` | 2449 | 指挥台版自己的版式 |
| `css/theme-light.css` | 1038 | 两套风格的配色令牌 |
| `js/console.js` | 833 | 右侧控制台：目录、操作日志、系统负载 |
| `js/theme-ui.js` | — | 浮动面板形式的主题/风格切换 |

其余脚本与 themeA 同名同源（各一份副本）。

### `shared/js/common/` —— 两套共用

| 文件 | 职责 |
| --- | --- |
| `prefs.js` | **主题/风格偏好**：读写、`isDesktop()` 屏幕判断、手机端锁定经典版 |
| `presence.js` | **在线人数**：心跳 `POST /presence/ping` + 拉取 `GET /presence/online` |
| `config.js` | API 地址、视图顺序、状态文案 |
| `utils.js` | `$`、`esc`、`now`、`scrollDown`、`getJson`、`bindEnter` |
| `announcement.js` | 更新公告：从 `GET /notice` 拉内容，记录本浏览器看过的版本 |
| `auth.js` | token 存取、访客会话引导、登录弹层逻辑、带认证的 fetch |
| `abort.js` | 请求中断控制（同一时刻只跑一个流） |
| `sse.js` | SSE 事件解析器 |
| `typer.js` | 打字机渲染 |

### `themeA/js/` —— 三个页面标签

两套主题各有一份同名副本；下表以 themeA 为准。

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `app.js` | 1745 | **闲聊 + 角色扮演 + 视图切换 + 启动**。全局 `state` 也定义在这里 |
| `trip.js` | 7 | 出行入口占位（只剩加载顺序说明，没有逻辑） |
| `trip/base.js` | 1721 | 出行壳子 + 全部界面逻辑：进度条、SSE、四段卡片、计时、记录列表、三种等待面板 |
| `trip/route.js` | 464 | 路线那两个等待面板：地点歧义、候选路线 |
| `trip/guide.js` | — | 攻略的景点卡片墙和勾景点面板 |
| `customer.js` | — | 客服：一问一答，本地维护最近 3 轮上下文 |
| `common/theme-ui.js` | — | 「主题 / 风格」菜单渲染与切换 |
| `common/presence-ui.js` | — | 侧栏底部在线人数 |
| `common/aura.js` / `sticky.js` / `selection.js` / `feedback.js` | — | 光晕特效 / 吸顶同步 / 列表多选 / 反馈弹窗 |

> 出行前端**没有"模式"了**：界面按每一轮实际返回了什么来画
> （收到 `START` 的 `mode` 才切进度条，收到 `STEP/DONE` 的 `key` 才建段落）。

---

## 七、`config/` `docs/` `eval/` `tests/` `scripts/`

| 文件 | 职责 |
| --- | --- |
| `config/.env` | **所有密钥和连接配置**（不进 git） |
| `config/YOUR_config.env` | 配置模板，告诉别人要填什么 |
| `config/notice.json` | **更新公告**：id、标题、日期、正文、条目；改完刷新页面生效 |
| `config/requirements.txt` | Python 依赖清单（langgraph / langchain 等版本已钉） |
| `config/requirements-dev.txt` | 开发和测试依赖（= requirements.txt + pytest） |
| `pytest.ini` | pytest 配置：只扫 `tests/`，不扫 `eval/` |
| `.github/workflows/test.yml` | CI：push 到 main 或开 PR 时自动跑 `tests/` |
| `docs/architecture.md` | 请求地图：用户点一下，代码经过哪些文件 |
| `docs/files.md` | **本文档**：每个文件做什么 |
| `docs/deployment.md` | 部署说明：线上实例、Docker、本地运行、上线流程 |
| `docs/themes.md` | 两套主题 / 五种风格的结构、手机端规则、加主题的做法 |
| `docs/imagegen.md` | 生图模块（在建，尚未接入路由） |
| `docs/tunnel-check.md` | 线上隧道副本排查、`scripts/check_online.ps1` 使用说明 |
| `eval/cases.json` | 端到端测评题库：36 条，覆盖闲聊/角色/客服/出行/平台 |
| `eval/run_eval.py` | 跑测评、自动检查、生成 JSON + Markdown 报告 |
| `eval/results/` | 每次测评的报告，保留最新一版基线 |
| `eval/README.md` | 怎么跑、怎么加题、怎么读结果 |
| `tests/conftest.py` | 给测试进程补一个 `JWT_SECRET_KEY`，不依赖 `config/.env` |
| `tests/test_auth.py` | token 往返 / 防篡改 / 密码哈希（挡多租户串号） |
| `tests/test_trip_rules.py` | 天气意图、偏好归一、需求检查、打分与推荐、卡片排版 |
| `tests/test_customer_retrieval.py` | 客服：切块、改写解析、寒暄判定、拒答分派、引用格式 |
| `tests/test_typer_frontend.py` | 打字机：跑真实 `typer.js`，防文字重复/漏字（需要 node） |
| `scripts/check_online.ps1` | 连续访问线上关键资源，判断是否间歇性超时 |

---

## 八、常见需求：改这里

| 我想… | 改哪个文件 |
| --- | --- |
| 换模型 / 调温度 | `core/llm.py` |
| 改提示词 | 对应模块的 `prompts.py` |
| 加一个新接口 | `api/main.py`（或新建 `api/routes/xxx.py`） |
| 加一张表 | 新建 `databases/db_xxx.py`，并在 `core/db.py` 的 `create_all_tables()` 里加一行 `("databases.db_xxx", "create_xxx_tables")` |
| 改流式事件格式 | 对应模块的 `stream.py`（打包函数在 `core/sse.py`） |
| 加外部工具 | `core/tools/`（搜索 / 天气 / 地图各一个文件） |
| 改预设角色 | `modules/roleplay/presets.py`（重启生效） |
| 改记忆规则 | `modules/roleplay/memory.py`（每 6 轮、200 字上限） |
| 改前端样式 | `static/themeA/css/modules.css`（颜色改 `theme.css`）；指挥台版改 `static/themeB/css/style.css` |
| 改前端逻辑 | `static/themeA/js/app.js` / `trip.js` / `customer.js`（两套各一份） |
| 改更新公告 | `config/notice.json` |
| 跑端到端测评 | `eval/run_eval.py`，题库在 `eval/cases.json` |
| 跑单元测试 | `venv\Scripts\python.exe -m pytest`（约 5 秒，不连库不调模型） |
| 改了规则导致测试红 | 补到 `tests/test_trip_rules.py` 或 `tests/test_auth.py` 的对应断言 |
| 看用户反馈 | `python -X utf8 -m databases.feedback_view` |
| 检查线上隧道 | `scripts/check_online.ps1`，排查步骤见 `docs/tunnel-check.md` |
| 加公用前端函数 | `static/shared/js/common/` 下新建文件，并在两套的 `index.html` 里按顺序引入 |
| 改主题 / 风格 | 见 `docs/themes.md` |
| **改完前端（线上）** | **必须跑 `node scripts/stamp-static.js`**，否则 Cloudflare 的 4 小时缓存会让用户看不到改动 |
| 改端口 | 环境变量 `PORT`（容器/线上）/ `api/main.py` 底部（本地） |
| 改数据库连接 | `config/.env` 的 `PG_*` 变量 |
| 上线 / 更新线上 | 见 `deployment.md` 第九节 |

---

## 九、文件行数排行（找最大的文件）

| 文件 | 行数 |
| --- | --- |
| `static/themeA/css/modules.css` | 3843 |
| `static/themeA/css/ui.css` | 3237 |
| `static/themeB/css/style.css` | 2449 |
| `static/themeA/css/theme.css` | 1973 |
| `static/themeA/js/app.js` | 1745 |
| `static/themeA/js/trip/base.js` | 1721 |
| `static/themeB/css/theme-light.css` | 1038 |
| `api/main.py` | 866 |
| `static/themeB/js/console.js` | 833 |
| `core/tools/amap.py` | 600 |
| `modules/trip/capabilities/route/stream.py` | 505 |
| `eval/run_eval.py` | 478 |
| `static/themeA/js/trip/route.js` | 464 |

**如果一个文件超过 500 行，考虑拆分。** 目前超标的集中在样式表和前端大文件；
后端业务模块拆分之后大多在 400 行以内。
