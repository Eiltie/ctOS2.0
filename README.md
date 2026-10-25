# ctOS 2.0

一个 FastAPI + LangGraph 搭建的多模块 AI 应用：同一个服务里挂载「闲聊对话」「智能出行规划」「RAG 智能客服」三种能力，共用一个端口、一套前端页面和一套 SQLite 数据库。

---

## 界面预览

**智能出行** — 开场页居中输入，像聊天助手那样从一句话开始：

![智能出行 开场页](screenshot/ctOS_trip01.png)

**智能出行** — 规划过程有分步进度，输出是一份连贯的行程文档：

![智能出行 规划结果](screenshot/ctOS_trip02.png)

**闲聊** — 支持多轮记忆、会话切换：

![闲聊对话](screenshot/ctOS_chat.png)

**智能客服** — 基于本地文档的 RAG 问答：

<p>
  <img src="screenshot/ctOS_customer01.png" width="49%" alt="智能客服 开场页">
  <img src="screenshot/ctOS_customer02.png" width="49%" alt="智能客服 回答">
</p>

---

## 它解决什么问题

把几种性质完全不同的 AI 能力放到同一条产品外壳下：

- **闲聊**证明长对话能跑通（有会话记忆、能翻历史）
- **智能出行**证明 Agent 能真正调工具干活（查天气、搜景点、算路线），不是只会说话
- **智能客服**证明 RAG 能让模型只照着资料回答，而不是凭空编造

三者共用的部分——FastAPI 应用、会话存储、流式输出、前端静态资源——是这个项目的骨架；各模块只负责自己的图和提示词。

## 快速开始

### 1. 装依赖

```bash
python -m venv venv
venv\Scripts\activate
pip install -r config/requirements.txt
```

### 2. 填密钥

```bash
cp config/YOUR_config.env config/.env
```

然后编辑 `config/.env`，至少填下面三个（只跑闲聊的话，这三个就够了）：

```
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### 3. 初始化并启动

```bash
python ctOS2_databases/ctOS2_db.py
python src/ctOS_chat_api.py
```

浏览器打开 <http://127.0.0.1:8080/>。

> 想用智能客服，还要额外配 `ZHIPU_API_KEY` 并跑一次入库脚本（见下方「常见用法示例」）。

## 架构

### 三个模块，一个 app

| 模块 | 路由 | 输出方式 |
| --- | --- | --- |
| 闲聊 | `POST /chat` | 纯文本流 |
| 智能出行 | `POST /trip/chat` | SSE 事件流 |
| 智能客服 | `POST /customer/chat` | SSE 事件流 |

入口统一在 `src/ctOS_chat_api.py`。每个模块对外只暴露一个流式函数，Web 层不关心图内部长什么样：

- 闲聊：`ctOS2_modules` 之外的 `src/ctOS_chat_graphOn.py` → `run_graph()`
- 出行：`ctOS2_modules/ctOS2_Trip_AI/ctOS2_Trip_stream.py` → `trip_stream()`
- 客服：`ctOS2_modules/ctOS2_customer_AI/ctOS2_customer_stream.py` → `customer_stream()`

### 三张 LangGraph 图

**闲聊**（单直线）：

```
START → chat_node → END
```

**客服**（单直线）：

```
START → retrieve → generate → END
```

**出行**（带条件分支和搜索循环）：

```
START → weather → spots_agent ─┬─→ tools ─┐   （还想搜就回 spots_agent）
                               │  ↑──────┘
                               └─→ planner → route_agent → END
