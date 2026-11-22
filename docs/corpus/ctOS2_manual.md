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
- **模型**：DeepSeek（对话与推理）、本机 Ollama qwen3-embedding（客服向量化）
- **外部工具**：DeepSeek Search 联网搜索、高德地图路径规划、Open-Meteo 天气
- **存储**：PostgreSQL 17 存会话、账号与出行记录（多租户）；Chroma 用于 RAG 向量库
- **检索**：jieba + rank-bm25 与向量混合
- **认证**：JWT + bcrypt
- **部署**：uvicorn 直接拉起服务（`python -m common.main`），线上由 Cloudflare 托管域名与 HTTPS
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
ZHIPU_API_KEY=         # 智谱密钥（历史配置项，现在客服向量化走本机 Ollama，不再需要它）
```

这个密钥是**必需的**：`rag_store.load_store()` 在加载知识库时会先检查它，取不到就直接抛错。
也就是说，`ZHIPU_API_KEY` 没配的话，智能客服模块启动不起来（Web 服务本身的其它模块不受影响）。

**安全提醒**：`config/.env` 已被 `.gitignore` 忽略，**不要**把真实密钥提交到代码仓库。
如果不小心提交过，请立刻去对应平台轮换密钥——仅仅删除文件并不能让密钥失效。

### 第三步：初始化数据库

```bash
python -X utf8 -m databases.schema
```

会建好全部 13 张表：`tenants`、`users`、`sessions`、`messages`、`trip_chats`、
`trip_sessions`、`trip_user_inputs`、`trip_ai_outputs`、`role_play_sessions`、
`role_play_memories`、`role_play_roles`、`feedback`。表已存在就跳过，不会动已有数据。
**没建表的话注册登录会直接报错**，这是最容易漏的一步。

### 第四步：智能客服入库（第一次使用前跑一次）

智能客服依赖本地向量库，需要先把 `docs/corpus/` 里的文档切块、向量化、入库：

```bash
python -X utf8 -m modules.customer.rag_ingest
```

**改了 `docs/corpus/` 里的文档后要重新跑一次。**

### 第五步：启动服务

```bash
python -X utf8 -m common.main
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
python -X utf8 -m databases.schema
```

### 4. 智能客服入库（第一次用才需要）

```bash
python -X utf8 -m modules.customer.rag_ingest
```

### 5. 启动服务

```bash
python -X utf8 -m common.main
```

看到 uvicorn 启动成功后，在浏览器打开 <http://127.0.0.1:8080/> 即可使用。
线上对应的地址是 <https://ctos2.cn/>。

### 快速启动（已经配置过之后的日常使用）

如果之前已经装好依赖、配好密钥、建好表、入过库，那以后每次只要一条命令：

```bash
python -X utf8 -m common.main
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
默认只监听 `127.0.0.1`（本机可访问）；要让局域网内其它设备访问，把 `HOST` 设成 `0.0.0.0`。

前端请求后端用的是**相对路径**（`API.base` 为空字符串），也就是同源访问，
所以**换端口前端也不用动**，线上和本地用的是同一份前端代码。

### 其它常用命令

| 用途 | 命令 |
| --- | --- |
| 建表 | `python -X utf8 -m databases.schema` |
| 客服入库 | `python -X utf8 -m modules.customer.rag_ingest` |
| 查知识库是否就绪 | `python -X utf8 -m modules.customer.rag_store` |
| 检索测评（40 题） | `python -X utf8 -m modules.customer.rag_eval` |
| 看数据库内容 | `python -X utf8 -m databases.tools.view` |
| 终端跑对话 | `python -X utf8 -m cli.chat` |
| 终端跑出行 | `python -X utf8 -m cli.trip` |
| 终端跑路线 | `python -X utf8 -m cli.route` |
| 终端跑攻略 | `python -X utf8 -m cli.guide` |
| 终端跑客服 | `python -X utf8 -m cli.customer` |
| 终端跑提示词 | `python -X utf8 -m cli.prompts` |

> 线上服务器上同样直接跑这些命令（工作目录为项目根目录）。

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

点击「智能出行」入口，只有一个输入框。**你描述需求，它自己判断该怎么办**——
不用选模式，它内部有路线规划和旅游攻略两项能力，但用哪个是它的事。

能直接回答的（不启动整套规划）：问有什么好玩的、要准备什么、带老人注意什么、天气、
打招呼道谢。

**能力一：路线规划**，例如：

```
从杭州东站到灵隐寺怎么走，带老人，少走路
```

