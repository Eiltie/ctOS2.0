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
│   ├── db.py              ← 开连接 + 建表总入口
│   ├── checkpoints.py     ← 出行的暂停现场（路线和攻略共用一个）
│   └── tools/             ← 外部数据工具（谁都能用，不判断、不调模型）
│       ├── search.py      ← web_search（攻略搜景点、角色扮演 AI 帮我查）
│       ├── weather.py     ← get_weather（Open-Meteo）
│       ├── amap.py        ← 高德：地名查坐标、四种方式的候选路线
│       └── suggest.py     ← 判断"这句更像路线还是攻略"（纯关键词）
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
├── modules/               ← 这里每一项都是 ctOS 的一个模块，层级一致
│   ├── chat/              ← 闲聊（graph/node/state/prompts/stream/sessions）
│   ├── roleplay/          ← 角色扮演（roles/presets/prompts/stream/search/memory/openings）
│   ├── trip/              ← 智能出行（一个 Agent + 若干能力）
│   │   ├── 出口：stream.py
│   │   ├── 编排：agent.py（判断 → 自己答 / 调能力）
│   │   ├── 图：graph.py + node.py + state.py（一个节点，messages 当状态）
│   │   ├── 提示词：prompts.py
│   │   ├── 判断：suggest.py（纯关键词的辅助判断）
│   │   └── capabilities/      ← 智能出行的能力（子图），只有这个模块用
│   │       ├── route/          路线规划：need / graph / stream / tools / prompts
│   │       └── guide/          旅游攻略：graph / stream / node / prompts / state /
│   │                           conditions / ask / quick / cli（终端调试）
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
   ├─ POST /chat/attachment ──→ 上传图片，返回 image_id
   ├─ GET  /chat/attachment/{id} ──→ 取图（鉴权，只给本租户）
   ├─ POST /chat      ──→ 闲聊 / 角色扮演   纯文本流（可带 image_ids）
   ├─ POST /trip/chat ──→ 智能出行（Agent 判断：自己答 / 路线 / 攻略）  SSE 事件流（可带 image_ids）
   └─ POST /customer/chat ─→ 客服           SSE 事件流
```

**识图的接入点（重要）：**

识图**不是一张独立的图**。模型本身支持多模态，所以识图只是「消息长什么样」的问题：

| 场景 | content |
| --- | --- |
| 没有图 | `"这张图里有什么"`（字符串，和以前一样） |
| 有图 | `[{"type":"text",...}, {"type":"image_url",...}]`（块数组） |

图的拓扑、节点、边、`core/llm.py`、所有工具、路线和攻略两个子图都没动。

```
上传接口 → modules/chat/attachments.py（存盘 + 记账 message_images）
                     ↓
        build_user_message(text, image_paths)   ← 有图才变块数组
                     ↓
   闲聊：api/main.py 构造 HumanMessage
   出行：交给 decide_node()，Agent 看到图后写 action + query
                     ↓
        Agent 写出的 query 是纯文字 → 两个子图原样吃，不用改