```

### 出行模块的完整链路

在 `POST /trip/chat` 中：

1. **分流**：用模型判断这句话是出行需求还是闲聊，出行需求会先把多轮对话合并成一句完整需求
2. **跑图**：图内部依次产出天气 / 景点 / 行程 / 路线四段
3. **流式回传**：逐字推送 + 每段完成时推整段
4. **存库**：图跑完才存，出错的那一轮不存

### RAG 三层检索

客服模块每一轮问题依次经过：

| 层 | 实现 | 用途 |
| --- | --- | --- |
| 第一层 | jieba 分词 + BM25 | 对专有名词（如 `MAX_HITS`、`rag_ingest`）最准 |
| 第二层 | Chroma 向量库 + 智谱 embedding | 换个说法也能命中 |
| 第三层 | 按名次加权合并 | 两层都命中的片段分数相加，最终交给模型最多 4 条 |

三层都跑是为了方便调试，但**真正交给模型写答案的只有第三层**。

## 配置说明

所有配置从 `config/.env` 读取，代码里不写死密钥。

| 变量 | 用途 | 是否必需 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 所有对话和推理 | **必需** |
| `DEEPSEEK_BASE_URL` | 接口地址 | **必需** |
| `DEEPSEEK_MODEL` | 模型名 | **必需** |
| `ZHIPU_API_KEY` | 客服的向量化 | 用客服就必需；缺了客服模块启动即报错 |
| `TAVILY_API_KEY` | 出行模块联网搜景点 | 用出行建议配，缺失时景点推荐质量变差 |
| `AMAP_KEY` | 出行的路线计算 | 用出行建议配，缺失时路线退化为文字提示 |

### 写死在代码里的参数

| 位置 | 值 | 含义 |
| --- | --- | --- |
| `src/ctOS_chat_api.py` | `port=8080` | 服务端口，改这里即可换端口 |
| `src/ctOS_chat_llm.py` | `TEMPERATURE = 0.7` | 闲聊的随机性 |
| `ctOS2_modules/ctOS2_Trip_AI/ctOS2_Trip_llm.py` | `TEMPERATURE = 0.3` | 出行的随机性 |
| `customer_AI/get_llm.py` | `TEMPERATURE = 0.3` | 客服的随机性 |
| `customer_AI/get_llm.py` | `EMBEDDING_MODEL = "embedding-3"` | 智谱向量模型 |
| `rag_ingest.py` | `MAX_CHUNK_CHARS = 600` | 单块字符上限 |
| `rag_ingest.py` | `MAX_EMBED_BATCH = 64` | 智谱接口单次上限，超了返回 400，所以必须分批 |
| `rag_hybrid.py` | `MAX_HITS = 4` | 最终交给模型的片段数 |
| `ctOS2_modules/ctOS2_Trip_AI/ctOS2_Trip_agent_node.py` | `MAX_SEARCH = 3` / `MAX_ROUTE_ROUNDS = 8` | 景点最多搜几次 / 路线最多问几轮 |
| `ctOS2_modules/ctOS2_Trip_AI/ctOS2_Trip_route.py` | `MAX_MESSAGES = 20` | 防工具反复失败时循环失控 |

## 常见用法示例

### 启动服务

```bash
python src/ctOS_chat_api.py
```

### 用 curl 调三个模块

```bash
# 闲聊（纯文本流）
curl -N -X POST http://127.0.0.1:8080/chat \
  -H "Content-Type: application/json" \
  -d "{\"messages\": \"你好\"}"

# 智能出行（SSE 事件流）
curl -N -X POST http://127.0.0.1:8080/trip/chat \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"下周想去杭州玩3天\", \"history\": []}"

