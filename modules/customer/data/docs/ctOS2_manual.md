# ctOS 2.0 系统手册

本文是 ctOS 2.0 的完整说明，涵盖使用方式、技术实现、常见问题与部署运维。
读者既可以是第一次接触本系统的普通用户，也可以是准备二次开发的工程师。

> **线上地址：<https://ctos2.cn>**（`www.ctos2.cn` 同样可访问）。注册账号后即可使用，
> 不需要自己部署。本文里提到的本地启动方式只供二次开发时使用。

---

## 一、ctOS 2.0 是什么

ctOS 2.0 是一个用 FastAPI 加 LangGraph 搭建的多模块 AI 应用。

它的核心设计是：**同一个 FastAPI 应用里挂载多个能力模块，所有模块共用一个端口、一套静态资源、一套会话接口。**
模块之间彼此独立，各自有自己的一张 LangGraph 图，互不干扰。

目前系统包含四个能力模块，都已接入 Web 页面（角色扮演挂在「闲聊」里，从侧栏菜单进入）：

| 模块 | 路由 | 说明 |
| --- | --- | --- |
| 闲聊 / 对话 | `/chat` | 基于 LangGraph 的对话图，流式返回纯文本 |
| 角色扮演 | `/chat`（带 `role_id`）+ `/roleplay/*` | 预设角色、自己写角色、AI 帮我查；会话复用闲聊的表 |
| 智能出行 | `/trip/chat` | 双模式：路线决策（多方案对比、人工选方案）+ 旅游攻略（天气 → 景点 → 暂停选景点 → 行程 → 路线），SSE 事件流 |
| 智能客服 | `/customer/chat` | 基于 RAG 三层检索的问答模块，SSE 事件流 |

需要特别说明的是：**智能出行和智能客服都不是独立的 app，它们是 ctOS 的一项能力。**
系统采用「一个 app、多个能力」的组织方式，而不是「多个 app 并列」。

三者还有一个重要区别：

- 闲聊、角色扮演和智能出行**会存数据库**，左侧栏能翻到历史记录。
- 智能客服的问答**不写数据库**，刷新页面就没了；但请求体会带上最近几轮对话（`history`），
  用来理解「那它怎么配」这类追问。

### 技术栈

- **Web 框架**：FastAPI、Uvicorn、Pydantic
- **编排框架**：LangGraph、LangChain、langchain-openai
- **模型**：DeepSeek（对话与推理）、智谱 embedding-3（向量化）
- **外部工具**：DeepSeek Search 联网搜索、高德地图路径规划、Open-Meteo 天气
- **存储**：PostgreSQL 17 存会话、账号与出行记录（多租户）；Chroma 用于 RAG 向量库
- **检索**：jieba + rank-bm25 与向量混合
- **认证**：JWT + bcrypt
- **部署**：Docker + Docker Compose，线上由 Cloudflare 托管域名与 HTTPS
- **配置**：python-dotenv

---

## 二、快速开始

### 第一步：安装依赖

在项目根目录执行：

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r config/requirements.txt
```

### 第二步：配置环境变量

复制配置模板，然后填入自己的值：

```bash
cp config/YOUR_config.env config/.env
```

`config/.env` 需要填写以下内容：

```
DEEPSEEK_API_KEY=      # DeepSeek 密钥，对话、出题、联网搜索都用它
DEEPSEEK_BASE_URL=     # DeepSeek 接口地址
DEEPSEEK_MODEL=        # 模型名

AMAP_KEY=              # 高德地图密钥，智能出行算路线用

# PostgreSQL 数据库
PG_HOST= / PG_PORT= / PG_DBNAME= / PG_USER= / PG_PASSWORD=

# 登录 token 的签名密钥
JWT_SECRET_KEY=
```

智能客服模块另外还需要一个密钥：

```
ZHIPU_API_KEY=         # 智谱密钥，RAG 向量化用
```

这个密钥是**必需的**：`rag_store.load_store()` 在加载知识库时会先检查它，取不到就直接抛错。
也就是说，`ZHIPU_API_KEY` 没配的话，智能客服模块启动不起来（Web 服务本身的其它模块不受影响）。

**安全提醒**：`config/.env` 已被 `.gitignore` 忽略，**不要**把真实密钥提交到代码仓库。
如果不小心提交过，请立刻去对应平台轮换密钥——仅仅删除文件并不能让密钥失效。

### 第三步：初始化数据库

```bash
python core/db.py
```

会建好全部 12 张表：`tenants`、`users`、`sessions`、`messages`、`trip_chats`、
`trip_sessions`、`trip_user_inputs`、`trip_ai_outputs`、`role_play_sessions`、
`role_play_memories`、`role_play_roles`、`feedback`。表已存在就跳过，不会动已有数据。
**没建表的话注册登录会直接报错**，这是最容易漏的一步。

### 第四步：智能客服入库（第一次使用前跑一次）

智能客服依赖本地向量库，需要先把 `data/docs/` 里的文档切块、向量化、入库：

```bash
python -X utf8 -m modules.customer.rag_ingest
```

**改了 `data/docs/` 里的文档后要重新跑一次。**

### 第五步：启动服务

```bash
python -X utf8 -m api.main
```

然后在浏览器打开 <http://127.0.0.1:8080/> 就是前端页面。

还没有跑过建表和入库时，闲聊和出行照样能用（写库失败只会打印一行日志），
但智能客服会因为找不到向量库而报错。

> **如果只是想用，不想自己装：** 直接打开 <https://ctos2.cn>，注册账号即可，
> 线上部署的就是这一套代码。

## 启动项目（完整步骤汇总）

这一节把「怎么启动这个项目」完整走一遍，照顺序做即可。

### 1. 安装依赖

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r config/requirements.txt
```

### 2. 配置密钥

```bash
cp config/YOUR_config.env config/.env
```

然后在 `config/.env` 里填好 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、
`AMAP_KEY`、`ZHIPU_API_KEY`、`PG_*`（数据库连接）、`JWT_SECRET_KEY`（登录签名密钥）。

### 3. 初始化数据库

```bash
python -X utf8 -m core.db
```

### 4. 智能客服入库（第一次用才需要）

```bash
python -X utf8 -m modules.customer.rag_ingest
```

### 5. 启动服务

```bash
python -X utf8 -m api.main
```

看到 uvicorn 启动成功后，在浏览器打开 <http://127.0.0.1:8080/> 即可使用。
线上对应的地址是 <https://ctos2.cn/>。

