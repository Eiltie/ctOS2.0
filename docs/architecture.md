# ctOS 2.0 请求地图

> 这份文档回答一个问题：**用户点一下，代码会依次经过哪些文件？**
>
> 加新模块时回来更新这张图；看不懂某段代码时，先在这里找它属于哪个环节。

---

## 一、全局：一个 app 装四个模块

### 目录结构

```
ctOS2.0/
├── api/
│   ├── main.py            ← 唯一入口，所有业务路由都在这里
│   └── routes/
│       ├── auth.py        ← 认证路由 /auth/*
│       └── trial.py       ← 访客账号 POST /auth/trial（可整块删）
├── core/                  ← 跨模块共用
│   ├── llm.py             ← 唯一的 get_llm()
│   ├── sse.py             ← sse() 打包 + stream_from_thread()
│   ├── auth.py            ← 密码哈希 + JWT
│   └── db.py              ← 开连接 + 建表总入口
├── databases/             ← 各模块的表和增删改查
│   ├── db_tenant.py       ← 全局身份表 tenants（谁都不依赖它，它也不依赖谁）
│   ├── db_auth.py         ← 账号 users
│   ├── db_chat.py         ← sessions / messages
│   ├── db_trip.py         ← 出行的 4 张表
│   ├── db_roleplay.py     ← 角色扮演的 3 张表
│   ├── db_feedback.py     ← feedback
│   ├── db_view.py         ← 命令行查看工具
│   ├── clean_db.py        ← 命令行清理工具
│   └── feedback_view.py   ← 命令行查看反馈
│   （数据在 PostgreSQL 里，不在仓库中；线上在 ctos2-db 容器的命名卷 ctos2-pgdata）
│   （databases/checkpoints/ 是出行的暂停现场，运行产物，不入 git）
├── modules/
│   ├── chat/              ← 闲聊（graph/node/state/prompts/stream/sessions）
│   ├── roleplay/          ← 角色扮演（roles/presets/prompts/stream/search/memory/openings）
│   ├── trip/              ← 出行
│   │   ├── 攻略：graph/node/state/prompts/tools/route/guide_ask/guide_stream
│   │   ├── 路线决策：route_decision_tools/prompts/graph/stream
│   │   └── 分流/出口：understand.py、stream.py、cli.py
│   └── customer/          ← 客服（graph/node/state/prompts/stream + rag_* + data/）
├── static/                ← 前端（无构建步骤）
├── docs/                  ← 本文档
├── eval/                  ← 端到端测评
├── config/                ← .env、requirements.txt、notice.json
├── Dockerfile             ← 镜像怎么打
└── docker-compose.yml     ← app + db 两个容器怎么起来（线上就是这套）
```

### 请求流向

```
浏览器 static/index.html   （本地 127.0.0.1:8080 / 线上 https://ctos2.cn）
        │
        ▼
api/main.py          ← 唯一入口，所有路由都在这里
   │  ↑ 每个业务请求先进 auth，从 token 取出 tenant_id
   │
   ├─ POST /auth/trial ──→ 访客账号（页面首次打开自动调用）
   ├─ POST /chat      ──→ 闲聊 / 角色扮演   纯文本流
   ├─ POST /trip/chat ──→ 出行              SSE 事件流
   └─ POST /customer/chat ─→ 客服           SSE 事件流
```

**先记住这张图**，下面四节是每一条链路的展开。

---

## 二、闲聊链路（最简单，建议从这里读起）

```
POST /chat（不带 role_id）
   │
   ├─ resolve_session()        modules/chat/sessions.py  没有会话就新建（标题取前 14 字）
   ├─ load_history()           modules/chat/sessions.py  取最近 10 条
   │
   ├─ run_graph()              modules/chat/stream.py    ← 模块对外唯一出口
   │     └─ 图：START → chat_node → END
   │          └─ ctOS_chat_node()   modules/chat/node.py（函数名和文件名对不上，就是这个文件）
   │                └─ 系统提示词    modules/chat/prompts.py
   │                └─ get_llm(temperature=0.7)  core/llm.py
   │
   └─ 跑完后才存库
        ├─ save_user_message()  modules/chat/sessions.py
        └─ save_ai_reply()      modules/chat/sessions.py
             └─ add_message()   databases/db_chat.py → 表 messages
```