1. **确认需求** —— 认出起点、终点、出发时间、偏好、同行人；太笼统会反问
2. **查候选** —— 高德查驾车 / 公交地铁 / 步行 / 骑行，摆出 2~4 条真实方案
3. **暂停等你选** —— 不直接下结论，停下来让你选一条（有系统推荐，但以你的选择为准）
4. **写结论** —— 你选完之后，才写候选对比、推荐理由、出发提醒

不画地图、不做语音播报，只做路线分析和决策。

**能力二：旅游攻略**，例如：

```
下周想去杭州玩3天，带老人
```

1. **查询天气** —— 识别目的地、天数、出发日期，查真实天气并给出总结
2. **推荐景点** —— 结合天气和同行人推荐景点，必要时联网查门票、开放时间
3. **暂停等你勾选** —— 景点清单出来后停下来，可以去掉不想去的、补一个想去的
4. **安排行程** —— 按确认后的景点排出逐日行程
5. **写游玩建议** —— 节奏、预约、交通卡、同行人注意、避坑、备选、预算

**攻略只有一个暂停点**（勾景点），勾完一路跑完。攻略不规划距离和逐段路线，
需要精确路线时接着说（比如「第一天从酒店到灵隐寺怎么走」）；跨城大交通也不规划，
建议用 12306 或航司 App 查。

**每一步的产出都会实时显示在页面上。**

**不需要选模式**：说错类型也没关系，它自己判断。判断不够准的时候，
它会在回复里追问一句，或者直接把该做的做了。

后端契约只有一个入口：

| 路径 | 请求体 |
| --- | --- |
| `POST /trip/chat` | `{"query": "...", "history": [...], "chat_id": null}` |

`POST /guide/chat` 保留了一个转发壳，打它和打 `/trip/chat` 完全一样（老页面兼容用）。

响应都是 `text/event-stream` 的 SSE 事件流。

**人工确认（HITL）怎么实现**：暂停都用 LangGraph 的 `interrupt()`。
图跑到暂停节点会停住，把现场存进 `databases/checkpoints/route_checkpoints.sqlite`（运行产物，已 gitignore），
同时向前端发一个 `ASK` 或 `ASK_SPOTS` 事件。用户点完后调对应的接口继续：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/trip/route/choose` | 路线规划：用户选了哪个方案，继续写结论 |
| `POST` | `/guide/spots` | 旅游攻略：用户勾掉/补充了哪些景点，继续排行程 |

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

**没有自动分流了**：拆分之前进流程前会先用一次模型判断「这句话是路线、攻略还是闲聊」，
现在模式由页面上点，那层判断已经删除。多轮补充（「改成5天」「改成8点出发」）
由各模块自己的需求解析接住——解析时把前几轮说过的话一起喂给模型，一次调用搞定。
所以路线一轮的耗时比拆分前少了大约一次模型调用。

存库仍用 `trip_sessions.turn_kind` 区分：`ROUTE` 路线、`TRAVEL` 攻略、`CHAT` 只回了一句话。

**出行记录**存在另外三张表里，和闲聊的会话表分开。左侧栏在出行模式下会切换成出行记录列表，
每条带一个模式标签（路线 / 攻略 / 问答），点开可以恢复当时的结果，也可以删除。
拆分前的老记录里，攻略的第四段存在 `route_plan` 列，页面上显示成「详细路线（旧版）」。

对应接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/trip/list` | 最近的出行记录（默认最多 50 条） |
| `GET` | `/trip/{id}` | 单条记录的完整内容（含各段产出） |
| `DELETE` | `/trip/{id}` | 删除一条记录，子表级联删除 |
| `GET` | `/trip/ping`、`GET /guide/ping` | 两个模块各自的存活检测 |
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

- **问题都会走 RAG 检索**，不会像聊天机器人那样闲聊。
- **寒暄给一句引导**：问「你好」「谢谢」「在吗」这类，它回一句「我是 ctOS 的智能客服，
  只负责回答关于这个项目本身的问题……」，告诉你该问什么。这句不查资料、不调模型。
- **只回答知识库里有的内容**。如果知识库里查不到答案，它会回答「这个问题我在知识库里没有找到相关资料」+ 说明它能回答哪些范围 + 建议怎么继续问
- **不编造**。即使检索到的片段与问题只是表面相关，只要不足以回答，它也会明确说没找到。
- **能接追问**：前端把最近几轮对话一起带过来，先用它把「那它怎么配」这类省略主语的句子
  改写成一句自包含的检索查询，再拿改写结果去检索。
- **问答不写数据库**，刷新页面就没了（最近几轮上下文只存在浏览器内存里）。

