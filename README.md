# ctOS 2.0

一个 FastAPI + LangGraph 搭建的多模块 超级AI 应用。同一个 FastAPI app 挂载多个能力模块，共用一套静态资源与会话接口。

## 模块

| 模块 | 路由 | 说明 |
| --- | --- | --- |
| 闲聊 / 对话 | `/chat` | 基于 LangGraph 的对话图，流式返回纯文本 |
| 智能出行 | `/trip/chat` | 旅行规划 agent（天气 → 景点推荐 → 行程 → 路线），SSE 事件流 |
| 智能客服 | `/customer/chat` | RAG 三层检索问答（关键词 → 向量 → 混合），SSE 事件流 |

三个模块不是独立的 app，它们是 ctOS 的能力。

闲聊和出行会把我说的内容存进数据库，左侧栏能翻到历史记录；智能客服是一问一答、不记会话、不写数据库。

## 界面预览

**闲聊模式**（`/chat`）——流式纯文本对话：

![闲聊模式](screenshots/chat.png)

**智能出行**（`/trip/chat`）——查询天气 → 推荐景点 → 安排行程 → 规划路线：

![智能出行](screenshots/trip.png)

## 目录结构

```
ctOS2.0/
├── src/                        # 后端主服务
│   ├── ctOS_chat_api.py        # ★ FastAPI 入口（app 在这里）
│   ├── ctOS_chat_graph.py      # 对话图
│   ├── ctOS_chat_graphOn.py    # 对话图对外入口 run_graph
│   ├── ctOS_chat_agent_node.py # 图节点
│   ├── ctOS_chat_llm.py        # LLM 初始化
│   ├── ctOS_chat_promtps.py    # 提示词
│   ├── ctOS_chat_sessions.py   # 会话读写
│   └── ctOS_chat_state.py      # 图状态定义
├── ctOS2_modules/
│   ├── ctOS2_Trip_AI/          # 智能出行模块
│   │   ├── ctOS2_Trip_main.py      # 终端调试入口
│   │   ├── ctOS2_Trip_stream.py    # 流式细节（读取 config/.env）
│   │   ├── ctOS2_Trip_create_graph.py
│   │   ├── ctOS2_Trip_agent_node.py
│   │   ├── ctOS2_Trip_agent_tools.py
│   │   ├── ctOS2_Trip_route.py
│   │   ├── ctOS2_Trip_prompts.py
│   │   ├── ctOS2_Trip_llm.py
│   │   └── ctOS2_Trip_state.py
│   └── ctOS2_customer_AI/      # 智能客服模块（RAG）
│       ├── main.py                 # 终端调试入口
│       ├── ctOS2_customer_stream.py # 流式封装（对外唯一入口）
│       ├── create_graph.py         # 组装图
│       ├── agent_node.py           # 图节点（检索、生成）
│       ├── agent_state.py          # 图状态定义
│       ├── get_llm.py              # 读配置、模型客户端、路径常量
│       ├── promtps.py              # 提示词
│       ├── rag_store.py            # 知识库加载与复用
│       ├── rag_ingest.py           # 一次性入库脚本
│       ├── rag_keyword.py          # 第一层：关键词检索
│       ├── rag_vector.py           # 第二层：向量检索
│       ├── rag_hybrid.py           # 第三层：混合检索
│       └── data/
│           ├── docs/               # 知识库原始文档
│           └── chroma/             # 向量库落盘目录（由入库脚本生成）
├── ctOS2_databases/            # SQLite 数据库层
│   ├── ctOS2_db.py             # ★ 连接层 + 统一建表入口
│   ├── ctOS2_db_chat.py        # 闲聊表：sessions / messages
│   ├── ctOS2_db_trip.py        # 出行表：trip_chats / trip_sessions / trip_user_inputs / trip_ai_outputs
│   ├── ctOS2_db_view.py        # 命令行查看工具
│   └── ctOS2_db.db             # 数据库文件（自动生成，不入库）
├── static/                     # 前端（无构建步骤）
│   ├── index.html
│   ├── README.md               # 前端文件说明
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

## 数据存储

所有业务数据存在同一个 SQLite 文件 `ctOS2_databases/ctOS2_db.db` 里，共 6 张表：

| 表 | 所属模块 | 说明 |
| --- | --- | --- |
| `sessions` | 闲聊 | 一次会话，主键 `id` |
| `messages` | 闲聊 | 会话里的消息，外键 `session_id` → `sessions.id` |
| `trip_chats` | 出行 | 一次出行会话（左侧列表一行），主键 `id` |
| `trip_sessions` | 出行 | 会话里的一轮对话，外键 `chat_id` → `trip_chats.id` |
| `trip_user_inputs` | 出行 | 用户输入，外键 `trip_id` → `trip_sessions.id` |
| `trip_ai_outputs` | 出行 | AI 四段产出，外键 `trip_id` → `trip_sessions.id` |

两个外键都设了 `ON DELETE CASCADE`：删掉主记录，子记录自动跟着删。
智能客服是一问一答，**不写数据库**，所以没有自己的表。

查看数据库内容（不用装任何工具）：

```bash
python ctOS2_databases/ctOS2_db_view.py            # 列出所有会话
python ctOS2_databases/ctOS2_db_view.py show 3     # 看某个会话的完整对话
python ctOS2_databases/ctOS2_db_view.py search 杭州 # 搜内容
python ctOS2_databases/ctOS2_db_view.py export 3   # 导出某个会话为 txt
python ctOS2_databases/ctOS2_db_view.py stats      # 统计
```

> `ctOS2_db_view.py` 只查闲聊的两张表（`sessions` / `messages`），看不到出行记录。

## 快速开始

> ### ⚠️ 先读这段：这个项目需要你自己的 API 密钥
>
> **clone 下来不能直接跑。** 项目本身不含任何密钥，所有功能都要调用外部 API，
> 你必须自己申请 5 个密钥并填进 `config/.env`，否则启动后各个模块会报错或不可用。
>
> | 密钥 | 用途 | 必要性 | 去哪申请 |
> | --- | --- | --- | --- |
> | `DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL` + `DEEPSEEK_MODEL` | 所有对话和推理 | **必需**，缺了闲聊和出行都不能用 | [platform.deepseek.com](https://platform.deepseek.com/) |
> | `ZHIPU_API_KEY` | 智能客服的向量化 | **必需**，缺了客服模块启动就报错 | [open.bigmodel.cn](https://open.bigmodel.cn/) |
> | `TAVILY_API_KEY` | 出行模块联网搜景点 | 出行要用；不填则景点推荐质量变差 | [tavily.com](https://tavily.com/) |
> | `AMAP_KEY` | 出行模块算路线 | 出行要用；不填则路线会退化为估算 | [lbs.amap.com](https://lbs.amap.com/) |
>
> 这些 API **大多需要注册账号，部分需要付费或有免费额度限制**，具体以各家官网当前政策为准。
> DeepSeek 和智谱按调用量计费，跑一次出行规划会调用十几次模型，请留意自己的余额。
>
> **只拿到 DeepSeek 密钥时**：闲聊模块可以正常用，另外两个模块会不可用。
> 想完整体验三个模块，5 个密钥都要配。

### 1. 安装依赖

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r config/requirements.txt
```

