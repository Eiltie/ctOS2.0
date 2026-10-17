# ctOS 2.0 系统手册

本文是 ctOS 2.0 的完整说明，涵盖使用方式、技术实现、常见问题与部署运维。
读者既可以是第一次接触本系统的普通用户，也可以是准备二次开发的工程师。

---

## 一、ctOS 2.0 是什么

ctOS 2.0 是一个用 FastAPI 加 LangGraph 搭建的多模块 AI 应用。

它的核心设计是：**同一个 FastAPI 应用里挂载多个能力模块，所有模块共用一个端口、一套静态资源、一套会话接口。**
模块之间彼此独立，各自有自己的一张 LangGraph 图，互不干扰。

目前系统包含三个模块，三个都已经接入 Web 页面：

| 模块 | 路由 | 说明 |
| --- | --- | --- |
| 闲聊 / 对话 | `/chat` | 基于 LangGraph 的对话图，流式返回纯文本 |
| 智能出行 | `/trip/chat` | 旅行规划 agent，按「天气 → 景点 → 行程 → 路线」四步产出，SSE 事件流 |
| 智能客服 | `/customer/chat` | 基于 RAG 三层检索的问答模块，SSE 事件流 |

需要特别说明的是：**智能出行和智能客服都不是独立的 app，它们是 ctOS 的一项能力。**
系统采用「一个 app、多个能力」的组织方式，而不是「多个 app 并列」。

三者还有一个重要区别：

- 闲聊和智能出行**会存数据库**，左侧栏能翻到历史记录。
- 智能客服是**一问一答、不记会话、不带历史**，问完即走，不写数据库。所以它的请求体里只有 `query`，没有 `session_id`。

### 技术栈

- **Web 框架**：FastAPI、Uvicorn、Pydantic
- **编排框架**：LangGraph、LangChain、langchain-openai
- **外部工具**：Tavily 联网搜索、高德地图路径规划、Open-Meteo 天气
- **存储**：SQLite（Python 标准库 `sqlite3`）存会话与出行记录；Chroma 用于 RAG 向量库
- **检索**：智谱 embedding-3、jieba + rank-bm25
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
DEEPSEEK_API_KEY=      # DeepSeek 密钥，对话与出题用
DEEPSEEK_BASE_URL=     # DeepSeek 接口地址
DEEPSEEK_MODEL=        # 模型名