**它不是聊天机器人。** 聊天机器人的职责已经由 ctOS 主模块（闲聊模块）承担了，
智能客服只负责「查资料回答问题」这一件事，寒暄只是引导你去提问，不会陪你聊。

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
| 第二层 | 向量检索 | 本机 Ollama 的 qwen3-embedding + Chroma 向量库 |
| 第三层 | 混合检索 | 前两层分数归一化后按权重相加，低于阈值的丢弃 |

### 4.2 图结构

模块基于 LangGraph，由「状态、节点、图」三部分构成。

```
START → rewrite → retrieve ─┬─(有资料)───→ generate → END
                             └─(没资料)──→ refuse   → END
```

- `rewrite` 节点：把当前问题改写成一句自包含的检索查询，并判断它是不是在问 ctOS。
  追问「那它怎么配」会先被补成「DeepSeek 密钥怎么配置」再去检索。
- `retrieve` 节点：跑混合检索，拿到带标题路径和分数的片段
- `generate` 节点：用检索结果让大模型生成回答
- `refuse` 节点：检索不到东西，或者判断明显是库外问题时，直接给固定拒答话术，**不调模型**

**拒答的判定为什么放在检索之后**：改写节点顺带会判断「是不是在问 ctOS」，
但模型对「像不像在问项目」和「知识库里有没有」经常分不清。
实测「怎么部署上线」被判成库外，而文档里有一整章部署与运维。
所以改成让检索结果当第二道关——模型说库外、但检索到强结果时仍然作答；
检索到的东西太弱、模型也说库外，才拒答。误拒比答得浅更难受。

### 4.3 三个核心概念

**状态（State）** 是全图共享的一份数据。每个节点从上游字段读数据，把自己的产出写回对应字段。
智能客服的状态包含：原问题、历史、改写后的检索查询、范围判断、检索结果、最终回答。

**节点（Node）** 是图上的一个处理步骤。本质上就是一个函数：收一份状态，返回要更新的那几个字段。

**图（Graph）** 负责把节点按顺序连起来，并在分叉点按条件决定走哪条路。

### 4.4 目录与文件职责

```
modules/customer/
├── graph.py                   # 组装图（节点 + 条件分支）
├── node.py                    # 图的节点：rewrite / retrieve / generate / refuse
├── state.py                   # 图的状态定义
├── prompts.py                 # 提示词（改写用一份、回答用一份）
├── stream.py                  # 流式封装（对外唯一入口 customer_stream）
├── rag_config.py              # 文档目录、向量库目录、集合名、embedding 模型
├── rag_ingest.py              # 一次性入库脚本
├── rag_store.py               # 知识库加载与复用（加载一次，全程共用）
├── rag_search.py              # 三层检索：关键词 / 向量 / 混合，都在这一个文件里
├── rag_eval.py                # 检索测评脚本（40 题）
├── eval/golden.json           # 检索测评题库（40 题）
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
3. 按分数从高到低排序，取前 8 段（`TOP_K = 8`）作为候选，分数为 0 的不算命中
4. 分数除以本次最高分，归一化成 0~1，再和向量层的分数按权重相加

这一层对**专有名词特别准**。比如问「chromadb」，BM25 能精确匹配到含这个词的段落。

索引的文本是「标题路径 + 正文」，所以标题里的词（比如「部署」）也能被关键词检索命中。

### 4.6 第二层：向量检索

向量检索把文本转成一组数字（向量），再比较向量之间的相似度，找语义最接近的段落。

向量模型跑在**本机的 Ollama** 上（默认 `qwen3-embedding:0.6b`），不走云端接口，
不需要密钥、不联网、不花钱。向量存在 Chroma 向量库里，集合用的是 **cosine 距离**。

这一层的优势是**语义匹配**：即使用户的问法和文档的用词不一样，也能命中。
比如用户问「这是什么系统」，能匹配到文档里的「多模块 AI 应用」。

**这一层有相似度下限**：余弦相似度低于 `MIN_VECTOR_SCORE`（0.36）的候选直接丢掉，
不参与后面的混合。这是「检索不到东西」这个信号的主要来源——
向量检索原本无论相不相关都会返回最接近的几条，加了阈值之后才能真正返回空结果。

### 4.7 第三层：混合检索

混合检索把前两层的结果合并，**按归一化分数加权求和**后重新排序。

这样做的道理是：关键词擅长专有名词，向量擅长语义相近，**两边的并集覆盖面比任何一层都大**。

打分规则：

- 关键词层：BM25 分数 ÷ 本层最高分，得到 0~1 的相对分
- 向量层：余弦相似度本身就是 0~1
- 两层按权重相加：关键词 0.5，向量 0.5（`KEYWORD_WEIGHT` / `VECTOR_WEIGHT`）
- 同一个片段被两层都命中，分数相加
- 总分低于 `MIN_HYBRID_SCORE`（0.28）的不要
- 最后按总分从高到低，最多取前 4 条（`MAX_HITS = 4`）交给模型

**为什么不按名次打分**：旧版是「每层第 1 名得最高分、第 2 名次之」，只看名次不看真实相关性。
结果是一个词都没匹配上的片段也能凭名次进榜，检索层永远返回 4 条，
上层分不清「有资料」和「没资料」，拒答只能靠提示词硬撑。
现在改成用分数，两层可以真正比较，也能拿到空结果。

权重和阈值都是拿 `rag_eval` 的 40 题扫出来的，不是拍脑袋定的：

| 切块上限 | 块数 | 命中@4 | 命中@1 | 可答题@1 |
| --- | --- | --- | --- | --- |
| 500 字 | 115 | 92.5% | 42.5% | 56.7% |
| 600 字 | 92 | 95.0% | 52.5% | 70.0% |
| **800 字** | **73** | **95.0%** | **60.0%** | **80.0%** |
| 1000 字 | 63 | 97.5% | 60.0% | 76.7% |

（「可答题@1」= 原词 + 同义改写 + 跨章节三类共 30 题的命中@1，库外题不计入。）

### 4.8 知识库的入库流程

知识库的原始文档放在 `docs/corpus/` 目录下，格式是 Markdown。

入库是**一次性操作**，执行：

```bash
python -X utf8 -m modules.customer.rag_ingest
```

线上服务器上同样直接跑：`python -X utf8 -m modules.customer.rag_ingest`。

入库脚本做四件事：

1. **读文档**：扫描 `docs/corpus/` 下所有 `.md` 文件（不含子目录）
2. **切块**：按 Markdown 的标题切成块，每块自带标题路径（见下面第二点）
3. **向量化**：调本机 Ollama 把「标题路径 + 正文」转成向量，
   接口限制一次最多传 64 条，脚本会自动分批，所以块数超过 64 也能一次跑完
4. **写入 Chroma**：连同正文、标题路径和来源文件名一起存进去

切块有两个容易踩的坑，都处理过了：

- **代码块里的 `#` 不是标题。** 文档里有大量 bash 片段，`# macOS / Linux`
  这种注释行长得和标题一模一样。不跳过代码块的话，切出来的块会带上假的章节名
  （改版前实测：整本手册一半的块标题路径都是「› source venv/bin/activate」）。