### 快速启动（已经配置过之后的日常使用）

如果之前已经装好依赖、配好密钥、建好表、入过库，那以后每次只要一条命令：

```bash
python -X utf8 -m api.main
```

> Windows 控制台默认 GBK，不加 `-X utf8` 中文可能乱码。

### 关于端口

本地默认监听 `127.0.0.1:8080`，由 `api/main.py` 末尾决定：

```python
host = os.getenv("HOST", "127.0.0.1")
port = int(os.getenv("PORT", "8080"))
uvicorn.run(app, host=host, port=port)
```

也就是说，**改端口用环境变量 `PORT`** 就够了，不用改代码。
容器（含线上）里 Dockerfile 已经把 `HOST` 设成 `0.0.0.0`，否则端口映射转发不进来。

前端请求后端用的是**相对路径**（`API.base` 为空字符串），也就是同源访问，
所以**换端口前端也不用动**，线上和本地用的是同一份前端代码。

### 其它常用命令

| 用途 | 命令 |
| --- | --- |
| 建表 | `python -X utf8 -m core.db` |
| 客服入库 | `python -X utf8 -m modules.customer.rag_ingest` |
| 查知识库是否就绪 | `python -X utf8 -m modules.customer.rag_store` |
| 检索测评（40 题） | `python -X utf8 -m modules.customer.rag_eval` |
| 看数据库内容 | `python -X utf8 -m databases.db_view` |
| 终端调试出行 | `python -X utf8 -m modules.trip.cli` |
| 验证客服流式封装 | `python -X utf8 -m modules.customer.stream` |

> 线上这些命令要在容器里跑，前面加 `docker exec ctos2-app`，例如
> `docker exec ctos2-app python -m core.db`。

---

## 三、使用手册

### 3.1 闲聊模块

点击前端左侧的「闲聊」入口即可开始对话。

闲聊模块的行为特点：

- **流式输出**：回答是一段一段吐出来的，前端按字追加，呈现打字机效果。
- **支持多轮上下文**：后端会读出当前会话的最近 10 条消息拼进上下文，所以可以接着上一句说。
- **有会话管理**：左侧栏会列出所有历史会话，可以点开旧会话继续聊，也可以删除不需要的会话。
- **会存数据库**：标题取用户第一句话的前 14 个字。会话和消息都存在 `sessions` / `messages` 两张表里，刷新页面后还在。

后端契约是：`POST /chat`，请求体为 `{"messages": "<用户说的话>", "session_id": <可选>}`，
响应是 `text/plain` 的流式文本，并在响应头 `X-Session-Id` 里带回本次使用的会话 id；
前端首次拿到这个 id 后记下来，后续请求带上它就能接着同一个会话聊。

### 3.2 智能出行模块

点击「智能出行」入口，用自然语言描述需求即可。它有两种模式，会自动判断：

**模式一：路线决策**，例如：

```
从杭州东站到灵隐寺怎么走，带老人，少走路
```

1. **确认需求** —— 认出起点、终点、出发时间、偏好、同行人；太笼统会反问
2. **查候选** —— 高德查驾车 / 公交地铁 / 步行 / 骑行，摆出 2~4 条真实方案
3. **暂停等你选** —— 不直接下结论，停下来让你选一条（有系统推荐，但以你的选择为准）
4. **写结论** —— 你选完之后，才写候选对比、推荐理由、出发提醒

不画地图、不做语音播报，只做路线分析和决策。

**模式二：旅游攻略**，例如：

```
下周想去杭州玩3天，带老人
```

1. **查询天气** —— 识别目的地、天数、出发日期，查真实天气并给出总结
2. **推荐景点** —— 结合天气和同行人推荐景点，必要时联网查门票、开放时间
3. **暂停等你勾选** —— 景点清单出来后停下来，可以去掉不想去的、补一个想去的
4. **安排行程** —— 按确认后的景点排出逐日行程
5. **规划路线** —— 细化成带具体时刻和交通耗时的路线
6. **问要不要查真实路线** —— 选了才用高德把每天相邻站点的真实距离和耗时再算一遍

**每一步的产出都会实时显示在页面上。**

后端契约是 `POST /trip/chat`，请求体 `{"query": "...", "history": [...], "chat_id": null}`，
响应是 `text/event-stream` 的 SSE 事件流。

**人工确认（HITL）怎么实现**：两个暂停点都用 LangGraph 的 `interrupt()`。
图跑到暂停节点会停住，把现场存进 `databases/route_checkpoints.sqlite`（运行产物，已 gitignore），
同时向前端发一个 `ASK` 或 `ASK_SPOTS` / `ASK_ROUTE` 事件。用户点完后调对应的接口继续：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/trip/route/choose` | 路线决策：用户选了哪个方案，继续写结论 |
| `POST` | `/trip/guide/spots` | 旅游攻略：用户勾掉/补充了哪些景点，继续排行程 |
| `POST` | `/trip/guide/route` | 旅游攻略：用户要不要查真实路线 |

继续时后端用 `Command(resume=...)` 恢复，同样的线程号从检查点取回现场。

**路线决策的地点校验**：地名查不到、城市对不上、或者太笼统（「家」「学校」）时，
系统会先反问，而不是拿一个错误的地点去算。「平湖秋月」这种在目标城市查不到的名字，
不会跑到外省同名地点去。

**目的地、天数、出发日期（`start_date`）是怎么从一句话里猜出来的**：
攻略图第一个节点 `weather` 先调一次模型做「需求解析」，把自然语言转成一段 JSON，
字段就是 `{"destination": 城市名, "days": 天数, "start_date": 出发日期}`。

- 目的地必须是城市名：说景点会换算成所属城市（西湖 → 杭州、故宫 → 北京），并去掉「市」这类后缀
- 天数：「周末」算 2 天、「三天两晚」算 3 天、「一周」算 7 天，没提就按 3 天
- 出发日期（`start_date`）：格式 `YYYY-MM-DD`，所有相对时间都以「今天」为基准推算，
  「明天」加 1 天、「后天」加 2 天、「周末」取最近的周六、「下周三」取下周星期三；
  没说出发时间就取今天

这段解析出的 JSON 是给程序用的，**不会流给用户看**；页面上展示的是解析后再写的天气总结。

**出行模块还带一个「意图分流」**：进图之前会先判断这句话属于哪一种。

- 路线需求 → 走路线决策
- 攻略需求 → 走旅游攻略
- 闲聊（打招呼、道谢、问你是谁） → **不跑图**，直接回一句话

三条路径都会存库，用 `trip_sessions.turn_kind` 区分：
`ROUTE` 表示路线决策，`TRAVEL` 表示旅游攻略，`CHAT` 表示闲聊分流。

**出行记录**存在另外三张表里，和闲聊的会话表分开。左侧栏在出行模式下会切换成出行记录列表，
点开可以恢复当时的结果，也可以删除。

对应接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/trip/list` | 最近的出行记录（默认最多 50 条） |
| `GET` | `/trip/{id}` | 单条记录的完整内容（含各段产出） |
| `DELETE` | `/trip/{id}` | 删除一条记录，子表级联删除 |
| `GET` | `/trip/ping` | 存活检测 |