TAVILY_API_KEY=        # Tavily 搜索密钥，智能出行查景点用
AMAP_KEY=              # 高德地图密钥，智能出行算路线用
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
python ctOS2_databases/ctOS2_db.py
```

会建好闲聊和出行两边的全部 5 张表。表已存在就跳过，不会动已有数据。

### 第四步：智能客服入库（第一次使用前跑一次）

智能客服依赖本地向量库，需要先把 `data/docs/` 里的文档切块、向量化、入库：

```bash
python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py
```

**改了 `data/docs/` 里的文档后要重新跑一次。**

### 第五步：启动服务

```bash
python src/ctOS_chat_api.py
```

然后在浏览器打开 <http://127.0.0.1:8080/> 就是前端页面。

还没有跑过建表和入库时，闲聊和出行照样能用（写库失败只会打印一行日志），
但智能客服会因为找不到向量库而报错。

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
`TAVILY_API_KEY`、`AMAP_KEY`、`ZHIPU_API_KEY`。

### 3. 初始化数据库

```bash
python ctOS2_databases/ctOS2_db.py
```

### 4. 智能客服入库（第一次用才需要）

```bash
python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py
```

### 5. 启动服务

```bash
python src/ctOS_chat_api.py
```

看到 uvicorn 启动成功后，在浏览器打开 <http://127.0.0.1:8080/> 即可使用。

### 快速启动（已经配置过之后的日常使用）

如果之前已经装好依赖、配好密钥、建好表、入过库，那以后每次只要一条命令：

```bash
python src/ctOS_chat_api.py
```

### 关于端口

端口 8080 写死在 `src/ctOS_chat_api.py` 文件末尾的这一行：

```python
uvicorn.run(app, host="127.0.0.1", port=8080)
```

前端请求后端用的是**相对路径**（`API.base` 为空字符串），也就是同源访问，
所以**换端口只需要改这一处**，前端不用动。

也可以用 uvicorn 命令启动，但端口必须和 8080 保持一致：

```bash
uvicorn src.ctOS_chat_api:app --reload --port 8080
```

### 其它常用命令

| 用途 | 命令 |
| --- | --- |
| 建表 | `python ctOS2_databases/ctOS2_db.py` |
| 客服入库 | `python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py` |
| 查知识库是否就绪 | `python -X utf8 ctOS2_modules/ctOS2_customer_AI/rag_store.py` |
| 看数据库内容 | `python -X utf8 ctOS2_databases/ctOS2_db_view.py` |
| 终端调试出行 | `python ctOS2_modules/ctOS2_Trip_AI/ctOS2_Trip_main.py` |
| 终端调试客服 | `python -X utf8 ctOS2_modules/ctOS2_customer_AI/main.py` |
| 验证客服流式封装 | `python -X utf8 ctOS2_modules/ctOS2_customer_AI/ctOS2_customer_stream.py` |

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

点击「智能出行」入口，用自然语言描述出行需求即可，例如：

```
下周想去杭州玩3天，带老人
```

系统会自动完成四步，并且**每一步的产出都会实时显示在页面上**：

1. **查询天气** —— 识别目的地、天数、出发日期，然后查真实天气并给出总结
2. **推荐景点** —— 结合天气和同行人推荐景点，必要时联网搜索查门票、开放时间
3. **安排行程** —— 把景点分配到每一天，排出逐日行程
4. **规划路线** —— 细化成带具体时刻和交通耗时的路线

后端契约是：`POST /trip/chat`，请求体为 `{"query": "...", "history": [...]}`，响应是 `text/event-stream` 的 SSE 事件流。

出行模块对模糊需求有容错：如果用户表达的信息不足以识别目的地，系统会提示「把话说具体点试试」，
而不是直接报错崩溃。

**出行模块还带一个「闲聊分流」**：进图之前会先判断这句话是不是出行需求。

- 是出行需求 → 把多轮对话合并成一句完整需求，再跑图；
- 是闲聊（打招呼、道谢、问你是谁） → **不跑图**，直接回一句话。

两条路径都会存库，用 `trip_sessions.turn_kind` 区分：`TRAVEL` 表示真跑了图，`CHAT` 表示闲聊分流。

**出行记录**存在另外三张表里，和闲聊的会话表分开。左侧栏在出行模式下会切换成出行记录列表，
点开可以恢复当时的四段卡片，也可以删除。

对应接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/trip/list` | 最近的出行记录（默认最多 50 条） |
| `GET` | `/trip/{id}` | 单条记录的完整内容（含四段产出） |
| `DELETE` | `/trip/{id}` | 删除一条记录，子表级联删除 |
| `GET` | `/trip/ping` | 存活检测 |

### 3.3 智能客服模块

这是基于 RAG（检索增强生成）的问答模块，专门回答关于 ctOS 2.0 项目本身的问题。

**两种运行方式**，两种都可用：

1. **网页**：点击「智能客服」入口直接提问（走 `POST /customer/chat`，SSE 流式返回）
2. **终端**：`python -X utf8 ctOS2_modules/ctOS2_customer_AI/main.py`
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
ctOS2_modules/ctOS2_customer_AI/
├── main.py                    # 终端调试入口（会打印三层检索详情）
├── ctOS2_customer_stream.py   # 流式封装（对外唯一入口，供 Web 层调用）
├── create_graph.py            # 组装图（定义节点和连线）
├── agent_node.py              # 图的节点：检索、生成
├── agent_state.py             # 图的状态定义
├── get_llm.py                 # 读配置、建模型客户端、路径常量
├── promtps.py                 # 提示词（文件名就是拼错的 prompts，别改）
├── rag_ingest.py              # 一次性入库脚本
├── rag_store.py               # 知识库加载与复用（加载一次，全程共用）
├── rag_keyword.py             # 第一层：关键词检索
├── rag_vector.py              # 第二层：向量检索
├── rag_hybrid.py              # 第三层：混合检索
└── data/
    ├── docs/                  # 知识库原始文档（放 .md 文件）
    └── chroma/                # 向量库落盘目录
```

**`ctOS2_customer_stream.py` 是模块对外的唯一出入口**，里面只有一个 `async` 生成器 `customer_stream(query)`，
把图的产出转成 SSE 事件。Web 层（`src/ctOS_chat_api.py` 的 `/customer/chat` 路由）只管调用它，
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

使用的模型是智谱的 `embedding-3`，输出 **2048 维**向量。
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
python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py
```

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
一共需要 5 个：DeepSeek（对话，必需）、智谱（客服向量化，必需）、Tavily（搜景点）、高德（算路线）。
另外克隆下来时数据库和向量库都还不存在，要先跑 `ctOS2_databases/ctOS2_db.py` 建表、
再跑 `rag_ingest.py` 入库，这两个都是一次性的初始化步骤。
只拿到 DeepSeek 密钥的话，闲聊模块能正常用，出行和客服会不可用。