- **不在代码块中间下刀**，也不把代码块拆散，否则半条命令模型看不懂。

每块除了正文还存一行**标题路径**，格式是「文件名 › 一级标题 › 二级标题」。
检索结果里把它拼在正文前面给模型看，模型才知道这段话是从哪份文档的哪一节来的。

长度超过 `MAX_CHUNK_CHARS`（800 字符）的小节会再切小：优先按空行（段落）切，
段落本身就超长才按整行切，保证不会从句子中间劈开。短于 40 字符的碎片直接丢掉。

**重复入库是安全的**：每次入库会先删掉同名集合再重建，所以不会出现旧数据累积。

**改了文档之后必须重新入库**，否则检索到的还是旧内容。

另外，知识库文本是在**加载时**读进内存的，所以重新入库之后要**重启服务**（或手动调用 `reset_store()`）
才会读到新内容。

### 4.9 提示词如何约束「不编造」

智能客服能守住「不知道就说不知道」，靠的是提示词里的硬性规则。规则包括：

1. 回答**只能**来自参考资料，不许用模型自己的知识补充，不许推测，不许编造
2. 参考资料里**有一部分**能回答时，把那部分答完整，不要因为凑不齐整段就整个拒答
3. 不要提到「参考资料」「知识库」「文档片段」这类词，也不要把它来自哪一节的定位信息写进回答

**拒答时不调模型**：检索层一段都没找到（或者判断明显是库外问题）时，
代码直接返回一段固定话术，几十毫秒就回，不消耗额度。

那段话术不只说「没找到」，还告诉用户**这个客服能回答什么范围**、以及可以怎么继续问——
只回一句「抱歉，没找到」是个死胡同，用户不知道是自己问错了还是功能坏了。
话术本身不编造任何事实，只是在说明服务边界，和「不瞎编」不冲突。
这样「答不出来」这句话也由模型统一输出，代码里不需要写判断分支。

---

## 五、常见问题 FAQ

### 关于使用

**Q：克隆下来为什么跑不起来？**
A：因为这个项目**不含任何 API 密钥**，必须自己申请并填进 `config/.env`。
对话和客服只需要 1 个外部密钥：DeepSeek（对话 + 联网搜索，必需）、高德（算路线，出行用），
外加 PostgreSQL 的连接参数和登录用的 `JWT_SECRET_KEY`。
另外克隆下来时数据库和向量库都还不存在，要先跑 `databases/conn.py` 建表、
再跑 `rag_ingest` 入库，这两个都是一次性的初始化步骤。
只拿到 DeepSeek 密钥的话，闲聊和出行都能用（联网搜索复用同一个密钥），只有客服会不可用。