**数据落在哪**：`sessions`（会话）+ `messages`（消息）

**读这里的顺序**：`modules/chat/stream.py`（22 行，看懂出口）→ `modules/chat/graph.py`（16 行，看懂图）→ `modules/chat/node.py`（18 行，看懂节点）

---

## 三、角色扮演链路（复用闲聊的会话，不走图）

最关键的一点：**角色扮演没有自己的 LangGraph 图**。它把「角色档案拼成的系统提示词 + 历史 + 这一句」
直接交给模型流式输出，会话和消息复用闲聊的 `sessions` / `messages`。

```
① 选角色（前端）
   ├─ GET /roleplay/roles        列出预设 + 自己写的
   │     └─ all_roles()          modules/roleplay/roles.py
   │           ├─ 预设    modules/roleplay/presets.py（代码常量）
   │           └─ 自定义  databases/db_roleplay.py → 表 role_play_roles
   │
   └─ POST /roleplay/start       开始一个角色会话
         ├─ get_role()             modules/roleplay/roles.py
         ├─ resolve_session()      modules/chat/sessions.py   建一个普通会话
         ├─ link_role_session()    databases/db_roleplay.py → 表 role_play_sessions
         └─ save_ai_reply(开场白)  modules/chat/sessions.py

② 对话
   POST /chat（带 role_id）
     └─ role_play_stream()        modules/roleplay/stream.py
           ├─ build_role_prompt()  modules/roleplay/prompts.py（档案 + 记忆）
           ├─ get_memory()         databases/db_roleplay.py → 表 role_play_memories
           └─ get_llm(temperature=0.8)

③ 记忆（后台异步，不让用户等）
   每聊满 6 轮 → asyncio.create_task(refresh_memory())
     └─ modules/roleplay/memory.py
           ├─ build_summary_prompt()  modules/roleplay/prompts.py
           ├─ 调模型压缩成 200 字以内
           └─ save_memory()           databases/db_roleplay.py（覆盖旧摘要）

④ 开场白  modules/roleplay/openings.py
   ├─ split_opening()   用户写了「开场白：xxx」就取这段
   └─ make_opening()    没写就让模型按人设说一句

⑤ AI 帮我查  POST /roleplay/roles/search
   └─ search_role()   modules/roleplay/search.py
         ├─ web_search()    modules/trip/tools.py（复用出行的搜索工具）
         └─ 模型整理成档案草稿，**不存库**，用户确认后才走 ⑥

⑥ 保存角色  POST /roleplay/roles
   └─ create_custom_role()  databases/db_roleplay.py → 表 role_play_roles
         id 形如 custom_12，source 区分 custom / ai_search
```

**数据落在哪**：`sessions` / `messages`（和闲聊共用）+ `role_play_sessions` + `role_play_memories` + `role_play_roles`

**几个约定**：

- 同一个会话不能换角色：用错角色去聊返回 400，会话不属于你返回 404
- 记忆**按角色**存，不按会话——同一角色换会话也记得上次聊过什么
- 记忆是覆盖式的，不会越写越长；清空是**全清**，不做逐条删除
- 自定义角色的「不会做什么」统一用 `DEFAULT_ROLE_BOUNDARIES`，不让用户自己填
- 删自定义角色会连带删掉它的聊天记录和记忆（`delete_custom_role()` 里用了一个事务）

**读这里的顺序**：
1. `modules/roleplay/roles.py`（角色从哪来、边界规则）
2. `modules/roleplay/stream.py`（对话怎么拼提示词、怎么流式吐）
3. `modules/roleplay/memory.py`（记忆怎么更新）

---

## 四、出行链路（两个分支：路线决策 / 旅游攻略）

### 4.1 先看分流