# 智能客服（SSE 事件流）
curl -N -X POST http://127.0.0.1:8080/customer/chat \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"端口怎么改？\"}"
```

### 智能客服：先入库再用

```bash
python -X utf8 ctOS2_modules/ctOS2_customer_AI/rag_ingest.py
```

文档放 `ctOS2_modules/ctOS2_customer_AI/data/docs/*.md`，按 `## ` 二级标题切块。**改了文档要重跑这个脚本，并重启服务。**

### 单独在终端调试模块（不走 Web）

```bash
python -X utf8 ctOS2_modules/ctOS2_Trip_AI/ctOS2_Trip_main.py
python -X utf8 ctOS2_modules/ctOS2_customer_AI/main.py
```

Windows 控制台默认 GBK，不加 `-X utf8` 中文会乱码。

### 查看数据库内容

```bash
python -X utf8 ctOS2_databases/ctOS2_db_view.py            # 列出会话
python -X utf8 ctOS2_databases/ctOS2_db_view.py show 3     # 看某个会话
python -X utf8 ctOS2_databases/ctOS2_db_view.py stats      # 统计
```

### 跑检索测评

```bash
python -X utf8 ctOS2_modules/ctOS2_customer_AI/rag_eval.py
python -X utf8 ctOS2_modules/ctOS2_customer_AI/rag_eval.py --fails     # 只看未命中
python -X utf8 ctOS2_modules/ctOS2_customer_AI/rag_eval.py --save      # 结果存到 eval/runs/
```

题库是 `ctOS2_modules/ctOS2_customer_AI/eval/golden.json`，共 40 题，分「原词 / 同义改写 / 跨章节 / 库外」四类。

### 直接调模块函数

```python
import sys
sys.path.insert(0, r"D:\ctOS2.0")

from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_main import understand_query

kind, merged_query = understand_query(["下周想去杭州玩3天"], "那换成5天呢")
print(kind, merged_query)
```

## 已知限制 / 注意事项

**数据与存储**

- SQLite 是本地单文件，`.db` 本身没有访问控制，拿到文件就能读，**不要外传**
- `ctOS2_databases/ctOS2_db_view.py` 只查闲聊的两张表，看不到出行记录
- 智能客服不写数据库，没有会话历史；刷新页面即清空
- 数据库文件和 Chroma 向量库都是**运行时生成**的，新环境必须依次执行建表和入库脚本

**外部依赖**

- 三个模块全部依赖外部 API，DeepSeek 密钥缺失时闲聊和出行都用不了
- 出行一次规划会调用十几次模型，请注意额度
- 高德/天气接口失败时，Agent 被要求「按常识估算并标注（估算）」，此时路线不是真实数据
- 天气预报最多可查未来 16 天（起始日起），超出会直接返回提示

**功能边界**

- 闲聊没有检索能力，问项目相关问题它可能直接编
- 客服查不到资料时只会回「抱歉，我在知识库里没有找到相关答案」，不会自己找答案
- 出行模块只做了驾车/步行两种方式，没有公交、地铁

**工程质量**

- **项目没有任何自动化测试**。`rag_eval.py` 只是手工跑的检索测评分，不属于测试套件
- 检索测评依赖真实 embedding 接口，离线跑不了
- 出行图的条件分支用元组作返回值，导出的 mermaid 图里画不出这三条条件边

**前端**

- 没有构建步骤，改完刷新即可，但三个 JS 必须按 `app.js → trip.js → customer.js` 顺序加载，后两个依赖前一个定义的全局变量

## 如何贡献 / 如何跑测试

项目目前没有测试套件，也没有 `pytest` 依赖。如果要开始补：

**可以放心测的**（纯函数，不碰外部接口）：`_keep()` 的四道过滤、`understand_query()` 的格式解析（把模型换成假的）、`split_markdown()` 的切块边界、`rank_score()` 与 `judge()`。

**不要写自动化测试的**：`/trip/chat` 完整链路、任何需要真实模型的路径、前端渲染。

**改动的验证方式**：

- 改检索相关：跑 `rag_eval.py`，看四类命中率有没有变
- 改出行图：在终端跑 `ctOS2_modules/ctOS2_Trip_AI/ctOS2_Trip_main.py`，看四段产出是否齐全
- 改接口：启动服务后打开 <http://127.0.0.1:8080/>，三个 tab 各发一句话

**提交前检查**：`config/.env` 和 `*.db` 已被 `.gitignore` 排除，不要提交真实密钥或本地数据库。