**Q：怎么启动这个项目？**
A：三步。① 装依赖 `pip install -r config/requirements.txt`；
② 建表 `python -X utf8 -m databases.schema`；
③ 启动服务 `python -X utf8 -m common.main`，然后在浏览器打开 <http://127.0.0.1:8080/>。
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
装完依赖后跑 `python -X utf8 -m common.main` 就把服务拉起来了。

**Q：服务在哪个端口上跑？启动后访问哪个地址？**
A：本地默认端口是 **8080**（`PORT` 环境变量控制），地址是 <http://127.0.0.1:8080/>。
线上地址是 <https://ctos2.cn>，走标准 443 端口和 HTTPS。

**Q：系统支持哪些大模型？**
A：对话和图上的推理用的是 DeepSeek，通过 `config/.env` 里的 `DEEPSEEK_MODEL` 配置。
向量化跑在本机 Ollama 上（默认 `qwen3-embedding:0.6b`），和对话用的 DeepSeek 是两个不同的模型，各司其职。

**Q：端口可以改吗？**
A：可以，设环境变量 `PORT` 即可（本地和线上都适用），不用改代码。
前端请求后端用的是相对路径（同源），不写死端口，所以不用改。

**Q：需要注册才能用吗？**
A：不需要。打开 <https://ctos2.cn> 会先自动进入一个**访客空间**（独立租户，记录只存在当前浏览器），
想跨设备保留记录再点侧栏底部「账号登录」注册或登录。每个账号是一个独立租户，看不到别人的会话记录。

**Q：智能客服为什么不跟我闲聊？**
A：智能客服的职责是「查资料回答问题」，不是聊天，聊天功能由 ctOS 主模块承担。
不过**打招呼、道谢这类寒暄它会给一句引导**：问「你好」「谢谢」「在吗」，
它会回一句「你好，我是 ctOS 的智能客服，只负责回答关于这个项目本身的问题……」，
告诉你该问什么。这句引导不查资料、不调模型，几十毫秒就返回。
除了寒暄以外的闲聊（比如「今天心情不好」）它仍然不接，会回没找到。

**Q：智能客服说「没找到答案」，是不是坏了？**
A：不一定是坏了。它只在知识库里确实没有相关内容时才这样回答。
可以先确认你要问的内容是否已经写进 `docs/corpus/` 下的文档里，并且**改完文档后重新跑过入库脚本**。

**Q：智能出行的天气准吗？**
A：天气数据来自 Open-Meteo 的真实预报，不是模型生成的。
但预报本身有不确定性，且最远只能查到未来 15 天左右。

**Q：对话记录会丢吗？**
A：不会。闲聊会话存在 `sessions` / `messages`，出行记录存在 `trip_chats` / `trip_sessions` 等表，
都在 PostgreSQL 数据库 `ctos2` 里，重启服务和刷新页面都还在。
只有智能客服的问答不留记录。

### 关于开发

**Q：怎么修改知识库内容？**
A：两步。第一，改 `docs/corpus/` 下的 Markdown 文件（或新增文件）；
第二，重新执行 `python -X utf8 -m modules.customer.rag_ingest`。
只做第一步不生效。改完记得重启服务。线上服务器上同样是先跑 `python -X utf8 -m modules.customer.rag_ingest`，再重启服务。

**Q：检索返回几条可以调吗？**
A：可以。关键词层和向量层共用一个候选数常量 `TOP_K`（`rag_search.py` 里，当前是 8）；
混合层有 `MAX_HITS` 控制最终交给模型的上限（同一文件，当前是 4）；
相关性门槛是 `MIN_VECTOR_SCORE` / `MIN_HYBRID_SCORE`，两层权重是 `KEYWORD_WEIGHT` / `VECTOR_WEIGHT`。
**改这些值之前先跑 `python -X utf8 -m modules.customer.rag_eval` 对比**，别凭感觉调。

**Q：切块的大小可以调吗？**
A：可以。`rag_ingest.py` 里的 `MAX_CHUNK_CHARS` 控制单块最大字符数，当前是 800。
这个数是拿 40 题测评扫出来的：600 太小（可答题命中@1 70%），1000 太大（76.7%），
800 时最好（80%）。改完要重新入库才生效。

**Q：文档多了以后入库报 400 怎么办？**
A：不用管，已经处理了。向量化接口限制一次最多传 64 条文本，
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