```
POST /trip/chat
   │
   └─ trip_stream()             modules/trip/stream.py  （先发一条 SAY「收到…」）
        ├─ _is_weather_query()  只问天气 → 直接跑 weather_node，发 CHAT，结束
        └─ understand_query()   modules/trip/understand.py
             ├─ CHAT   → 直接回一句，存库，结束
             ├─ ROUTE  → 路线决策（见 4.2）
             └─ TRAVEL → 旅游攻略（见 4.3）
```

> 分流和图都是同步调用，统一交给 `core/sse.py` 的 `stream_from_thread()` 放到工作线程里跑。
> 同步代码留在事件循环里会让 SSE 被整体缓冲，浏览器白屏到整个流程结束。

### 4.2 路线决策（伪导航 + 人工选方案）

```
POST /trip/chat
   │
   └─ start_route_decision()    modules/trip/route_decision_stream.py
        ├─ 解析需求  parse_route_need()    调 LLM 出 JSON
        ├─ 查地点    find_place()          高德地理编码，城市/类型校验
        ├─ 查天气    get_weather()         Open-Meteo
        ├─ 查候选    route_graph           modules/trip/route_decision_graph.py
        │     ├─ collect_routes   查驾车/公交/步行/骑行（route_decision_tools.py）
        │     ├─ ask_user         interrupt() 暂停，等用户选方案
        │     ├─ compare_routes   写对比
        │     ├─ decide_route     写推荐理由
        │     └─ write_tips       写出发提醒
        └─ 存库      save_trip_turn(..., "ROUTE")
```

**人工干预（HITL）**：

- 地点有歧义时先发 `ASK_PLACE`，让用户点一个候选，不会反复追问。
- 候选路线出来后，图会停在 `ask_user`，后端发 `ASK` 事件，前端显示候选按钮。
- 用户点一条后，前端 POST `/trip/route/choose`，后端用 `Command(resume=choice_id)` 接着跑。
- 暂停状态存在 `databases/checkpoints/route_checkpoints.sqlite`（LangGraph 检查点，运行产物，已 gitignore）。
  这个文件打不开时 `make_checkpointer()` 自动退回 `MemorySaver`，不影响其他模块。
- 服务重启后，没选完的暂停仍然能接着选。

**数据落在哪**：`trip_ai_outputs` 的 `route_need`、`route_compare`、`route_decision`、`route_tips` 四列；
`trip_sessions.turn_kind = 'ROUTE'`。

**老库升级**：跑一次 `python -X utf8 -m core.db`。`db_trip.py` 里的 `route_columns_ready()`
会在第一次存库前检查这几列在不在；不在时旧模块仍能存，只是路线轮次不存历史，不会拖垮攻略/闲聊。

### 4.3 旅游攻略（原流程 + 两个暂停点）

```
POST /trip/chat
   │
   └─ start_guide()             modules/trip/guide_stream.py
        ├─ 跑图  guide_graph      modules/trip/graph.py
        │     ├─ weather          解析需求 + 查天气
        │     ├─ spots_agent      搜景点（ReAct 循环）
        │     ├─ ask_spots        interrupt() 暂停：用户勾掉/补充景点
        │     ├─ planner          按用户的调整排行程
        │     └─ route_agent      写详细路线
        │
        ├─ 暂停时发 ASK_SPOTS，用户点确认后 POST /trip/guide/spots
        │     └─ resume_guide()   Command(resume=...) 继续排行程
        │
        ├─ 跑完发 ASK_ROUTE，用户选择后 POST /trip/guide/route
        │     ├─ 要查 → check_guide_route() 高德查每天相邻站点
        │     └─ 不查 → finish_guide() 直接存库
        │
        └─ 存库  save_trip_turn(..., "TRAVEL")
```

**两个暂停点**：

1. 景点清单出来之后停住，用户可以勾掉不想去的、补一个想去的；
   “必须去掉”和“用户想补充”会明确写进排行程的提示词。
2. 攻略写完后问“要不要按真实路线查每天的移动”，选了才去查，
   结果作为第 5 段「真实路线」（`guide_route`）单独显示。

**逐段产出细节**：

