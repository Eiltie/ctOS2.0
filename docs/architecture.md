# ctOS 2.0 请求地图

> 这份文档回答一个问题：**用户点一下，代码会依次经过哪些文件？**
>
> 加新模块时回来更新这张图；看不懂某段代码时，先在这里找它属于哪个环节。

---

## 一、全局：一个 app 装三个模块

### 目录结构

```
ctOS2.0/
├── api/
│   └── main.py            ← 唯一入口，所有路由都在这里
├── core/                  ← 跨模块共用
│   ├── llm.py             ← 唯一的 get_llm()
│   ├── sse.py             ← sse() 事件打包
│   └── db.py              ← 开连接 + 建表总入口
├── databases/             ← 各模块的表和增删改查
│   ├── db_tenant.py       ← 全局身份表 tenants（谁都不依赖它，它也不依赖谁）
│   ├── db_chat.py
│   ├── db_trip.py
│   ├── db_view.py         ← 命令行查看工具
│   └── ctOS2_db.db        ← 数据文件在这
├── modules/
│   ├── chat/              ← 闲聊（graph/node/state/prompts/stream/sessions）
│   ├── trip/              ← 出行（graph/node/tools/prompts/route/state/stream/cli）
│   └── customer/          ← 客服（graph/node/state/prompts/stream + rag_* + data/）
├── static/                ← 前端（无构建步骤）
├── docs/                  ← 本文档
└── config/                ← .env、requirements.txt
```

### 请求流向

```
浏览器 static/index.html
        │
        ▼
api/main.py          ← 唯一入口，所有路由都在这里
   │
   ├─ POST /chat      ──→ 闲聊    纯文本流
   ├─ POST /trip/chat ──→ 出行    SSE 事件流
   └─ POST /customer/chat ─→ 客服 SSE 事件流
```

**先记住这张图**，下面三节是每一条链路的展开。

---

## 二、闲聊链路（最简单，建议从这里读起）

```
POST /chat
   │
   ├─ resolve_session()        modules/chat/sessions.py  没有会话就新建
   ├─ load_history()           modules/chat/sessions.py  取最近 10 条
   │
   ├─ run_graph()              modules/chat/stream.py    ← 模块对外唯一出口
   │     └─ 图：START → chat_node → END
   │          └─ ctOS_chat_node()   modules/chat/node.py
   │                └─ 系统提示词    modules/chat/prompts.py
   │                └─ get_llm(temperature=0.7)  core/llm.py
   │
   └─ 跑完后才存库
        ├─ save_user_message()  modules/chat/sessions.py
        └─ save_ai_reply()      modules/chat/sessions.py
             └─ add_message()   databases/db_chat.py → 表 messages
```

**数据落在哪**：`sessions`（会话）+ `messages`（消息）

**读这里的顺序**：`modules/chat/stream.py`（12 行，看懂出口）→ `modules/chat/graph.py`（22 行，看懂图）→ `modules/chat/node.py`（17 行，看懂节点）

---

## 三、出行链路（最复杂，一次规划十几次模型调用）