### 2. 配置环境变量

复制模板并填入自己的值：

```bash
cp config/YOUR_config.env config/.env
```

`config/.env` 需要填写：

```
DEEPSEEK_API_KEY=      # DeepSeek 密钥，对话和图上推理都用它
DEEPSEEK_BASE_URL=     # DeepSeek 接口地址，例如 https://api.deepseek.com
DEEPSEEK_MODEL=        # 模型名，例如 deepseek-chat

TAVILY_API_KEY=        # Tavily 搜索密钥，智能出行查景点用
AMAP_KEY=              # 高德地图密钥，智能出行算路线用

ZHIPU_API_KEY=         # 智谱密钥，智能客服 RAG 向量化用（必填，缺失时客服模块启动即报错）
```

每一步都能看到效果，可以按需分阶段配置：

| 你想先试哪个模块 | 最少需要配哪些 |
| --- | --- |
| 只看闲聊 | `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` |
| 加智能出行 | 再补 `TAVILY_API_KEY`、`AMAP_KEY` |
| 加智能客服 | 再补 `ZHIPU_API_KEY` |

> `config/.env` 已被 `.gitignore` 忽略，**不要**提交真实密钥。

### 3. 初始化数据库

```bash
python ctOS2_databases/ctOS2_db.py
```

会建好全部 5 张表（已存在则跳过，不会动已有数据）。

### 4. 智能客服入库（第一次使用前跑一次）

智能客服依赖本地向量库，需要先把 `data/docs/` 里的文档切块、向量化、入库：

```bash
python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py
```

**改了 `data/docs/` 里的文档后要重新跑一次**，否则检索到的还是旧内容。

注意两点：

- 入库用的是智谱接口，`ZHIPU_API_KEY` 必须先配好。
- 入库脚本只处理 `data/docs/` 下的 `*.md` 文件，按 Markdown 的 `## ` 二级标题切块。

### 5. 启动服务

```bash
python src/ctOS_chat_api.py
```

打开 <http://127.0.0.1:8080/> 即为前端页面。