**Q：怎么启动这个项目？**
A：三步。① 装依赖 `pip install -r config/requirements.txt`；
② 建表 `python ctOS2_databases/ctOS2_db.py`；
③ 启动服务 `python src/ctOS_chat_api.py`，然后在浏览器打开 <http://127.0.0.1:8080/>。
如果是第一次用智能客服，中间还要多跑一次入库脚本 `python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py`。

**Q：怎么安装依赖？**
A：在项目根目录执行：

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r config/requirements.txt
```

依赖清单在 `config/requirements.txt` 里，分 Web、出行模块、客服模块三组。

**Q：启动后端口是多少？访问哪个地址？**
A：端口是 8080，地址是 <http://127.0.0.1:8080/>。
端口写死在 `src/ctOS_chat_api.py` 末尾的 `uvicorn.run(..., port=8080)`。

**Q：系统支持哪些大模型？**
A：对话和图上的推理用的是 DeepSeek，通过 `config/.env` 里的 `DEEPSEEK_MODEL` 配置。
向量化用的是智谱的 `embedding-3`。两者是不同厂商的模型，各司其职。

**Q：端口可以改吗？**
A：可以，只改 `src/ctOS_chat_api.py` 末尾的 `uvicorn.run(..., port=8080)` 这一处即可。
前端请求后端用的是相对路径（同源），不写死端口，所以不用改。

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
A：不会。闲聊会话存在 `sessions` / `messages`，出行记录存在 `trip_*` 三张表，
都是本地 SQLite 文件 `ctOS2_databases/ctOS2_db.db`，重启服务和刷新页面都还在。
只有智能客服不留记录。

### 关于开发

**Q：怎么修改知识库内容？**
A：两步。第一，改 `data/docs/` 下的 Markdown 文件（或新增文件）；
第二，重新执行 `python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py`。
只做第一步不生效。改完记得重启服务。

**Q：检索返回几条可以调吗？**
A：可以。每层各自有一个 `TOP_K` 常量控制返回条数（`rag_keyword.py` 和 `rag_vector.py`，当前都是 3）；
混合层还有 `MAX_HITS` 控制最终交给模型的上限（`rag_hybrid.py`，当前是 4）。

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
A：可以。三个模块都已接入页面，点顶栏的「智能客服」即可。

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
python -X utf8 ctOS2_modules/ctOS2_customer_AI/main.py
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
python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py
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

- Python 3.14（开发环境实测版本：3.14.5）
- 无需额外安装数据库（SQLite 是 Python 标准库自带的）
- 能访问外网：需要调用 DeepSeek、智谱、Tavily、高德、Open-Meteo 的接口

### 6.2 依赖清单

依赖统一写在 `config/requirements.txt`，分三组：

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
langchain-tavily==0.2.18
openai==2.53.0
httpx
# 智能客服模块（RAG 三层检索）用的
chromadb==1.5.9
jieba==0.42.1
rank-bm25==0.2.2
```

其中 `chromadb`、`jieba`、`rank-bm25` 三个是智能客服模块专用的。

`langgraph-checkpoint-sqlite` 虽然列在「出行模块用的」这组里，但**当前代码并没有真的用到它**：
项目里没有任何地方 import 它，也没有配置任何 checkpointer。
真正承担持久化的是 `ctOS2_databases/` 那套自己写的 `sqlite3` 代码。
这个包留着不影响运行，只是占一个位置。

### 6.3 启动顺序

1. 确认 `config/.env` 已填好所有密钥（含 `ZHIPU_API_KEY`）
2. 建表：`python ctOS2_databases/ctOS2_db.py`
3. 智能客服要用的话，先跑一次入库脚本
4. 启动 Web 服务：`python src/ctOS_chat_api.py`

### 6.4 数据存放位置

| 数据 | 位置 | 说明 |
| --- | --- | --- |
| 闲聊会话 | `ctOS2_databases/ctOS2_db.db` → `sessions` / `messages` | 会话与消息 |
| 出行记录 | 同一个 `.db` → `trip_sessions` / `trip_user_inputs` / `trip_ai_outputs` | 一轮出行 = 主表一行 + 子表各一行 |
| 向量库 | `ctOS2_modules/ctOS2_customer_AI/data/chroma/` | Chroma 落盘的向量数据 |
| 知识库原文 | `ctOS2_modules/ctOS2_customer_AI/data/docs/` | Markdown 文档 |

向量库文件和 `.db` 文件都已被 `.gitignore` 排除，不会进代码仓库。