```

凡是「把消息当文字用」的地方（`trip/node.py` 两处等）必须过 `text_of()`，
否则 content 变成数组后会 TypeError。

**为什么识图不单独建一张图**：模型本身支持多模态，识图就是「把图拼进 content」，
中间没有任何独立决策。拆成图只会多一次模型调用、多一份 state，还看不到聊天历史。

**图片的几条硬规则**：

- 图片不放 `static/`：那是公开挂载的，放进去等于全站可见；存 `databases/images/`，只走带鉴权的接口
- 格式按**文件真实内容**判断，不看扩展名
- 单张上限 8 MiB，单次最多 3 张
- 消息正文只存纯文字，图走 `message_images` —— 历史回放逻辑一行不用改
- 历史里不回放图片：上一轮的图这一轮模型看不到（读盘 + 反复吃 token，不值）

**图片记录的两个坑**：

1. 上传时先插一行占位（`message_id` 为空）。发消息时如果又插一行新的，
   同一个文件就有两条记录，旧的那条永远挂着空 `message_id` 变成孤儿。
   正确做法是用 `claim_image()` **UPDATE 认领**上传时那条，不插新行。
2. `_last_user_text()` 一类函数如果直接 `return message.content`，
   content 变成数组后做字符串拼接会 TypeError。**凡是把消息当文字用的地方，必须过 `text_of()`**。

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

**角色扮演定位为「闲聊的插件」，不是独立模块。**

插件的定义：**一种有明确规则、有专属界面的对话模式**。它挂在闲聊下面，
不占独立标签页 —— 顶部的一条插件切换栏就是它的入口。

```
闲聊模块
├── 普通聊天        （现在的样子）
└── 插件
    ├── 角色扮演    ← 已实现
    ├── 模拟面试    ← 以后加
    └── 口语陪练    ← 以后加
```

**先做 1 个插件做深，不要一次做 3 个浅的。** 这也是它复用闲聊 `sessions` / `messages`
而不是自建一套表的原因：数据层不用重复，插件只负责「怎么说话」。

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
         ├─ web_search()    core/tools/search.py（和攻略共用）
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

**角色数据的一整套规则**（改之前先看这张表，都是定死的）：

| 项目 | 决定 |
| --- | --- |
| 角色档案字段 | 名字、性格、说话方式、边界（不会做什么）、开场白 |
| 档案是否展示 | **不直接展示**，只给「构建成功 + 一句台词」；可主动查看 |
| 记忆更新频率 | **每 6 轮更新一次**（覆盖式，不是追加） |
| 记忆归属 | **按角色记忆**（不是按会话），同一角色多次聊天共用一份 |
| 记忆长度 | 200 字以内，每次覆盖旧摘要 |
| 记忆保存时长 | **永久** |
| 清空记忆 | **全清**，不做挑着删 |
| 预设角色存放 | **代码里的常量**（`modules/roleplay/presets.py`），不进数据库 |
| 用户创建的角色 | 存 `role_play_roles`，用 `source` 区分 `custom` / `ai_search` |

**三个必踩的坑及对策**（改角色提示词时对照着看）：

| 坑 | 对策 |
| --- | --- |
| 搜索结果不等于人设，模型会念百科 | 要求转成**第一人称自述**，不能照抄资料 |
| 聊几轮后跑调，回到默认 AI 腔 | **每轮重申角色约束**，不只开头说一次 |
| 用户问"你真的是 X 吗"，角色出戏 | 约束在角色内回应，同时留一个「确实需要帮助时」的例外 |

**读这里的顺序**：
1. `modules/roleplay/roles.py`（角色从哪来、边界规则）
2. `modules/roleplay/stream.py`（对话怎么拼提示词、怎么流式吐）
3. `modules/roleplay/memory.py`（记忆怎么更新）

---

## 四、出行：一个 Agent + 若干能力

### 4.0 先记住：用户只面对一个入口

```
用户：一句出行需求
   │
   ▼
智能出行 Agent（modules/trip/）      ← 判断该干嘛，然后办
   ├─ 自己答：推荐、准备清单、天气、闲聊
   ├─ 调能力：路线规划
   └─ 调能力：旅游攻略