> 端口 8080 写死在 `src/ctOS_chat_api.py` 末尾的 `uvicorn.run(app, host="127.0.0.1", port=8080)`，
> 前端用相对路径请求后端（同源），所以换端口只改这一处即可。
>
> 也可以用 uvicorn 命令启动，但**端口必须和 8080 保持一致**：
>
> ```bash
> uvicorn src.ctOS_chat_api:app --reload --port 8080
> ```

## 跑不起来？先看这里

大部分「跑不起来」都是密钥或初始化没做全。按下面顺序自查：

| 现象 | 原因 | 怎么办 |
| --- | --- | --- |
| 启动就说「没找到向量数据库」/「没有这个集合」 | 还没跑入库脚本 | `python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py` |
| 报错 `config/.env 里没有 ZHIPU_API_KEY` | 智谱密钥没配 | 去 [open.bigmodel.cn](https://open.bigmodel.cn/) 申请后填进 `config/.env` |
| 闲聊一提问就报 401 / 认证失败 | DeepSeek 密钥错或没余额 | 检查 `DEEPSEEK_API_KEY`，并确认账户有余额 |
| 智能出行一上来就报错 | 没配 `TAVILY_API_KEY` 或 `AMAP_KEY` | 补上对应密钥，或先只用闲聊模块 |
| 出行模块提示「没能识别出目的地」 | 不是报错，是需求太模糊 | 说具体点，例如「下周想去杭州玩3天」 |
| 改了 `data/docs/` 但客服回答还是旧的 | 没重新入库，或没重启服务 | 重跑入库脚本 **并且重启** 服务 |
| 页面打开是白屏 | 后端没启动，或端口不是 8080 | 先确认 `python src/ctOS_chat_api.py` 在跑，访问 <http://127.0.0.1:8080/> |

**说明**：项目不含数据库文件和向量库，这两样都是**第一次运行时自动生成**的，
所以刚 clone 下来时必须先执行「第 3 步 初始化数据库」和「第 4 步 入库」，否则一定跑不起来。

## 前端开发

前端**没有任何构建步骤**：改代码保存后刷新浏览器即可生效。

| 文件 | 负责 |
| --- | --- |
| `static/js/app.js` | 核心状态、侧边栏、闲聊、模块切换 |
| `static/js/trip.js` | 智能出行（四段卡片、出行历史） |
| `static/js/customer.js` | 智能客服（问答渲染） |
| `static/css/style.css` | 全部样式 |

三个 JS 文件按 `app.js → trip.js → customer.js` 的顺序加载，后两个依赖 `app.js` 里的 `$`、`esc`、`md`、`API`、`state` 等全局变量，**调整加载顺序会导致报错**。

详见 [`static/README.md`](static/README.md)。

## 单独调试各模块

出行模块可以脱离 Web 服务在终端直接跑：

```bash
python ctOS2_modules/ctOS2_Trip_AI/ctOS2_Trip_main.py
```

客服模块同样可以，每轮会打印三层检索各命中了什么，方便调检索效果：

```bash
python -X utf8 ctOS2_modules/ctOS2_customer_AI/main.py
```

> Windows 控制台默认 GBK，不加 `-X utf8` 中文可能乱码。

单独检查知识库是否就绪（不启动对话）：

```bash
python -X utf8 ctOS2_modules/ctOS2_customer_AI/rag_store.py
```

单独跑一遍客服的流式封装（用一条固定问题验证 SSE 事件能正常吐出）：

```bash
python -X utf8 ctOS2_modules/ctOS2_customer_AI/ctOS2_customer_stream.py
```

## 技术栈

- **Web**：FastAPI、Uvicorn、Pydantic
- **编排**：LangGraph、LangChain、langchain-openai
- **工具**：Tavily 搜索、高德地图、Open-Meteo 天气
- **存储**：SQLite（Python 标准库 `sqlite3`）存会话与出行记录；Chroma 存 RAG 向量
- **检索**：智谱 embedding-3、jieba + rank-bm25
- **配置**：python-dotenv

## 安全说明

- 所有密钥均从 `config/.env` 读取，代码中不写死任何凭据。
- 数据库为本地 SQLite 文件，不含账号密码；⚠️ `.db` 文件本身没有访问权限控制，谁拿到谁能读，不要外传。
- `.gitignore` 已排除 `config/.env`、`*.env`、`venv/`、`__pycache__/`、`*.sql`、`*.sqlite`、`*.db` 等。
- 若曾误提交密钥，请立即在对应平台轮换（删除文件并不能让密钥失效）。

## 许可证

[MIT License](LICENSE) — 可以自由使用、修改、商用，只需保留版权声明，作者不承担担保责任。