```
POST /trip/chat
   │
   └─ trip_stream()             modules/trip/stream.py
        │  ← 注意：这个函数本身不干活，它把活丢给线程再收回来
        │
        ├─ yield SAY "收到，正在理解你的需求…"    第一秒就发，不让用户白等
        │
        └─ _run_trip() 在【工作线程】里跑
             │
             ├─ ① 分流  understand_query()   modules/trip/cli.py
             │      调一次 LLM，看这句是 TRAVEL 还是 CHAT
             │      │
             │      ├─ CHAT → 直接回一句话，存库，结束
             │      └─ TRAVEL ↓
             │
             ├─ ② 回显  yield START
             │
             ├─ ③ 跑图  trip_graph.stream()    ← 十几次模型调用全在这里
             │      │
             │      图结构定义：modules/trip/graph.py
             │      │
             │      ├─ weather      modules/trip/node.py
             │      │     └─ 调 LLM 解析需求（出 JSON，这段不流给用户）
             │      │     └─ get_weather()    modules/trip/tools.py → Open-Meteo
             │      │     └─ 调 LLM 写天气总结
             │      │
             │      ├─ spots_agent  modules/trip/node.py
             │      │     └─ ReAct 循环：要搜就 bind_tools
             │      │           ├─→ tools (ToolNode) → web_search() → DeepSeek Search
             │      │           └─→ 搜够了直接出景点清单
             │      │     循环上限：MAX_SEARCH=3（modules/trip/node.py）
             │      │     路由判断：should_continue()  modules/trip/route.py
             │      │
             │      ├─ planner      modules/trip/node.py  把景点排成逐日行程
             │      │
             │      └─ route_agent  modules/trip/node.py
             │            └─ for 循环藏在这个函数里（MAX_ROUTE_ROUNDS=8）
             │            └─ get_directions() modules/trip/tools.py → 高德
             │
             │      每一步的 token 都要过 _keep() 四道过滤才流给用户
             │
             └─ ④ 存库  save_trip_turn()   databases/db_trip.py
                        一次事务写三张表：
                          trip_sessions（本轮）
                          trip_user_inputs（用户原话）
                          trip_ai_outputs（四段产出）
```

**数据落在哪**：`trip_chats`（会话）+ `trip_sessions`（每轮）+ `trip_user_inputs` + `trip_ai_outputs`

**提示词全在**：`modules/trip/prompts.py`（共 6 个，每个都按「角色/任务/输出格式」写）

**读这里的顺序**：
1. `modules/trip/graph.py`（28 行，**这张图就是全部逻辑**）
2. `modules/trip/stream.py` 的 `_run_trip`（看清 4 个阶段）
3. 按需读某个节点，不用全读

---

## 四、客服链路（RAG）

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

## 五、三条链路共用什么

| 东西 | 在哪 | 谁在用 |
|---|---|---|
| 模型客户端 | `core/llm.py` 的 `get_llm()` | 三个模块全部 |
| `.env` 加载 | `core/llm.py`（全项目唯一一处） | 全部 |
| SSE 打包 | `core/sse.py` 的 `sse()` | 出行 + 客服 |
| 数据库连接 | `core/db.py` 的 `open_database()` | 闲聊 + 出行 |
| 会话读写 | `modules/chat/sessions.py` | 目前只有闲聊（客服还没接） |
| 路径解析 | `venv/Lib/site-packages/ctOS2_project.pth` | 全部（不用再写 sys.path.insert） |

**统一约定**：存库失败不拖垮主流程——各模块自己 `try/except`，打印后继续。

---

## 六、怎么快速定位一段代码

不要通读，**搜锚点词**。下面这些词全项目只有一处在用：

| 我想找什么 | 搜这个 | 会出现几处 |
|---|---|---|
| 出行是走 Chat 还是 Travel | `TRAVEL` | `modules/trip/cli.py` + `databases/db_trip.py` |
| 什么时候给用户报错 | `没跑通` | 3 处，全在 stream 文件 |
| 这轮哪些 token 流给用户 | `_keep` | 只有出行，独一份 |
| 模型怎么调的 | `get_llm(` | 全指向 `core/llm.py` |
| 数据库写在哪 | `save_` | 4 处，正好是 4 个写入点 |
| 检索三层怎么合并 | `hybrid_search` | 只有 `modules/customer/rag_search.py` 定义一次 |
| 知识库配置在哪 | `CHROMA_DIR` | `modules/customer/rag_config.py` |

---

## 七、加新模块时照着改哪里

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
   里的 `module_builders` 列表（写成 `("databases.db_weather", "create_weather_tables")`）
6. **在 `api/main.py` 加路由**：`from modules.weather.stream import weather_stream`，
   并补一个 `GET /weather/ping` 存活检测
7. **回到这份文档，补一节「天气链路」**

**第 5、6 步最容易忘**：忘了第 5 步会「表不存在」报错，忘了第 6 步前端根本调不到。

**第 5 步最容易忘**，忘了就会「表不存在」报错。