**计时**：页面右下角会显示「规划中 12s」。中途停在选择面板时计时会暂停，
不会把用户思考的时间算进用时。

### 3.3 智能客服模块

这是基于 RAG（检索增强生成）的问答模块，专门回答关于 ctOS 2.0 项目本身的问题。

**两种运行方式**，两种都可用：

1. **网页**：点击「智能客服」入口直接提问（走 `POST /customer/chat`，SSE 流式返回）
2. **终端**：`python -X utf8 modules/customer/stream.py`
   启动后直接打字提问即可，输入 `exit`、`quit`、`q` 或 `退出` 结束。

终端入口比网页多一件事：每轮提问都会打印**三层检索各自命中了什么**，方便观察检索效果。
网页端刻意**不给用户看检索过程**，事件里只带最终答案。

**它的行为特点**（和闲聊模块有本质区别）：

- **每一句都会走 RAG 检索**，不会像聊天机器人那样闲聊。
- **只回答知识库里有的内容**。如果知识库里查不到答案，它会回答「抱歉，我在知识库里没有找到相关答案。」
- **不编造**。即使检索到的片段与问题只是表面相关，只要不足以回答，它也会明确说没找到。
- **一问一答，不留记录**：不带历史上下文，也不写数据库。网页端切到客服模块时左侧栏会整体收起。

**它不是聊天机器人。** 聊天机器人的职责已经由 ctOS 主模块（闲聊模块）承担了，
智能客服只负责「查资料回答问题」这一件事。

---

## 四、智能客服模块技术说明

### 4.1 模块定位

智能客服是一个 RAG 模块。RAG 的全称是检索增强生成，思路是：
**先从知识库里检索出相关资料，再把这些资料交给大模型，让模型基于资料作答。**

这样做的好处是：模型的回答有据可查，而不是凭记忆编造。

模块采用 **三层检索** 结构：

| 层级 | 名称 | 实现方式 |
| --- | --- | --- |
| 第一层 | 关键词检索 | jieba 分词 + BM25 排序 |
| 第二层 | 向量检索 | 智谱 embedding-3 + Chroma 向量库 |
| 第三层 | 混合检索 | 前两层结果按名次加权打分，重新排序后取前几名 |

### 4.2 图结构

模块基于 LangGraph，由「状态、节点、图」三部分构成。

这一版是最小可跑的完整流程，一条直线，没有分支也没有循环：

```
START → retrieve → generate → END
```

- `retrieve` 节点：依次跑三层检索，结果都写进状态
- `generate` 节点：用第三层（混合检索）的结果让大模型生成回答

之所以三层检索结果都保存在状态里，是为了在终端能看清每一层各命中了什么，方便调参对比。
真正交给生成节点使用的只有第三层的结果。

### 4.3 三个核心概念

**状态（State）** 是全图共享的一份数据。每个节点从上游字段读数据，把自己的产出写回对应字段。
智能客服的状态包含：用户问题、三层检索各自的结果、最终回答。

**节点（Node）** 是图上的一个处理步骤。本质上就是一个函数：收一份状态，返回要更新的那几个字段。

**图（Graph）** 负责把节点按顺序连起来，并管理状态的传递。

### 4.4 目录与文件职责

```
modules/customer/
├── graph.py                   # 组装图（定义节点和连线）
├── node.py                    # 图的节点：retrieve 检索、generate 生成
├── state.py                   # 图的状态定义
├── prompts.py                 # 提示词
├── stream.py                  # 流式封装（对外唯一入口 customer_stream）
├── rag_config.py              # 文档目录、向量库目录、集合名、embedding 模型
├── rag_ingest.py              # 一次性入库脚本
├── rag_store.py               # 知识库加载与复用（加载一次，全程共用）
├── rag_search.py              # 三层检索：关键词 / 向量 / 混合，都在这一个文件里
├── rag_eval.py                # 检索测评脚本（40 题）
├── eval/golden.json           # 测评题库
└── data/
    ├── docs/                  # 知识库原始文档（放 .md 文件）
    └── chroma/                # 向量库落盘目录（不入 git）
```

**`stream.py` 里的 `customer_stream()` 是模块对外的唯一出入口**，它是个 `async` 生成器，
把图的产出转成 SSE 事件。Web 层（`api/main.py` 的 `/customer/chat` 路由）只管调用它，
不需要知道图长什么样、有几个节点、三层检索怎么跑。

事件协议和出行模块保持同一套命名，前端好复用：

| 事件 | 含义 |
| --- | --- |
| `START` | 开始跑图 |
| `TOKEN` | 答案的逐字碎片（打字机效果） |
| `DONE` | 答案定稿（前端用它重渲染，纠正逐字拼接的偏差） |
| `ERROR` | 跑图途中出错 |

一个实现细节：`graph.stream()` 是同步的，直接调用会卡住事件循环，导致期间连首页都无响应。
所以流式封装把图丢进一个后台线程跑，产出经由队列交回异步侧，事件循环始终是空闲的。

### 4.5 第一层：关键词检索

关键词检索用的是 **BM25** 算法。BM25 是衡量「查询词和文档有多相关」的经典算法，
纯靠词频统计，不需要向量，速度很快。

具体做法是：

1. 用 jieba 把用户问题和每段文档都切成词
2. 用 BM25 给每段文档打相关性分数
3. 按分数从高到低排序，取前 3 段（`TOP_K = 3`），分数为 0 的不算命中

这一层对**专有名词特别准**。比如问「chromadb」，BM25 能精确匹配到含这个词的段落。