**Q：改了 `docs/corpus/` 里的文档，客服回答还是旧的？**
A：两步都做了吗：① 重新跑 `rag_ingest.py`；② **重启服务**。
知识库是在加载时读进内存的，只重新入库不重启，进程里还是旧的那一份。

**Q：出行模块提示「没能识别出目的地」怎么办？**
A：说明表达太模糊了。把话说具体一点，比如「下周想去杭州玩3天」，
明确说出目的地、天数和出发时间。

---

## 六、部署与运维

### 6.1 环境要求

- Python 3.14（开发环境实测版本：3.14.5）
- PostgreSQL 17（本机安装并启动）
- 能访问外网：需要调用 DeepSeek、高德、Open-Meteo 的接口；客服的向量化跑在本机，不占外网
- 线上：一台装了 Python 和 PostgreSQL 的服务器 + 一个域名（本站用的是 `ctos2.cn`，DNS 和 HTTPS 托管在 Cloudflare）

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
2. 建表：`python -X utf8 -m databases.schema`
3. 智能客服要用的话，先跑一次入库脚本
4. 启动 Web 服务：`python -X utf8 -m common.main`

这样四个步骤跑完，服务就在 `127.0.0.1:8080` 上起来了。

### 6.4 数据存放位置

| 数据 | 位置 | 说明 |
| --- | --- | --- |
| 租户 / 账号 | PostgreSQL 表 `tenants` / `users` | 一个注册用户 = 一个租户，密码存 bcrypt 哈希 |
| 闲聊 / 角色扮演会话 | PostgreSQL 表 `sessions` / `messages` | 会话与消息，两种玩法共用 |
| 角色扮演 | `role_play_sessions` / `role_play_memories` / `role_play_roles` | 会话用的是哪个角色、角色记得什么、自己写的角色 |
| 出行记录 | `trip_chats` / `trip_sessions` / `trip_user_inputs` / `trip_ai_outputs` | 一轮出行 = 主表一行 + 子表各一行 |
| 用户反馈 | PostgreSQL 表 `feedback` | 评价 + 文字，只给维护者看 |
| 向量库 | `modules/customer/data/chroma/` | Chroma 落盘的向量数据 |
| 知识库原文 | `docs/corpus/` | Markdown 文档 |
| 人工确认的暂停现场 | `databases/checkpoints/` | 路线决策 / 旅游攻略停下来等你选择时的现场 |

数据库数据在本机（或服务器）装的 PostgreSQL 里；向量库目录和检查点目录是运行产物，
重启服务不会丢，**没选完的方案重启后也能接着选**。
这两个目录都已被 `.gitignore` 排除，不会进代码仓库。

### 6.5 备份与恢复

- **数据库**：`pg_dump -U ctos_app ctos2 > backup.sql`，
  恢复用 `psql -U ctos_app ctos2 < backup.sql`
- **向量库**：可以直接复制整个 `data/chroma/` 目录；
  但因为向量库可以随时由入库脚本重建，更稳妥的做法是**备份 `docs/corpus/` 里的原始文档**，
  需要时重新跑一次入库脚本

### 6.6 常见运维操作

**更新知识库**：
```bash
# 1. 修改 docs/corpus/ 下的文档
# 2. 重新入库
python -X utf8 -m modules.customer.rag_ingest
# 3. 重启服务，否则内存里还是旧知识库（Ctrl+C 再重新 python -m common.main）
```

**单独调试某个模块**（不启动 Web 服务，每个 agent 一个入口）：
```bash
python -X utf8 -m cli.chat       # 对话
python -X utf8 -m cli.trip       # 出行（能看到 Agent 自己判断走哪条路）
python -X utf8 -m cli.route      # 路线规划子图
python -X utf8 -m cli.guide      # 旅游攻略子图
python -X utf8 -m cli.customer   # 智能客服
python -X utf8 -m cli.prompts    # 提示词生成
```

**单独调试智能客服模块**：
```bash
python -X utf8 -m modules.customer.stream
```

**查看/导出聊天记录**：
```bash
# 列出所有会话
python -X utf8 -m databases.tools.view
# 看某个会话的完整对话
python -X utf8 -m databases.tools.view show 3
```

**线上健康检查与日志**：
```bash
curl https://ctos2.cn/health
# 日志就是运行 python -m common.main 那个终端的输出；要在后台跑可以用 nohup 或计划任务
```

---

## 七、项目目录结构

项目按职责分成八层，依赖方向单向（api → cli → modules → common → databases）。