```

**路线规划和旅游攻略是它的能力（子图），不是用户能选的菜单。**
用户不需要知道内部用了哪个，正如不需要知道 Agent 用了哪个工具。

**入口只有一个**：`POST /trip/chat`。

> 前端还有一个"路线规划 | 旅游攻略"的模式条，那是界面上的过渡（下一步收口）。
> `POST /guide/chat` 已经改成转发壳，打它和打 `/trip/chat` 完全一样，
> 由 Agent 判断该干嘛——从攻略那个入口问"怎么走"，照样会被派去路线。

### 4.0.1 Agent 那一圈怎么转

```
POST /trip/chat
   │
   └─ trip_stream()            modules/trip/stream.py（先发 SAY「收到…」）
        └─ run_trip_service()  modules/trip/agent.py   ← 编排
             ├─ 先跑一次 Agent 图   modules/trip/graph.py
             │     └─ decide_node()  modules/trip/node.py
             │          调一次模型（modules/trip/prompts.py 的 AGENT_PROMPT）
             │          结论三选一：answer / route / guide
             │          自己答的那类顺手把回复写出来（判断和回答合在一次调用里）
             │
             ├─ answer → 存 CHAT 轮，回一条气泡
             ├─ route  → modules/trip/capabilities/route/stream.py
             └─ guide  → modules/trip/capabilities/guide/stream.py
```

**Agent 图只有一个节点**：`START → agent → END`，和闲聊模块那张图同构。
"路由"现在表现为节点内部的三种结论，由 `agent.py` 分派。
将来 Agent 要自己转圈（办完一个能力接着办另一个），再在图里加节点和条件边。

**为什么编排不在图里**：子图要"边跑边吐"，用户得看到进度；
图的节点只能返回状态，产不出事件流。所以判断交给图，执行留在生成器里。

**人在回路**：子图自己的暂停照旧——用户点完还是打到子图的恢复接口
（`/trip/route/choose`、`/guide/spots`），线程号和现场都不变，Agent 层不掺和。

**天气**：只问天气时先把真实数据查出来（`answer_weather`），再交给 Agent 组织语言，
不然模型会编气温。

### 4.1 能力一：路线规划

```
（由 Agent 判断 action=route 后进来，也可以单独调）
   │
   └─ start_route_decision() modules/trip/capabilities/route/stream.py
        ├─ 解析需求 parse_route_need(query, history)   capabilities/route/need.py
        │     history 一起喂进去，一次调用搞定"改成5天"这类补充
        ├─ 校验     check_need()      缺起点/终点/城市 → 反问
        ├─ 查地点   find_place()      core/tools/amap.py
        ├─ 查天气   get_weather()     core/tools/weather.py
        ├─ 查候选   route_graph       capabilities/route/graph.py
        │     ├─ collect_routes   查驾车/公交/步行/骑行（tools.py）
        │     ├─ ask_user         interrupt() 暂停，等用户选方案
        │     ├─ compare_routes   写对比
        │     ├─ decide_route     写推荐理由
        │     └─ write_tips       写出发提醒
        └─ 存库    save_trip_turn(..., "ROUTE")
```

**人工干预（HITL）**：

- 地点有歧义时先发 `ASK_PLACE`，让用户点一个候选。
  **发事件之前**把"这份需求 + 线程号"存进检查点，`thread_id` 一起发给前端。
- 用户点一个后 POST `/trip/route/place`（`{thread_id, place}`），后端用**原来那份需求**接着跑：
  把选中的地点塞进起点/终点，直接查天气、跑图。**不重新解析、不重新判断、不改写**。
- 候选路线出来后，图停在 `ask_user`，后端发 `ASK`，前端显示候选卡片。
- 用户点一条后 POST `/trip/route/choose`，后端用 `Command(resume=choice_id)` 接着跑。
- 暂停状态存在 `databases/checkpoints/route_checkpoints.sqlite`（`core/checkpoints.py` 管，全进程一个实例）。
  文件打不开时自动退回 `MemorySaver`，不影响其他模块。
- 恢复时会校验 `tenant_id`，拿别人的暂停现场续不上。
- **什么时候不弹地点候选**：只查到一条（没得选）、或后续候选只是同名变体
  （查"灵隐寺"带出"富阳灵隐寺"）时直接采用第一条；只有名字前面紧挨行政后缀
  （"长城(延庆区)"）那种真正的多处，才让用户选。

**数据落在哪**：`trip_ai_outputs` 的 `route_need`/`route_compare`/`route_decision`/`route_tips` 四列；
`trip_sessions.turn_kind = 'ROUTE'`。

### 4.2 能力二：旅游攻略（一个暂停点）

```
（由 Agent 判断 action=guide 后进来，也可以单独调）
   │
   └─ start_guide()              modules/trip/capabilities/guide/stream.py
        ├─ 跑图  guide_graph      modules/trip/capabilities/guide/graph.py
        │     ├─ weather          解析需求（带 history）+ 查天气 + 写总结
        │     ├─ spots_agent      搜景点（ReAct 循环，最多 3 轮）
        │     ├─ ask_spots        interrupt() 暂停：用户勾掉/补充景点
        │     ├─ planner          按用户的调整排行程
        │     └─ advice           写游玩建议
        │
        ├─ 暂停时发 ASK_SPOTS，用户勾完 POST /guide/spots
        │     └─ resume_guide()   Command(resume=...) 一路跑到 advice
        │
        └─ 存库  save_trip_turn(..., "TRAVEL")