### 6.5 备份与恢复

- **数据库**：直接复制 `ctOS2_databases/ctOS2_db.db` 一个文件即可，会话和出行记录都在里面。
  程序运行时开了 WAL 模式，热备时注意把同目录下的 `-wal` / `-shm` 文件一并复制
- **向量库**：可以直接复制整个 `data/chroma/` 目录；
  但因为向量库可以随时由入库脚本重建，更稳妥的做法是**备份 `data/docs/` 里的原始文档**，
  需要时重新跑一次入库脚本

### 6.6 常见运维操作

**更新知识库**：
```bash
# 1. 修改 data/docs/ 下的文档
# 2. 重新入库
python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py
# 3. 重启服务，否则内存里还是旧知识库
```

**单独调试出行模块**（不启动 Web 服务）：
```bash
python ctOS2_modules/ctOS2_Trip_AI/ctOS2_Trip_main.py
```

**单独调试智能客服模块**：
```bash
python -X utf8 ctOS2_modules/ctOS2_customer_AI/main.py
```

**查看/导出聊天记录**：
```bash
# 列出所有会话
python -X utf8 ctOS2_databases/ctOS2_db_view.py
# 看某个会话的完整对话
python -X utf8 ctOS2_databases/ctOS2_db_view.py show 3
# 导出某个会话为 txt（写到 ctOS2_databases/ 下）
python -X utf8 ctOS2_databases/ctOS2_db_view.py export 3
```
注意这个工具只查闲聊的两张表，看不到出行记录。

---

## 七、项目目录结构

```
ctOS2.0/
├── src/                        # 后端主服务
│   ├── ctOS_chat_api.py        # ★ FastAPI 入口（app 在这里）
│   ├── ctOS_chat_graph.py      # 对话图
│   ├── ctOS_chat_graphOn.py    # 对话图对外入口 run_graph
│   ├── ctOS_chat_agent_node.py # 图节点
│   ├── ctOS_chat_llm.py        # LLM 初始化
│   ├── ctOS_chat_promtps.py    # 提示词
│   ├── ctOS_chat_sessions.py   # 会话读写（错误兜底 + 格式转换）
│   └── ctOS_chat_state.py      # 图状态定义
├── ctOS2_modules/
│   ├── ctOS2_Trip_AI/          # 智能出行模块
│   └── ctOS2_customer_AI/      # 智能客服模块（RAG）
├── ctOS2_databases/            # SQLite 数据库层
│   ├── ctOS2_db.py             # ★ 连接层 + 统一建表入口
│   ├── ctOS2_db_chat.py        # 闲聊表：sessions / messages
│   ├── ctOS2_db_trip.py        # 出行表：trip_sessions / trip_user_inputs / trip_ai_outputs
│   ├── ctOS2_db_view.py        # 命令行查看工具
│   └── ctOS2_db.db             # 数据库文件（自动生成，不入库）
├── static/                     # 前端（无构建步骤）
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── app.js              # 核心：状态、侧边栏、闲聊、模块切换
│       ├── trip.js             # 智能出行
│       └── customer.js         # 智能客服
├── screenshots/                # README 用的界面截图
└── config/
    ├── YOUR_config.env         # 配置模板（入库）
    ├── .env                    # 真实密钥（已 gitignore，不入库）
    └── requirements.txt
```

### 关于前端

前端**没有任何构建步骤**。改 `static/css/style.css` 或 `static/js/*.js`，
保存后刷新浏览器就能生效，不需要执行任何编译或打包命令。

三个 JS 文件按 `app.js → trip.js → customer.js` 的顺序加载，
后两个依赖 `app.js` 里的 `$`、`esc`、`md`、`API`、`state` 等全局变量，**调整加载顺序会导致报错**。
详见 `static/README.md`。

后端为了提供静态资源，在 `src/ctOS_chat_api.py` 里挂载了静态目录：

```python
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
```

挂载在 `/static` 前缀下，不会和已有的 `/chat`、`/sessions`、`/trip/...`、`/customer/...` 等路由冲突。

---

## 八、安全说明

- 所有密钥都从 `config/.env` 读取，**代码里不写死任何凭据**
- `.gitignore` 已排除 `config/.env`、`*.env`、`venv/`、`__pycache__/`、`*.sql`、`*.sqlite`、`*.sqlite3`、`*.db` 等
- 只有配置模板 `config/YOUR_config.env` 会入库，里面有占位符，不含真实值
- SQLite 数据库文件本身没有访问权限控制，谁拿到谁能读，不要外传
- 如果不小心把密钥提交进了仓库，**必须立刻去对应平台轮换密钥**。
  删除文件并不能让已泄露的密钥失效，因为提交历史里还留着