### 4.6 第二层：向量检索

向量检索把文本转成一组数字（向量），再比较向量之间的相似度，找语义最接近的段落。

使用的模型是智谱的 `embedding-3`，输出 2048 维向量。
向量存在 Chroma 向量库里。

这一层的优势是**语义匹配**：即使用户的问法和文档的用词不一样，也能命中。
比如用户问「这是什么系统」，能匹配到文档里的「多模块 AI 应用」。

**注意**：向量检索无论相不相关，**总会返回最接近的那几条**（这里同样是 `TOP_K = 3`）。
所以它单独用的时候容易引入无关内容，这也是需要第三层混合检索的原因之一。

### 4.7 第三层：混合检索

混合检索把前两层的结果合并起来，但**不是简单地「关键词排前面、向量排后面」**，
而是按名次加权打分后重新排序。

这样做的道理是：关键词擅长专有名词，向量擅长语义相近，**两边的并集覆盖面比任何一层都大**。

打分规则（RRF 思路的简单版）：

- 每层第 1 名得 3 分，第 2 名得 2 分，第 3 名得 1 分
- 同一个片段被两层都命中，分数相加
- 最后按总分从高到低，最多取前 4 条（`MAX_HITS = 4`）交给模型

打分是按**该层实际返回的条数**倒着数的（代码里是 `len(hits) - position`），
不是写死 3/2/1。正常情况下每层都是 3 条，所以正好是 3/2/1；
但某一层因为分数为 0 被过滤、或库里内容很少而只返回 2 条时，那层就变成 2/1，
两层相加后仍能正常比较（分数低的层天然吃亏，这符合预期）。

这里有个容易看漏的细节：**`MAX_HITS = 4` 是上限，不保证一定给 4 条**。
两层各取 3 条，去重后留下 0~6 个不同片段，再从中取前 4 条：

| 情况 | 合并后 | 实际交给模型 |
| --- | --- | --- |
| 两层完全不重叠 | 6 条 | 4 条 |
| 部分重叠 | 4~5 条 | 4 条 |
| 两层完全相同 | 3 条 | 3 条 |
| 只有一层命中 | 3 条 | 3 条 |
| 两层都没命中 | 0 条 | 0 条（提示词里放「没有检索到任何资料」） |

**为什么要加权**：如果直接按顺序截断，关键词层排第 3 的片段会永远压过向量层排第 1 的片段，
这显然不合理——向量层的第一名往往比关键词层的第三名更相关。
加权之后，只在单层排后面的「万金油片段」总分上不去，会被真正相关的片段压下去。

需要说明的是：加权只在**两层结果有分歧**时起作用。
如果两层检索到的是同一批片段（比如问了一个完全无关的问题），加权无从发挥。
这种情况下靠的是提示词的约束，让模型回答「没找到答案」。

### 4.8 知识库的入库流程

知识库的原始文档放在 `data/docs/` 目录下，格式是 Markdown。

入库是**一次性操作**，执行：

```bash
python -X utf8 -m modules.customer.rag_ingest
```

线上要在容器里跑：`docker exec ctos2-app python -m modules.customer.rag_ingest`。

入库脚本做四件事：

1. **读文档**：扫描 `data/docs/` 下所有 `.md` 文件（不含子目录）
2. **切块**：按 Markdown 的二级标题（`## `）切成块，每块自带标题。
   如果某个标题下的内容太长（超过 600 字符），会再按**整行**分组切开，
   保证不会从句子中间劈开
3. **向量化**：调智谱接口把每块文本转成向量。
   智谱接口限制一次最多传 64 条，脚本会自动分批（`MAX_EMBED_BATCH = 64`），
   所以文档块数超过 64 也能一次跑完，不用手动处理
4. **写入 Chroma**：连同正文和来源文件名一起存进去

**重复入库是安全的**：每次入库会先删掉同名集合再重建，所以不会出现旧数据累积。

**改了文档之后必须重新入库**，否则检索到的还是旧内容。

另外，知识库文本是在**加载时**读进内存的，所以重新入库之后要**重启服务**（或手动调用 `reset_store()`）
才会读到新内容。

### 4.9 提示词如何约束「不编造」

智能客服能守住「不知道就说不知道」，靠的是提示词里的硬性规则。规则包括：

1. 回答**只能**来自参考资料，不许用模型自己的知识补充，不许推测，不许编造
2. 参考资料里没有相关内容时，只回一句「抱歉，我在知识库里没有找到相关答案。」
3. 不要额外解释，不要猜，不要说「可能」「建议你」之类的话
4. 不要提到「参考资料」「知识库」「文档片段」这类词

需要说明的是：检索不到资料时，代码**不会跳过模型调用**，而是照样调用模型，
只是在参考资料的位置放一句「（没有检索到任何资料）」。
这样「答不出来」这句话也由模型统一输出，代码里不需要写判断分支。

---

## 五、常见问题 FAQ

### 关于使用

**Q：克隆下来为什么跑不起来？**
A：因为这个项目**不含任何 API 密钥**，必须自己申请并填进 `config/.env`。
一共需要 4 个：DeepSeek（对话 + 联网搜索，必需）、智谱（客服向量化，必需）、高德（算路线），
外加 PostgreSQL 的连接参数和登录用的 `JWT_SECRET_KEY`。
另外克隆下来时数据库和向量库都还不存在，要先跑 `core/db.py` 建表、
再跑 `rag_ingest` 入库，这两个都是一次性的初始化步骤。
只拿到 DeepSeek 密钥的话，闲聊和出行都能用（联网搜索复用同一个密钥），只有客服会不可用。

**Q：怎么启动这个项目？**
A：三步。① 装依赖 `pip install -r config/requirements.txt`；
② 建表 `python -X utf8 -m core.db`；
③ 启动服务 `python -X utf8 -m api.main`，然后在浏览器打开 <http://127.0.0.1:8080/>。
如果是第一次用智能客服，中间还要多跑一次入库脚本 `python -X utf8 -m modules.customer.rag_ingest`。
**不想自己装的话，直接用线上的 <https://ctos2.cn> 就行，注册后就能用。**