```

**只有一个暂停点**：景点清单。勾完直接排行程、写建议、入库，不再问"要不要查真实路线"。

**四段产出**：天气 / 景点推荐 / 行程安排 / 游玩建议。

第四段是拆分后才有的：只写节奏、预约、交通卡、同行人注意、避坑、备选、预算，
**不写距离和逐段路线**——那是路线模块的事。全程不调高德。

**数据落在哪**：`trip_ai_outputs` 的 `weather`/`spots`/`itinerary`/`advice`；
`trip_sessions.turn_kind = 'TRAVEL'`。老记录的第四段存在 `route_plan` 列里，
前端按"详细路线（旧版）"显示，不丢历史。

### 4.3 两条链共同的部分

```
save_trip_turn()        databases/db_trip.py
  一次事务写三张表：
    trip_chats（会话，没有就新建）
    trip_sessions（本轮，turn_kind 区分路线/攻略/问答）
    trip_user_inputs（用户原话）
    trip_ai_outputs（产出，哪些列存在写哪些）

事件协议：SAY / START / STEP / TOKEN / DONE / CHAT / ASK / ASK_PLACE / ASK_SPOTS / SAVED / ERROR
                    ASK / ASK_PLACE（路线）、ASK_SPOTS（攻略）
                    CHAT / SAVED / ERROR
```

**老库升级**：跑一次 `python -X utf8 -m core.db`。
`db_trip.py` 里的 `route_columns_ready()` / `advice_column_ready()` 会在第一次存库前检查列在不在，
不在时跳过那几列，不会拖垮其他模块。

**提示词在哪**：路线 `modules/trip/capabilities/route/prompts.py`；攻略 `modules/trip/capabilities/guide/prompts.py`。

**读攻略的顺序**：
1. `modules/trip/capabilities/guide/graph.py`（**这张图就是攻略的全部逻辑**）
2. `modules/trip/capabilities/guide/stream.py`（开始、暂停、继续、存库）
3. `modules/trip/capabilities/guide/node.py`（四个节点的实现）

**读路线决策的顺序**：
1. `modules/trip/capabilities/route/graph.py`（图：查候选 → 暂停 → 写对比/推荐/提醒）
2. `modules/trip/capabilities/route/stream.py`（SSE 出口、恢复）
3. `modules/trip/capabilities/route/need.py`（需求解析、校验、查地点）
4. `modules/trip/capabilities/route/tools.py`（推荐打分和排版，不调模型）
## 五、客服链路（RAG）

```
POST /customer/chat
   │
   └─ customer_stream()         modules/customer/stream.py
        │
        └─ 图结构：modules/customer/graph.py
           START ─┬─(寒暄)────→ greet                               → END
                  └─(其余)────→ rewrite → retrieve ─┬─(有资料)→ generate → END
                                                    └─(没资料)→ refuse   → END
             │
             ├─ rewrite_node()    modules/customer/node.py
             │     ├─ 把「那它怎么配」改写成自包含的检索句
             │     └─ 判断是不是在问 ctOS（in_scope）
             │
             ├─ retrieve_node()   modules/customer/node.py
             │     ├─ keyword_search()  rag_search.py   BM25 + jieba，分数归一化
             │     ├─ vector_search()   rag_search.py   Chroma（cosine）+ 本机 Ollama 向量
             │     └─ hybrid_search()   rag_search.py   按分数加权（0.5/0.5），低于阈值丢弃
             │
             ├─ generate_node()   modules/customer/node.py
             │     └─ 提示词 ANSWER_PROMPT（prompts.py），资料带「文件 › 章节」标题路径
             │
             └─ greet_node() / refuse_node()
                   └─ 不调模型，直接返回固定话术（流式层会补发 TOKEN 让前端逐字显示）

