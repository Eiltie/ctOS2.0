# ctOS 2.0 文件职责清单

> **每个文件做什么。** 想知道某段代码在哪，先看这里。
>
> 原则：文件名要能猜出内容；猜不出的，这里写清楚。

---

## 一、根目录

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `README.md` | 241 | 项目说明：怎么装、怎么跑、怎么用 |
| `LICENSE` | 17 | MIT 协议 |
| `Dockerfile` | 48 | 怎么把项目打包成镜像（Python 环境、装依赖、启动命令） |
| `docker-compose.yml` | 78 | 怎么把「应用 + 数据库」两个容器组起来跑 |
| `.dockerignore` | 45 | 构建镜像时排除哪些文件（venv、密钥、数据库） |
| `.gitignore` | 78 | 哪些文件不进 git（密钥、数据库、缓存） |

> **配置只有一份**：`config/.env`。根目录不放 `.env`，
> Docker 用 `--env-file config/.env` 指定，代码用 `load_dotenv` 读同一份。

---

## 二、`api/` —— HTTP 接口层

**只做一件事：把 HTTP 请求转成业务调用，返回响应。**

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `main.py` | 164 | **唯一入口**。定义所有路由（`/chat`、`/trip/*`、`/customer/*`、`/sessions`、`/health`），挂载静态文件。每个业务接口都从这里取 `tenant_id` 做隔离 |
| `routes/auth.py` | 118 | 注册、登录、查当前用户。`current_tenant()` 是所有接口的数据隔离入口 |

**读代码的顺序**：先看 `main.py` 的路由列表，知道有哪些接口，再按需跳进去。

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
| `db_view.py` | 283 | 全部 | **命令行查看工具**，不参与 Web 服务 |

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
| `graph.py` | 28 | 图：`weather → spots_agent ⇄ tools → planner → route_agent` |
| `node.py` | 124 | 四个节点的实现（天气、景点 ReAct 循环、排行程、查路线） |
| `state.py` | 15 | 状态：目的地、天数、四段产出、消息列表 |
| `prompts.py` | 267 | **6 个提示词**：需求解析、天气总结、景点、行程、路线、对话理解 |
| `tools.py` | 288 | **三个外部工具**：`get_weather`（Open-Meteo）、`web_search`（DeepSeek）、`get_directions`（高德） |
| `route.py` | 10 | 条件路由：景点搜够了就去 planner，没够就继续搜 |
| `stream.py` | 175 | 对外出口 `trip_stream()`，把图的事件转成 7 种 SSE |
| **`understand.py`** | 28 | **需求解析**：判断「这句是出行需求还是闲聊」，合并多轮需求 |
| `cli.py` | 73 | **终端调试入口**，只有手动运行才用到 |

**关键细节**：
- `understand.py` 是业务逻辑（被 `stream.py` 用），不是调试代码
- `tools.py` 里 `_city_name_variants()` 处理城市名后缀变体（实测救回 22% 查不到的城市）
- `node.py` 里 `route_agent_node` 的 for 循环是隐藏的 ReAct

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
| `index.html` | 164 | 页面结构（登录页 + 主界面） |
| `css/style.css` | 145 | 模板原样式：光标光晕、呼吸滚动条、全息光幕 |
| `css/modules.css` | 619 | 模板之外新增：出行卡片、客服气泡、登录页、多选操作条 |

### `js/common/` —— 跨模块公用

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `config.js` | 24 | API 地址、视图顺序、状态文案、打字机参数 |
| `utils.js` | 53 | `$`、`esc`、`now`、`scrollDown`、`getJson`、`bindEnter` |
| `auth.js` | 154 | token 存取、登录页逻辑、带认证的 fetch |
| `abort.js` | 28 | 请求中断控制（同一时刻只跑一个流） |
| `sse.js` | 57 | SSE 事件解析器 |
| `typer.js` | 128 | 打字机渲染 |
| `selection.js` | 92 | 列表多选删除（闲聊和出行共用） |
| `sticky.js` | 25 | 吸顶高度同步 |
| `aura.js` | 23 | 光标光晕特效 |

### `js/` —— 三个模块

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `app.js` | 433 | **闲聊 + 视图切换 + 启动**。全局 `state` 也定义在这里 |
| `trip.js` | 645 | 出行：四段卡片、进度条、出行记录 |
| `customer.js` | 145 | 客服：一问一答，本地维护上下文 |

### 开发工具

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `_selftest.html` | 154 | 前端自检页：检查所有函数是否就绪 |
| `_selftest_sidebar.html` | 60 | 侧栏切换验证页 |

**访问**：`http://127.0.0.1:8080/static/_selftest.html`

---

## 七、`config/` 和 `docs/`

| 文件 | 职责 |
| --- | --- |
| `config/.env` | **所有密钥和连接配置**（不进 git） |
| `config/YOUR_config.env` | 配置模板，告诉别人要填什么 |
| `config/requirements.txt` | Python 依赖清单 |
| `docs/architecture.md` | 请求地图：用户点一下，代码经过哪些文件 |
| `docs/files.md` | **本文档**：每个文件做什么 |
| `docs/deployment.md` | Docker 部署详细说明 |

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
| 加公用前端函数 | `static/js/common/` 下新建文件，并在 `index.html` 里按顺序引入 |
| 改端口 | 环境变量 `PORT`（容器）/ `api/main.py` 底部（本地） |
| 改数据库连接 | `config/.env` 的 `PG_*` 变量 |

---

## 九、文件行数排行（找最大的文件）

| 文件 | 行数 |
| --- | --- |
| `static/js/trip.js` | 645 |
| `static/css/modules.css` | 619 |
| `static/js/app.js` | 433 |
| `modules/trip/tools.py` | 288 |
| `databases/db_view.py` | 283 |
| `modules/trip/prompts.py` | 267 |
| `README.md` | 241 |
| `databases/db_trip.py` | 218 |
| `docs/architecture.md` | 193 |
| `modules/customer/rag_eval.py` | 184 |
| `modules/trip/stream.py` | 175 |
| `static/README.md` | 172 |
| `api/main.py` | 164 |
| `static/index.html` | 164 |

**如果一个文件超过 500 行，考虑拆分。** 目前只有两个前端文件超标（都是历史积累），后端都在合理范围。