```
ctOS2.0/
├── api/                        # ③ 接口层：每个模块一个路由文件
│   ├── main.py                 # ★ FastAPI 入口，只做装配（建 app + 挂静态 + include_router）
│   ├── deps.py                 # 路由共用：取租户 / 校验图片 / SSE 响应头
│   └── routes/                 # auth、trial、chat、trip、guide、roleplay、
│                               # customer、sessions、presence、feedback、system
├── cli/                        # ④ 本地层：每个能独立跑完的 agent 一个终端入口
│   ├── chat.py                 # 对话：python -m cli.chat
│   ├── trip.py                 # 出行主 Agent（自己判断走哪条路）：python -m cli.trip
│   ├── route.py                # 路线规划子 Agent：python -m cli.route
│   ├── guide.py                # 旅游攻略子 Agent：python -m cli.guide
│   ├── customer.py             # 智能客服：python -m cli.customer
│   └── prompts.py              # 提示词生成：python -m cli.prompts
├── common/                     # ② 公共层：跨模块共用
│   ├── llm.py                  # 唯一的模型客户端 get_llm()，也负责加载 .env
│   ├── db.py                   # ★ PostgreSQL 连接 + 统一建表入口
│   ├── auth.py                 # bcrypt 密码哈希 + JWT 签发校验
│   ├── sse.py                  # SSE 事件打包 + 同步生成器转线程
│   ├── checkpoints.py          # 出行的暂停现场（路线和攻略共用一个）
│   └── tools/                  # 外部数据工具：search / weather / amap
├── databases/                  # ⑥ 数据库层：公共 / 各模块 / 运维工具
│   ├── common/
│   │   ├── db.py               # 连接 + 通用操作 + 建表总入口
│   │   └── db_tenant.py        # 全局身份表 tenants
│   ├── modules/
│   │   ├── db_auth.py          # 用户表 users
│   │   ├── db_chat.py          # sessions / messages / message_images
│   │   ├── db_trip.py          # 出行 4 张表
│   │   ├── db_roleplay.py      # 角色扮演 3 张表
│   │   └── db_feedback.py      # 反馈 feedback
│   └── tools/                  # 运维 CLI：view / clean / feedback_view
├── modules/                    # ① 模块层：按子集 / 交集组织
│   ├── chat/                   # 闲聊（父）
│   │   └── roleplay/           # ← 子集：角色扮演（复用闲聊的会话表）
│   ├── trip/                   # 智能出行（父）
│   │   ├── agent.py            # 编排：判断该自己答 / 走路线 / 做攻略
│   │   ├── route/              # ← 子集：路线规划
│   │   └── guide/              # ← 子集：旅游攻略
│   ├── customer/               # 智能客服（RAG）：graph / node / state /
│   │                           # prompts / stream / rag_* / embedding / eval
│   └── imagegen/               # ← 交集：生图（在建，尚未接入路由）
├── docs/                       # ⑧ 文档层
│   ├── reading/                # 给人读的技术文档
│   ├── planning/               # 规划稿与排查记录
│   └── corpus/                 # RAG 语料（本文就在这里）
├── config/                     # ⑦ 配置层
│   ├── YOUR_config.env         # 配置模板（入库）
│   ├── .env                    # 真实密钥（已 gitignore，不入库）
│   ├── notice.json             # 更新公告
│   └── requirements.txt
├── web/                        # 前端（Vue 3 + TypeScript）
│   ├── src/                    # 源码：features / shared / App.vue / router.ts
│   │   ├── features/           # 按业务分：chat（含 roleplay）/ trip / customer
│   │   └── shared/             # 共用：api / auth / attachments / components / lib / styles / types
│   ├── dist/                   # 构建产物（npm run build 生成，不进 git）
│   ├── index.html              # 页面骨架
│   └── vite.config.ts          # 构建配置
├── scripts/                    # 构建与运维脚本
└── screenshot/                 # README 用的界面截图
```

### 关于前端

前端是 **Vue 3 + TypeScript + Vite**，**有构建步骤**。改了 `web/src/` 下的代码必须重新构建，
否则浏览器看到的还是旧产物：

```bash
cd web
npm run build
```

构建产物输出到 `web/dist/`，后端 `api/main.py` 把这个目录挂到 `/static` 前缀，
`api/routes/system.py` 的 `/` 返回 `web/dist/index.html`。

前端按业务分目录：`features/chat`、`features/trip`、`features/customer`，
跨模块共用的组件和工具在 `shared/`。开发时可以 `npm run dev` 起热更新服务器（端口 5174），
接口请求会自动转发给后端。

线上走 Cloudflare，`.js` / `.css` 会被缓存 4 小时，所以改完前端还要跑
`node scripts/stamp-static.js` 给资源引用加版本号，否则用户要等 4 小时才看到改动。

线上直接访问 <https://ctos2.cn/> 就是同一份页面。