```
              ├─ ① 分流  understand_query()   modules/trip/understand.py
              │      调一次 LLM，看这句是 ROUTE / TRAVEL 还是 CHAT
              │
              ├─ ② 回显  yield START（带 mode=TRAVEL）
              │
              ├─ ③ 跑图  guide_graph.stream()
              │      图结构定义：modules/trip/graph.py
              │      ├─ weather      modules/trip/node.py
              │      │     └─ 调 LLM 解析需求（出 JSON，这段不流给用户）
              │      │     └─ get_weather()    modules/trip/tools.py → Open-Meteo
              │      │     └─ 调 LLM 写天气总结
              │      ├─ spots_agent  modules/trip/node.py
              │      │     └─ ReAct 循环：要搜就 bind_tools
              │      │           ├─→ tools (ToolNode) → web_search() → DeepSeek Search
              │      │           └─→ 搜够了直接出景点清单
              │      │     循环上限：MAX_SEARCH=3（modules/trip/node.py）
              │      │     路由判断：should_continue()  modules/trip/route.py
              │      ├─ planner      modules/trip/node.py  把景点排成逐日行程
              │      └─ route_agent  modules/trip/node.py
              │            └─ for 循环藏在这个函数里（MAX_ROUTE_ROUNDS=8）
              │            └─ get_directions() modules/trip/tools.py → 高德
              │
              └─ ④ 存库  save_trip_turn()   databases/db_trip.py
                         一次事务写三张表：
                           trip_sessions（本轮）
                           trip_user_inputs（用户原话）
                           trip_ai_outputs（四段产出）
```

**数据落在哪**：`trip_chats`（会话）+ `trip_sessions`（每轮）+ `trip_user_inputs` + `trip_ai_outputs`。
路线决策也用同一套表，只是 `trip_ai_outputs` 多出 4 列（见 4.2）。
攻略“查真实路线”那一段目前只在结果里显示，不单独入库。

**提示词在哪**：攻略提示词在 `modules/trip/prompts.py`；路线提示词在 `modules/trip/route_decision_prompts.py`。

**读攻略的顺序**：
1. `modules/trip/graph.py`（**这张图就是攻略的全部逻辑**）
2. `modules/trip/guide_stream.py`（暂停接口、确认后继续、跑完问要不要查路线）
3. `modules/trip/guide_ask.py`（景点清单的暂停节点和用户调整整理）

**读路线决策的顺序**：
1. `modules/trip/route_decision_graph.py`（图：查候选 → 暂停 → 写对比/推荐/提醒）
2. `modules/trip/route_decision_stream.py`（解析需求、校验地点、SSE、恢复）
3. `modules/trip/route_decision_tools.py`（高德数据，不调模型）

---

## 五、客服链路（RAG）

```
POST /customer/chat
   │
   └─ customer_stream()         modules/customer/stream.py
        │
        └─ 图：START → retrieve → generate → END
             图结构：modules/customer/graph.py
             │
             ├─ retrieve_node()   modules/customer/node.py
             │     ├─ keyword_search()  rag_search.py   BM25 + jieba 分词
             │     ├─ vector_search()   rag_search.py   Chroma + 智谱向量
             │     └─ hybrid_search()   rag_search.py   两层按名次加权，取前 4
             │
             └─ generate_node()   modules/customer/node.py
                   └─ 提示词 ANSWER_PROMPT（prompts.py）
                        铁律：只能照参考资料答，查不到就说没找到

知识库从哪来：
   data/docs/*.md  ──rag_ingest.py──→  data/chroma/（向量库）
                          │
                          ├─ split_markdown()  按 ## 二级标题切块，600 字上限
                          └─ embed_batch()     智谱 embedding-3，每批 64 条
```

**数据落在哪**：**不落库**。客服没有会话历史，刷新即清空（已知限制）

**配置在哪**：`rag_config.py`（文档目录、向量库目录、集合名、embedding 模型）

**知识库加载**：`rag_store.py` 的 `load_store()`，**全进程只加载一次**，三层检索共享