---

## 九、数据库表结构

项目使用一个本地 SQLite 文件：`ctOS2_databases/ctOS2_db.db`。
所有模块共用同一个文件、同一套连接函数（`ctOS2_db.open_database()`）。

建表入口是 `ctOS2_db.create_all_tables()`，它会依次调用各模块的建表函数。
建表语句都用了 `CREATE TABLE IF NOT EXISTS`，重复执行是安全的。

`open_database()` 每次开连接都会做三件事：打开外键检查 `PRAGMA foreign_keys = ON`、
开启 WAL 模式、设置 `row_factory` 让查询结果能按列名取值。
**不要另写第二份开连接的代码**，否则某个模块漏了开外键，就会悄悄出 bug。

### 9.1 闲聊：`sessions` / `messages`

| 表 | 字段 | 说明 |
| --- | --- | --- |
| `sessions` | `id` | 主键，自增 |
| | `title` | 会话标题（用户第一句话的前 14 个字） |
| | `created_at` / `updated_at` | 本地时间，`updated_at` 在每次追加消息时刷新，列表按它倒序 |
| `messages` | `id` | 主键，自增 |
| | `session_id` | 外键 → `sessions.id`，`ON DELETE CASCADE` |
| | `role` | 只能是 `user` 或 `assistant` |
| | `content` | 消息正文 |
| | `created_at` | 本地时间 |

`messages.session_id` 上有索引 `ix_messages_session_id`。

### 9.2 出行：`trip_sessions` / `trip_user_inputs` / `trip_ai_outputs`

| 表 | 字段 | 说明 |
| --- | --- | --- |
| `trip_sessions` | `id` | 主键，自增 |
| | `title` | 标题，优先用目的地，没有就取用户第一句话的前 14 个字 |
| | `turn_kind` | `TRAVEL`（真跑了图）或 `CHAT`（闲聊分流） |
| | `destination` / `days` / `start_date` | 从需求里解析出来的出行要素 |
| | `created_at` | 本地时间 |
| `trip_user_inputs` | `id` / `trip_id` / `content` / `created_at` | `trip_id` 外键 → `trip_sessions.id`，级联删除 |
| `trip_ai_outputs` | `id` / `trip_id` | `trip_id` 外键 → `trip_sessions.id`，级联删除 |
| | `weather` / `spots` / `itinerary` / `route_plan` | 四段产出 |
| | `chat_reply` | 闲聊分流的回复 / 创建时间 |

两个子表的 `trip_id` 上都有索引。

存一轮出行记录 = 主表插一行 + 两个子表各插一行，在同一个事务里完成，
要么全成、要么全不成，不会出现「有主表没子表」的半截数据。

### 9.3 智能客服

客服模块**不写数据库**，一问一答不留记录。它的「知识」只落在本地 Chroma 目录里。

---

## 十、扩展与二次开发

### 增加一个新的能力模块

系统的设计是「一个 app 挂多个能力」，新增模块的步骤大致是：

1. 在 `ctOS2_modules/` 下建一个模块目录
2. 在图里定义状态、节点，然后组装成一张图
3. 在模块内写一个流式封装文件，对外只暴露一个生成器（参照 `ctOS2_Trip_stream.py` / `ctOS2_customer_stream.py`）
4. 在 `src/ctOS_chat_api.py` 里加一个路由，把生成器塞进 `StreamingResponse`
5. 在前端加一个面板和请求逻辑（参照 `static/js/trip.js` / `customer.js`）
6. 要存数据的话，在 `ctOS2_databases/` 下加一个 `ctOS2_db_xxx.py`（命名参照现有的 `ctOS2_db_chat.py` / `ctOS2_db_trip.py`），并把它的建表函数加进 `ctOS2_db.create_all_tables()`

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

这些改动都集中在 `rag_vector.py`、`rag_hybrid.py` 和 `rag_ingest.py` 里，不影响图的其它部分。

### 让智能客服记住上下文

目前客服是「一问一答、不带历史」。如果要改成多轮：

1. 在 `agent_state.py` 里加一个 `history` 字段
2. 在 `ctOS2_customer_stream.py` 里接收历史并写进初始状态
3. 在 `agent_node.py` 的提示词里拼上历史
4. 在 `src/ctOS_chat_api.py` 的 `CustomerRequest` 里加上 `history` 字段，前端跟着传

如果还要把客服问答存进会话记录，就再参照闲聊的做法加表。注意：这会改变「客服不留记录」的现有设计意图。