---

## 八、安全说明

- 所有密钥都从 `config/.env` 读取，**代码里不写死任何凭据**
- `.gitignore` 已排除 `config/.env`、`*.env`、`venv/`、`__pycache__/`、`*.sql`、`*.db`、向量库目录、测评结果等
- 只有配置模板 `config/YOUR_config.env` 会入库，里面有占位符，不含真实值
- **所有业务接口都要登录**：请求头带 `Authorization: Bearer <token>`，未登录返回 401
- 密码存 bcrypt 哈希；登录失败时不区分「邮箱不存在」和「密码错误」，避免被用来枚举账号
- **数据库不暴露到公网**：PostgreSQL 默认只监听本机，不对公网开放端口
- HTTPS 由 Cloudflare 提供，应用本身不处理证书
- 如果不小心把密钥提交进了仓库，**必须立刻去对应平台轮换密钥**。
  删除文件并不能让已泄露的密钥失效，因为提交历史里还留着

---

## 九、数据库表结构

项目使用 PostgreSQL 数据库：`ctos2`，共 13 张表。
所有模块共用同一个数据库、同一套连接函数（`databases/conn.py` 的 `get_conn()` / `query()` / `execute()`）。

建表入口是 `databases/conn.py` 的 `create_all_tables()`，它会先建全局身份表 `tenants`，
再依次调用各模块的建表函数。建表语句都用了 `CREATE TABLE IF NOT EXISTS`，重复执行是安全的。

连接层每个操作开一个短连接，用完自动关、出错自动回滚；`transaction()` 把多条写入包成一个事务。
**不要另写第二份开连接的代码**，所有 SQL 都走 `databases/conn.py` 提供的函数。

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

**预设角色不在这三张表里**，它们写在模块代码 `modules/chat/roleplay/presets.py` 中，不吃数据库。

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
5. 要存数据的话，在 `databases/modules/` 下加一个 `db_xxx.py`（命名参照现有的 `db_chat.py` / `db_trip.py`），表里带上 `tenant_id`，建表语句加进 `databases/schema.sql`
6. 改完前端要 `cd web && npm run build`；前端页面加在 `web/src/features/` 下
7. 上线：把代码同步到服务器，重启 `python -X utf8 -m common.main`

模块之间应该保持独立：各自的图、各自的提示词、各自的配置读取。
共享的只有 FastAPI 应用、端口、会话接口和数据库连接层。

### 改进智能客服的检索质量

混合检索现在已经是「分数归一化 + 权重 + 相关性阈值」，下面这些是已经做完的：

- ~~给向量检索加相关性阈值~~ → **已做**：`MIN_VECTOR_SCORE = 0.36`，低于它不进候选。
  完全无关的问题现在能真正返回 0 条，不再「无论问什么都有 4 条」。
- ~~调整每层条数~~ → **已调**：`TOP_K` 从 3 调到 8（候选更多，混合才有得选）。
- ~~优化切块策略~~ → **已做**：每块带标题路径，代码块不再被切断，
  `MAX_CHUNK_CHARS` 从 600 调到 800。

还能继续做的：

- **重排（Rerank）**：对合并后的候选片段再做一次精排
- **改文档结构**：现在 `ctOS2_manual.md` 是一整本 52KB 的大文件，
  分成几篇主题更集中的文档（部署 / 接口 / 数据库 / FAQ）会让检索更有区分度

这些改动都集中在 `rag_search.py`（检索三层）、`rag_ingest.py`（切块入库）
和 `node.py`（改写与范围判断）里。改完用
`python -X utf8 -m modules.customer.rag_eval` 跑一遍 40 题测评，对比改动前后的命中率。

### 智能客服的多轮是怎么做的

客服支持追问：前端把最近几轮对话放进请求体的 `history` 里。

- `rewrite` 节点先让模型把「那它怎么配」改写成一句自包含的检索查询
  （比如「DeepSeek 密钥怎么配置」），再拿这句去检索。
  早先的做法是把「上一轮问题 + 当前问题」用空格拼起来，噪声大，
  同义改写那类题命中@1 只有 40%，已经换掉了。
- 如果改写结果和原问题一模一样（模型没改），而原文又是一个很空泛的问法
  （「这东西能帮我干什么」），会补一句意图提示再检索一次。
- `generate` 节点把最近 3 轮对话（`HISTORY_TURNS = 3`）拼进提示词，让模型理解「它」指什么。

目前客服问答**不落库**。如果要把问答也存进会话记录，参照闲聊的做法在 `databases/` 下加表，
并把建表函数加进 `databases/conn.py` 的 `create_all_tables()`。
注意：这会改变「客服不留记录」的现有设计意图。