**改了文档要做什么**：重跑 `rag_ingest.py` → 重启服务

---

## 六、四条链路共用什么

| 东西 | 在哪 | 谁在用 |
|---|---|---|
| 模型客户端 | `core/llm.py` 的 `get_llm()` | 四个模块全部 |
| `.env` 加载 | `core/llm.py`（全项目唯一一处；其他文件再调 `load_dotenv` 只是幂等兜底） | 全部 |
| SSE 打包 | `core/sse.py` 的 `sse()` | 出行 + 客服 |
| 同步转线程 | `core/sse.py` 的 `stream_from_thread()` | 出行 + 客服 |
| 数据库连接 | `core/db.py` 的 `get_conn()` / `query()` / `execute()` / `transaction()` | 全部 |
| 会话读写 | `modules/chat/sessions.py` | 闲聊 + 角色扮演 |
| 联网搜索工具 | `modules/trip/tools.py` 的 `web_search()` | 出行 + 角色扮演（AI 帮我查） |
| 检查点 | `modules/trip/route_decision_graph.py`（路线 + 攻略共用一份） | 出行 |

**统一约定**：存库失败不拖垮主流程——各模块自己 `try/except`，打印后继续。

---

## 七、怎么快速定位一段代码

不要通读，**搜锚点词**。下面这些词全项目只有一处或少数几处在用：

| 我想找什么 | 搜这个 | 会出现几处 |
|---|---|---|
| 出行是走 Chat / Route 还是 Travel | `"TRAVEL"` / `ROUTE` | `modules/trip/understand.py` + `databases/db_trip.py` |
| 什么时候给用户报错 | `没跑通` | 几处，全在 stream 文件 |
| 模型怎么调的 | `get_llm(` | 全指向 `core/llm.py` |
| 数据库写在哪 | `save_` | 各模块的写入口 |
| 检索三层怎么合并 | `hybrid_search` | 只有 `modules/customer/rag_search.py` 定义一次 |
| 知识库配置在哪 | `CHROMA_DIR` | `modules/customer/rag_config.py` |
| 谁在发 SSE 事件 | `"kind":` | 各模块的 stream 文件 |
| 人工确认在哪暂停 | `interrupt(` | `modules/trip/guide_ask.py` + `route_decision_graph.py` |
| 角色记忆规则 | `MEMORY_LIMIT` / `add_one_round` | `modules/roleplay/memory.py` + `databases/db_roleplay.py` |

---

## 八、加新模块时照着改哪里

假设要加一个「天气」模块 `modules/weather/`：

```
modules/weather/
├── __init__.py
├── graph.py       ← 图结构（照抄 modules/trip/graph.py）
├── node.py        ← 节点实现
├── prompts.py     ← 提示词
├── state.py       ← TypedDict 状态（可选，简单模块可以直接用 dict）
└── stream.py      ← 对外出口 weather_stream()，yield SSE
```

**七个步骤**：

1. **建目录** `modules/weather/`，加 `__init__.py`
2. **写出口函数** `weather_stream(query)` → yield SSE 字符串
   （用 `from core.sse import sse`，别自己写一份）
3. **拿模型** 用 `from core.llm import get_llm`，按需要传 `temperature` / `thinking`
4. **图放** `graph.py`，节点放 `node.py`，提示词放 `prompts.py`
5. **要用数据库的话**：在 `databases/db_weather.py` 写建表 + 增删改查，
   然后把 `create_weather_tables()` 加进 **`core/db.py`** 的 `create_all_tables()`
   里的 `module_builders` 列表（写成 `("databases.db_weather", "create_weather_tables")`）。
   注意 `tenants` 必须最先建，新表如果要外键引用它，写进 `module_builders` 就自动排在后面
6. **在 `api/main.py` 加路由**：`from modules.weather.stream import weather_stream`，
   并补一个 `GET /weather/ping` 存活检测
7. **回到这份文档，补一节「天气链路」**

**第 5、6 步最容易忘**：忘了第 5 步会「表不存在」报错，忘了第 6 步前端根本调不到。