知识库从哪来：
   data/docs/*.md  ──rag_ingest.py──→  data/chroma/（向量库）
                          │
                          ├─ split_markdown_detailed()  按标题切块，每块带标题路径
                          │     · 代码块里的 # 不算标题，也不切断代码块
                          │     · 优先在 ### 三级标题处切，超长再按段落
                          ├─ MAX_CHUNK_CHARS = 800（扫过 500/600/800/1000 定的）
                          └─ 向量化：本机 Ollama qwen3-embedding，每批 64 条
```

**拒答的判定**：模型说库外 **且** 检索也没找到强结果（`STRONG_HIT_SCORE = 0.68`），才拒答。
两边都不同意才拒答，误拒优先——客服最难受的不是答得浅，是明明能答却说没找到。

**数据落在哪**：**不落库**。客服没有会话历史，`history` 由前端每次带上，刷新即清空

**配置在哪**：`rag_config.py`（文档目录、向量库目录、集合名、向量模型与地址）

**调参怎么验**：改 `MAX_CHUNK_CHARS` / 权重 / 阈值之前，
先跑 `python -X utf8 -m modules.customer.rag_eval` 对比，别凭感觉调

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
| 联网搜索工具 | `core/tools/search.py` 的 `web_search()` | 路线 + 攻略 + 角色扮演（AI 帮我查） |
| 检查点 | `modules/trip/capabilities/route/graph.py`（路线 + 攻略共用一份） | 出行 |

**统一约定**：存库失败不拖垮主流程——各模块自己 `try/except`，打印后继续。

---

## 七、怎么快速定位一段代码

不要通读，**搜锚点词**。下面这些词全项目只有一处或少数几处在用：

| 我想找什么 | 搜这个 | 会出现几处 |
|---|---|---|
| 这轮是路线还是攻略 | `"ROUTE"` / `TRAVEL` | `trip_sessions.turn_kind`（用户点哪个模式就是哪个） |
| 什么时候给用户报错 | `没跑通` | 几处，全在 stream 文件 |
| 模型怎么调的 | `get_llm(` | 全指向 `core/llm.py` |
| 数据库写在哪 | `save_` | 各模块的写入口 |
| 检索三层怎么合并 | `hybrid_search` | 只有 `modules/customer/rag_search.py` 定义一次 |
| 知识库配置在哪 | `CHROMA_DIR` | `modules/customer/rag_config.py` |
| 谁在发 SSE 事件 | `"kind":` | 各模块的 stream 文件 |
| 人工确认在哪暂停 | `interrupt(` | `modules/trip/capabilities/guide/ask.py` + `route_decision_graph.py` |
| 角色记忆规则 | `MEMORY_LIMIT` / `add_one_round` | `modules/roleplay/memory.py` + `databases/db_roleplay.py` |

---

## 八、加新模块时照着改哪里

假设要加一个「天气」模块 `modules/weather/`：

```
modules/weather/
├── __init__.py
├── graph.py       ← 图结构（照抄 modules/trip/capabilities/guide/graph.py）
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