**Q：怎么安装依赖？**
A：在项目根目录执行：

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r config/requirements.txt
```

依赖清单在 `config/requirements.txt` 里，分 Web、出行模块、客服模块、数据库、认证五组。
如果不想装 Python，也可以直接用 Docker：`docker compose --env-file config/.env up -d`。

**Q：启动后端口是多少？访问哪个地址？**
A：本地默认端口是 8080，地址是 <http://127.0.0.1:8080/>；
线上地址是 <https://ctos2.cn>，走标准 443 端口和 HTTPS。
端口由环境变量 `PORT` 控制，默认值写在 `api/main.py` 末尾。

**Q：系统支持哪些大模型？**
A：对话和图上的推理用的是 DeepSeek，通过 `config/.env` 里的 `DEEPSEEK_MODEL` 配置。
向量化用的是智谱的 `embedding-3`。两者是不同厂商的模型，各司其职。

**Q：端口可以改吗？**
A：可以，设环境变量 `PORT` 即可（本地或容器都适用），不用改代码。
前端请求后端用的是相对路径（同源），不写死端口，所以不用改。

**Q：需要注册才能用吗？**
A：不需要。打开 <https://ctos2.cn> 会先自动进入一个**访客空间**（独立租户，记录只存在当前浏览器），
想跨设备保留记录再点侧栏底部「账号登录」注册或登录。每个账号是一个独立租户，看不到别人的会话记录。

**Q：智能客服为什么不跟我闲聊？**
A：这是刻意设计的。智能客服的职责是「查资料回答问题」，不是聊天。
你每次提问它都会去检索知识库，查不到就直说查不到。
聊天功能由 ctOS 主模块承担。

**Q：智能客服说「没找到答案」，是不是坏了？**
A：不一定是坏了。它只在知识库里确实没有相关内容时才这样回答。
可以先确认你要问的内容是否已经写进 `data/docs/` 下的文档里，并且**改完文档后重新跑过入库脚本**。

**Q：智能出行的天气准吗？**
A：天气数据来自 Open-Meteo 的真实预报，不是模型生成的。
但预报本身有不确定性，且最远只能查到未来 15 天左右。

**Q：对话记录会丢吗？**
A：不会。闲聊会话存在 `sessions` / `messages`，出行记录存在 `trip_chats` / `trip_sessions` 等表，
都在 PostgreSQL 数据库 `ctos2` 里，重启服务和刷新页面都还在。
只有智能客服的问答不留记录。

### 关于开发

**Q：怎么修改知识库内容？**
A：两步。第一，改 `data/docs/` 下的 Markdown 文件（或新增文件）；
第二，重新执行 `python -X utf8 -m modules.customer.rag_ingest`。
只做第一步不生效。改完记得重启服务。线上则是先 `docker exec ctos2-app python -m modules.customer.rag_ingest`，再重启容器。

**Q：检索返回几条可以调吗？**
A：可以。关键词层和向量层各有一个 `TOP_K` 常量控制返回条数（都在 `rag_search.py` 里，当前都是 3）；
混合层还有 `MAX_HITS` 控制最终交给模型的上限（`rag_search.py`，当前是 4）。

**Q：切块的大小可以调吗？**
A：可以。`rag_ingest.py` 里的 `MAX_CHUNK_CHARS` 控制单块最大字符数，当前是 600。

**Q：文档多了以后入库报 400 怎么办？**
A：不用管，已经处理了。智谱 embedding 接口限制一次最多传 64 条文本，
高版本脚本会自动按 `MAX_EMBED_BATCH = 64` 分批提交，块数再多也能一次跑完。
这个常量在 `rag_ingest.py` 里，一般不需要改。

**Q：为什么向量检索总会返回结果？**
A：因为向量检索本质是「找最接近的几条」，无论问题是否和知识库相关，它都会算出距离并返回前几名。
这是正常现象。真正决定「能不能答」的是提示词的约束，不是检索有没有返回。

**Q：可以在前端页面上用智能客服吗？**
A：可以。四个能力都已接入页面，点顶栏的「智能客服」即可。

### 关于排错

**Q：报错说 `ModuleNotFoundError: No module named 'chromadb'`（或 jieba、rank-bm25）怎么办？**
A：这三个包是智能客服模块（RAG 检索）的依赖。确认你已经执行过：
```bash
pip install -r config/requirements.txt
```
如果还是报错，很可能是**装到了别的 Python 环境里**。
请检查你当前用的 Python 是不是项目里的 venv：
```bash
python -c "import sys; print(sys.executable)"
```
正确的结果应该指向项目目录下的 `venv\Scripts\python.exe`。
如果指向的是系统全局 Python，说明依赖装错了地方。

**Q：编辑器（VS Code 等）里 import 报红波浪线，但程序能跑，为什么？**
A：这是编辑器选错了 Python 解释器，用的是系统全局 Python 去解析代码，
而依赖装在项目 venv 里，所以编辑器找不到包。
解决办法：`Ctrl+Shift+P` → `Python: Select Interpreter` → 选择项目下的 `venv\Scripts\python.exe`。
选完红线就会消失。**这不影响程序运行**，只是编辑器的提示。

**Q：智能客服输出中文乱码怎么办？**
A：Windows 控制台默认编码是 GBK。运行时加上 `-X utf8` 参数即可：
```bash
python -X utf8 -m modules.customer.stream
```

**Q：报错说缺少 `ZHIPU_API_KEY` 怎么办？**
A：这是向量检索必需的密钥。请在 `config/.env` 里补上：
```
ZHIPU_API_KEY=你的密钥
```
代码在取不到这个密钥时会主动报错，而不是等到调用接口时抛一个看不懂的认证失败。

**Q：智能客服启动时报「没找到向量数据库」/「没有这个集合」/「向量数据库是空的」？**
A：说明还没入库，或者入库目录被删了。跑一次：
```bash
python -X utf8 -m modules.customer.rag_ingest
```
这几种情况的报错文本里也都会直接提示这条命令。

**Q：改了 `data/docs/` 里的文档，客服回答还是旧的？**
A：两步都做了吗：① 重新跑 `rag_ingest.py`；② **重启服务**。
知识库是在加载时读进内存的，只重新入库不重启，进程里还是旧的那一份。

**Q：出行模块提示「没能识别出目的地」怎么办？**
A：说明表达太模糊了。把话说具体一点，比如「下周想去杭州玩3天」，
明确说出目的地、天数和出发时间。

---

## 六、部署与运维

### 6.1 环境要求

- Python 3.14（开发环境实测版本：3.14.5）；或者只装 Docker，用镜像跑
- PostgreSQL 17（本地开发自己装；Docker 部署时由 `db` 容器提供，不用另外装）
- 能访问外网：需要调用 DeepSeek、智谱、高德、Open-Meteo 的接口
- 线上：一台能跑 Docker 的服务器 + 一个域名（本站用的是 `ctos2.cn`，DNS 和 HTTPS 托管在 Cloudflare）

### 6.2 依赖清单

依赖统一写在 `config/requirements.txt`，分五组：

```
fastapi
uvicorn[standard]
python-dotenv
# 智能出行模块（LangGraph agent）用的
langgraph==1.2.10
langgraph-prebuilt==1.1.0
langgraph-checkpoint-sqlite==3.1.2
langchain==1.3.14
langchain-core==1.5.3
langchain-openai==1.4.2
openai==2.53.0
httpx
# 智能客服模块（RAG 三层检索）用的
chromadb==1.5.9
jieba==0.42.1
rank-bm25==0.2.2
# 数据库：从 SQLite 迁到 PostgreSQL 后加的
psycopg[binary]
psycopg_pool
# 认证：注册登录用
python-jose[cryptography]
bcrypt
```

其中 `chromadb`、`jieba`、`rank-bm25` 三个是智能客服模块专用的，
`psycopg` 系列是数据库驱动，`python-jose` / `bcrypt` 是登录认证用的。

`langgraph-checkpoint-sqlite` 用来给人工确认（HITL）存暂停现场：
路线决策和旅游攻略在等你选择时会停住，现场就存在 `databases/route_checkpoints.sqlite` 里。
业务数据（会话、账号、出行记录）仍然走 `databases/` 那套自己基于 `psycopg` 写的代码，
这个 sqlite 文件只存“暂停中的流程”，是运行产物，已经在 `.gitignore` 里。

### 6.3 启动顺序

1. 确认 `config/.env` 已填好所有密钥（含 `ZHIPU_API_KEY`、`PG_*`、`JWT_SECRET_KEY`）
2. 建表：`python -X utf8 -m core.db`
3. 智能客服要用的话，先跑一次入库脚本
4. 启动 Web 服务：`python -X utf8 -m api.main`

用 Docker 的话只有三步：`docker compose --env-file config/.env up -d` →
`docker exec ctos2-app python -m core.db` → `docker exec ctos2-app python -m modules.customer.rag_ingest`。

### 6.4 数据存放位置

| 数据 | 位置 | 说明 |
| --- | --- | --- |
| 租户 / 账号 | PostgreSQL 表 `tenants` / `users` | 一个注册用户 = 一个租户，密码存 bcrypt 哈希 |
| 闲聊 / 角色扮演会话 | PostgreSQL 表 `sessions` / `messages` | 会话与消息，两种玩法共用 |
| 角色扮演 | `role_play_sessions` / `role_play_memories` / `role_play_roles` | 会话用的是哪个角色、角色记得什么、自己写的角色 |
| 出行记录 | `trip_chats` / `trip_sessions` / `trip_user_inputs` / `trip_ai_outputs` | 一轮出行 = 主表一行 + 子表各一行 |
| 用户反馈 | PostgreSQL 表 `feedback` | 评价 + 文字，只给维护者看 |
| 向量库 | `modules/customer/data/chroma/` | Chroma 落盘的向量数据，Docker 里是挂载进去的目录 |
| 知识库原文 | `modules/customer/data/docs/` | Markdown 文档 |
| 人工确认的暂停现场 | `databases/checkpoints/` | 路线决策 / 旅游攻略停下来等你选择时的现场，Docker 里也是挂载进去的目录 |

Docker 部署时数据库数据在命名卷 `ctos2-pgdata` 里，删容器不丢；
向量库目录和检查点目录被挂载出来，重建容器不用重新入库，**没选完的方案重建后也能接着选**。
这两个目录都已被 `.gitignore` 排除，不会进代码仓库。

> 在 Linux 服务器上用 Docker 时，如果容器内用户（uid 1000）写不了
> `databases/checkpoints/`，执行一次 `sudo chown -R 1000:1000 databases/checkpoints` 即可。
> Windows / Docker Desktop 不需要这一步。

### 6.5 备份与恢复

- **数据库**（Docker）：`docker exec ctos2-db pg_dump -U ctos_app ctos2 > backup.sql`，
  恢复用 `docker exec -i ctos2-db psql -U ctos_app ctos2 < backup.sql`
- **数据库**（本地直连）：`pg_dump -U ctos_app ctos2 > backup.sql`
- **向量库**：可以直接复制整个 `data/chroma/` 目录；
  但因为向量库可以随时由入库脚本重建，更稳妥的做法是**备份 `data/docs/` 里的原始文档**，
  需要时重新跑一次入库脚本

### 6.6 常见运维操作

**更新知识库**：
```bash
# 1. 修改 data/docs/ 下的文档
# 2. 重新入库
python -X utf8 -m modules.customer.rag_ingest
# 3. 重启服务，否则内存里还是旧知识库
#    线上等价于：
#    docker exec ctos2-app python -m modules.customer.rag_ingest
#    docker compose --env-file config/.env restart app
```

**单独调试出行模块**（不启动 Web 服务）：
```bash
python -X utf8 -m modules.trip.cli
```

**单独调试智能客服模块**：
```bash
python -X utf8 -m modules.customer.stream
```

**查看/导出聊天记录**：
```bash
# 列出所有会话
python -X utf8 -m databases.db_view
# 看某个会话的完整对话
python -X utf8 -m databases.db_view show 3
```

**线上健康检查与日志**：
```bash
curl https://ctos2.cn/health
docker compose --env-file config/.env logs -f app
```

---

## 七、项目目录结构

```
ctOS2.0/
├── api/                        # HTTP 接口层
│   ├── main.py                 # ★ FastAPI 入口，所有业务路由都在这里
│   └── routes/auth.py          # 认证路由 /auth/register、/auth/login、/auth/me
├── core/                       # 跨模块公用
│   ├── llm.py                  # 唯一的模型客户端 get_llm()，也负责加载 .env
│   ├── db.py                   # ★ PostgreSQL 连接 + 统一建表入口
│   ├── auth.py                 # bcrypt 密码哈希 + JWT 签发校验
│   └── sse.py                  # SSE 事件打包
├── databases/                  # 表和读写
│   ├── db_tenant.py            # 全局身份表 tenants
│   ├── db_auth.py              # 用户表 users
│   ├── db_chat.py              # 闲聊表：sessions / messages
│   ├── db_trip.py              # 出行表：trip_chats / trip_sessions / trip_user_inputs / trip_ai_outputs
│   └── db_view.py              # 命令行查看工具
├── modules/                    # 三个业务模块
│   ├── chat/                   # 闲聊：graph / node / prompts / state / stream / sessions
│   ├── trip/                   # 智能出行：graph / node / tools / prompts / route / state / stream / understand / cli
│   └── customer/               # 智能客服（RAG）：graph / node / state / prompts / stream / rag_* / eval
├── static/                     # 前端（无构建步骤）
│   ├── index.html
│   ├── css/style.css           # 模板原样式
│   ├── css/modules.css         # 出行卡片、客服气泡、登录页等
│   └── js/
│       ├── common/             # 公用：配置、工具、SSE、打字机、多选、中断
│       ├── auth.js             # 登录页
│       ├── app.js              # 核心：状态、侧边栏、闲聊、模块切换
│       ├── trip.js             # 智能出行
│       └── customer.js         # 智能客服
├── screenshot/                 # README 用的界面截图
├── docs/                       # 项目文档（architecture / files / deployment）
├── config/
│   ├── YOUR_config.env         # 配置模板（入库）
│   ├── .env                    # 真实密钥（已 gitignore，不入库）
│   └── requirements.txt
├── Dockerfile                  # 镜像构建（python:3.14-slim，非 root，带健康检查）
└── docker-compose.yml          # 应用 + 数据库两个容器
```

### 关于前端

前端**没有任何构建步骤**。改 `static/css/*.css` 或 `static/js/*.js`，
保存后刷新浏览器就能生效，不需要执行任何编译或打包命令。

加载顺序是 `common/*.js` → `app.js` → `trip.js` / `customer.js`，
后面加载的依赖前面定义的全局变量（`$`、`esc`、`md`、`API`、`state` 等），**调整加载顺序会导致报错**。
详见 `static/README.md`。

后端为了提供静态资源，在 `api/main.py` 里挂载了静态目录：

```python
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
```

挂载在 `/static` 前缀下，不会和已有的 `/chat`、`/sessions`、`/trip/...`、`/customer/...` 等路由冲突。
线上直接访问 <https://ctos2.cn/> 就是同一份页面。

---

## 八、安全说明

- 所有密钥都从 `config/.env` 读取，**代码里不写死任何凭据**
- `.gitignore` 已排除 `config/.env`、`*.env`、`venv/`、`__pycache__/`、`*.sql`、`*.db`、向量库目录、测评结果等
- 只有配置模板 `config/YOUR_config.env` 会入库，里面有占位符，不含真实值
- **所有业务接口都要登录**：请求头带 `Authorization: Bearer <token>`，未登录返回 401
- 密码存 bcrypt 哈希；登录失败时不区分「邮箱不存在」和「密码错误」，避免被用来枚举账号
- **数据库不直接暴露到公网**：Docker 部署时 PostgreSQL 只在内部网络 `ctos2-net` 里，
  只有 `app` 容器能连
- HTTPS 由 Cloudflare 提供，应用本身不处理证书
- 如果不小心把密钥提交进了仓库，**必须立刻去对应平台轮换密钥**。
  删除文件并不能让已泄露的密钥失效，因为提交历史里还留着

---

## 九、数据库表结构

项目使用 PostgreSQL 数据库：`ctos2`，共 12 张表。
所有模块共用同一个数据库、同一套连接函数（`core/db.py` 的 `get_conn()` / `query()` / `execute()`）。

建表入口是 `core/db.py` 的 `create_all_tables()`，它会先建全局身份表 `tenants`，
再依次调用各模块的建表函数。建表语句都用了 `CREATE TABLE IF NOT EXISTS`，重复执行是安全的。

连接层每个操作开一个短连接，用完自动关、出错自动回滚；`transaction()` 把多条写入包成一个事务。
**不要另写第二份开连接的代码**，所有 SQL 都走 `core/db.py` 提供的函数。

**多租户**：`tenants` 是一切的根，`users` / `sessions` / `trip_chats` / `trip_sessions` 都外键引用它，
所有业务表都带 `tenant_id` 列。API 层从登录 token 解析出当前租户，一路传下去做数据隔离。

### 9.0 身份：`tenants` / `users`

| 表 | 字段 | 说明 |
| --- | --- | --- |
| `tenants` | `id` / `name` / `slug` / `created_at` | 租户，`slug` 唯一；建表时会插入一个 `default` 兜底租户 |
| `users` | `id` | 主键，自增 |
| | `tenant_id` | 外键 → `tenants.id`，`ON DELETE CASCADE` |
| | `email` | 唯一 |
| | `password_hash` | bcrypt 哈希，**不存明文** |
| | `display_name` | 显示名，可为空 |
| | `created_at` / `last_login_at` | 创建时间 / 最近登录时间 |

目前是「一人一户」：一个用户注册时自动创建自己的租户，所以用户和租户是一对一。

### 9.1 闲聊：`sessions` / `messages`

| 表 | 字段 | 说明 |
| --- | --- | --- |
| `sessions` | `id` | 主键，自增 |
| | `tenant_id` | 所属租户 |
| | `title` | 会话标题（用户第一句话的前 14 个字） |
| | `created_at` / `updated_at` | `updated_at` 在每次追加消息时刷新，列表按它倒序 |
| `messages` | `id` | 主键，自增 |
| | `session_id` | 外键 → `sessions.id`，`ON DELETE CASCADE` |
| | `role` | 只能是 `user` 或 `assistant` |
| | `content` | 消息正文 |
| | `created_at` | 创建时间 |

索引：`ix_sessions_tenant`（`tenant_id, updated_at DESC`）、`ix_messages_session`（`session_id`）、
`ix_messages_tenant`（`tenant_id`）。

### 9.2 出行：`trip_sessions` / `trip_user_inputs` / `trip_ai_outputs`

| 表 | 字段 | 说明 |
| --- | --- | --- |
| `trip_sessions` | `id` | 主键，自增 |
| | `title` | 标题，优先用目的地，没有就取用户第一句话的前 14 个字 |
| | `turn_kind` | `ROUTE`（路线决策）/ `TRAVEL`（旅游攻略）/ `CHAT`（闲聊分流） |
| | `destination` / `days` / `start_date` | 从需求里解析出来的出行要素 |
| | `created_at` | 本地时间 |
| `trip_user_inputs` | `id` / `trip_id` / `content` / `created_at` | `trip_id` 外键 → `trip_sessions.id`，级联删除 |
| `trip_ai_outputs` | `id` / `trip_id` | `trip_id` 外键 → `trip_sessions.id`，级联删除 |
| | `weather` / `spots` / `itinerary` / `route_plan` | 攻略四段产出 |
| | `route_need` / `route_compare` / `route_decision` / `route_tips` | 路线决策四段产出 |
| | `chat_reply` | 闲聊分流的回复 / 创建时间 |

两个子表的 `trip_id` 上都有索引。

存一轮出行记录 = 主表插一行 + 两个子表各插一行，在同一个事务里完成，
要么全成、要么全不成，不会出现「有主表没子表」的半截数据。

### 9.3 角色扮演：`role_play_sessions` / `role_play_memories` / `role_play_roles`

角色扮演**没有自己的图和自己的会话表**，它复用 9.1 的 `sessions` / `messages`，
另外用这三张表记录角色相关的东西：

| 表 | 字段 | 说明 |
| --- | --- | --- |
| `role_play_sessions` | `session_id` | **主键，同时外键 → `sessions.id`**，级联删除 |
| | `tenant_id` / `role_id` / `created_at` | 哪个会话用的是哪个角色 |
| `role_play_memories` | `tenant_id` + `role_id` | 复合主键，**一个角色一份记忆**（不按会话） |
| | `summary` | 摘要正文，200 字以内，覆盖式更新 |
| | `rounds` | 已经聊了几轮，每满 6 轮触发一次整理 |
| | `updated_at` | 最近整理时间 |
| `role_play_roles` | `id` | 主键，自增；对外 id 是 `custom_<id>` |
| | `tenant_id` | 所属租户，按租户隔离 |
| | `name` / `emoji` / `tagline` | 名字、头像 emoji、一句话标签 |
| | `age` / `gender` / `personality` / `deeds` / `background` / `extra` | 用户填写的档案 |
| | `speaking` / `boundaries` / `opening` | 说话方式、不会做什么、开场白 |
| | `source` | `custom`（自己写的）/ `ai_search`（AI 查出来的） |
| | `created_at` | 创建时间 |

**预设角色不在这三张表里**，它们写在模块代码 `modules/roleplay/presets.py` 中，不吃数据库。

删自定义角色时会在一个事务里删掉：它的所有会话（`sessions` 级联带走 `messages`）、
它的记忆（`role_play_memories`）、以及角色本身（`role_play_roles`）。

### 9.4 反馈：`feedback`

| 字段 | 说明 |
| --- | --- |
| `content` / `contact` | 反馈正文、联系方式；都用空串而不是 NULL |
| `rating` | 存中文原文（很满意 / 满意 / 一般 / 不太满意），不存 1~5 的数字 |
| `page` | 在哪个页面提交的：`chat` / `trip` / `customer` / `login` |
| `tenant_id` | 可以为空——没登录也能提交，登录了就顺带记下是谁 |
| `user_agent` / `created_at` | 排查用信息、提交时间 |

反馈表独立存在，**不关联任何其他表**，也不对外提供查询接口（只给维护者用命令行看）。

### 9.5 智能客服

客服模块**不写数据库**，一问一答不留记录。它的「知识」只落在本地 Chroma 目录里。

---

## 十、扩展与二次开发

### 增加一个新的能力模块

系统的设计是「一个 app 挂多个能力」，新增模块的步骤大致是：

1. 在 `modules/` 下建一个模块目录
2. 在图里定义状态、节点，然后组装成一张图
3. 在模块内写一个流式封装文件，对外只暴露一个生成器（参照 `modules/trip/stream.py` 里的 `trip_stream` / `modules/customer/stream.py` 里的 `customer_stream`）
4. 在 `api/main.py` 里加一个路由，把生成器塞进 `StreamingResponse`；**记得像别的业务路由一样调 `tenant_of(authorization)`**，否则新接口会绕过登录和数据隔离
5. 在前端加一个面板和请求逻辑（参照 `static/js/trip.js` / `customer.js`），并把新视图加进 `static/js/common/config.js` 的 `VIEW_ORDER`
6. 要存数据的话，在 `databases/` 下加一个 `db_xxx.py`（命名参照现有的 `db_chat.py` / `db_trip.py`），表里带上 `tenant_id`，并把它的建表函数加进 `core/db.py` 的 `create_all_tables()`
7. 上线：走 `docker compose build` + `up -d`（线上环境见部署文档）

模块之间应该保持独立：各自的图、各自的提示词、各自的配置读取。
共享的只有 FastAPI 应用、端口、会话接口和数据库连接层。

### 改进智能客服的检索质量

第三层混合检索已经做了「按名次加权打分」。如果要进一步提升效果，可以考虑：

- **给向量检索加相关性阈值**：目前向量检索无论相不相关，总会返回最接近的 3 条。
  加上阈值后（距离超过某个值就丢弃），完全无关的问题会返回 0 条，混合层的输入更干净。
  难点是阈值定多少要试，定高了可能误杀。
- **重排（Rerank）**：对合并后的候选片段再做一次精排
- **调整每层条数**：把 `TOP_K` 和 `MAX_HITS` 调到更合适的值
- **优化切块策略**：调整 `MAX_CHUNK_CHARS`，或在切块时保留更多上下文

这些改动都集中在 `rag_search.py`（检索三层）和 `rag_ingest.py`（切块入库）里，不影响图的其它部分。
改完用 `python -X utf8 -m modules.customer.rag_eval` 跑一遍 40 题测评，对比改动前后的命中率。

### 智能客服的多轮是怎么做的

客服已经支持追问：前端把最近几轮对话放进请求体的 `history` 里，
`retrieve` 节点用「上一轮问题 + 当前问题」拼成检索串，`generate` 节点把最近 3 轮对话拼进提示词。
两个关键点都在 `node.py`：

- 检索串合并（`_build_search_query`）：解决「那它怎么配」这类没有主语的追问搜不到东西
- 历史截断（`HISTORY_TURNS = 3`）：历史太长会挤占上下文

目前客服问答**不落库**。如果要把问答也存进会话记录，参照闲聊的做法在 `databases/` 下加表，
并把建表函数加进 `core/db.py` 的 `create_all_tables()`。
注意：这会改变「客服不留记录」的现有设计意图。
