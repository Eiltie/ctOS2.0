# 前端文件说明

前端没有构建步骤。`index.html` 只放页面结构，CSS 和 JS 都在独立文件里，
**改前端直接改 `css/` 和 `js/` 即可，改完刷新浏览器就生效，不需要任何编译或打包**。

> **线上地址：<https://ctos2.cn>**。前端静态文件和后端在同一个进程里，
> 由 `api/main.py` 用 `StaticFiles` 挂载在 `/static`，所以线上和本地看到的是同一份前端。
>
> **注意**：当前 Docker 已经把宿主机的 `static/` 挂进容器，改完刷新页面就生效；
> 如果把镜像部署到没有挂载的机器，仍需重新构建镜像。

```
static/
├── index.html            ← 页面结构（只有 DOM，数据全部由 JS 渲染）
├── README.md             ← 本说明
├── css/
│   ├── style.css         ← 模板原样式：光标光晕、呼吸滚动条、全息光幕、扫描打字机……
│   │                        （与设计模板逐字一致，不在这里改）
│   ├── modules.css       ← 模板之外新增的类：出行四段卡片、客服气泡、多选操作条等
│   └── theme.css         ← 三套主题：简洁现代 / 街头黑客 / 赛博暗色
└── js/
    ├── common/           ← 跨模块公用，与任何业务无关
    │   ├── config.js     ← API 地址、视图顺序、状态标签、打字机参数
    │   ├── utils.js      ← $、esc、now、scrollDown、getJson、bindEnter
    │   ├── abort.js      ← 请求中断控制（同一时刻只跑一个流）
    │   ├── sse.js        ← SSE 事件解析器
    │   ├── typer.js      ← 打字机渲染
    │   ├── selection.js  ← 列表多选删除（闲聊和出行共用）
    │   ├── sticky.js     ← 吸顶高度同步
    │   ├── aura.js       ← 光标光晕特效
    │   └── theme.js      ← 主题切换 + localStorage 记忆
    ├── app.js            ← 闲聊：会话列表 + 聊天区 + 视图切换 + 启动
    ├── trip.js           ← 智能出行：四段卡片、进度条、出行记录
    └── customer.js       ← 智能客服：一问一答
```

## 主题切换

右上角「主题」按钮可以切三套：

| 值 | 名字 | 样子 |
| --- | --- | --- |
| `clean` | 简洁现代 | 白底、细边框、紫色主色（默认） |
| `street` | 街头黑客 | 米白纸底、黑描边、硬阴影、荧光黄/品红 |
| `cyber` | 赛博暗色 | 原来的深色赛博霓虹 |

- 切换时改 `<html data-theme="...">`，选择存在 `localStorage` 的 `ctos_theme` 里，刷新后还记得。
- `index.html` 头部有一段内联脚本，在 CSS 加载前先把主题设好，避免刷新时闪一下旧主题。
- 主题相关的颜色/边框/阴影在 `css/theme.css` 里，业务逻辑（SSE、HITL、计时器）不受影响。

## 加载顺序不能乱

`index.html` 里的加载顺序是：

```html
<!-- 1. common/ 里都是无状态工具，最先加载 -->
<script src="/static/js/common/config.js"></script>
<script src="/static/js/common/utils.js"></script>
<script src="/static/js/common/abort.js"></script>
<script src="/static/js/common/sse.js"></script>
<script src="/static/js/common/typer.js"></script>
<script src="/static/js/common/selection.js"></script>
<script src="/static/js/common/sticky.js"></script>
<script src="/static/js/common/aura.js"></script>
<script src="/static/js/common/theme.js"></script>

<!-- 2. app.js 定义全局 state 和闲聊逻辑 -->
<script src="/static/js/app.js"></script>

<!-- 3. 两个模块依赖 app.js 的 state 和 common/ 的工具 -->
<script src="/static/js/trip.js"></script>
<script src="/static/js/customer.js"></script>
```

**为什么顺序重要**：这三个文件是普通 script，不是模块（没有 `import`），
所有函数和变量都挂在全局。后加载的能用先加载的，反过来就报 `undefined`。

`common/config.js` 必须排第一：`utils.js` 里的 `getJson()` 要用 `API.base`，
`selection.js` 里的 `historySelectable()` 要用 `state.view`（后者在 app.js 定义，运行时才读，没问题）。

## 每个文件负责什么

| 文件 | 职责 | 想改什么来这里 |
| --- | --- | --- |
| `common/config.js` | 部署地址、视图列表、状态文案 | 换后端地址、改输入框提示 |
| `common/utils.js` | 转义、时间、滚动、请求封装 | 加通用小工具 |
| `common/abort.js` | 中断上一个流 | 调并发行为 |
| `common/sse.js` | 解析 `data: {...}` | 后端换事件格式 |
| `common/typer.js` | 逐字渲染 | 调打字节奏（`config.js` 里的 CPS） |
| `common/selection.js` | 多选删除 | 改勾选交互 |
| `common/sticky.js` | 吸顶高度 | 出行页骨架高度错位 |
| `common/aura.js` | 鼠标光晕 | 改特效 |
| `common/theme.js` | 主题切换 + 本地记忆 | 加主题、改默认主题 |
| `app.js` | 闲聊 + 视图切换 + 启动 | 闲聊逻辑、Tab 切换 |
| `trip.js` | 出行 | 四段卡片、进度条、出行记录 |
| `customer.js` | 客服 | 问答交互 |



## 数据从哪来

页面里**没有任何写死的聊天数据**，全部来自后端：

| 区域 | 数据来源 |
| --- | --- |
| 左侧「会话记录」（闲聊） | `GET /sessions`，消息按需 `GET /sessions/{id}/messages` |
| 左侧「会话记录」（出行） | `GET /trip/list`，点开时 `GET /trip/{id}` 还原四段卡片 |
| 左侧（智能客服） | 客服一问一答不落库，这里只放一句说明 |
| 对话区 | `POST /chat` 的流式正文 |
| 出行四段卡片 | `POST /trip/chat` 的 SSE 事件 |
| 客服回答 | `POST /customer/chat` 的 SSE 事件 |

页面上唯一保留的固定文案是闲聊的空状态欢迎语（「你好。ctOS 在线…」）、出行空状态里的
三张示例卡、快捷指令胶囊，以及「新会话」按钮——它们都是引导用的、点击即发请求，不是模拟数据。

## 接口约定

| 模块 | 请求 | 响应 | 前端文件 |
| --- | --- | --- | --- |
| 闲聊 | `POST /chat` `{ messages, session_id? }` | `text/plain` 流式正文 + 响应头 `X-Session-Id` | `app.js` |
| 智能出行 | `POST /trip/chat` `{ query, history }` | `text/event-stream`（SSE） | `trip.js` |
| 智能客服 | `POST /customer/chat` `{ query }` | `text/event-stream`（SSE） | `customer.js` |

后端地址写在 `common/config.js` 顶部的 `API.base` 里，默认是空字符串——
也就是**同源访问**，前端用相对路径请求，所以**本地和线上（ctos2.cn）用同一份前端代码，不需要改任何地址**。换端口时前端也不用改。

### 闲聊为什么不是 EventSource

`EventSource` 只能发 GET，而 `/chat` 要 POST 一句话过去，所以用 `fetch` 读
`ReadableStream`（同一条 HTTP + 流式响应，浏览器原生支持）。SSE 同理：两个模块也各用
`fetch` 读流，再按 `\n\n` 切事件、解析 `data:` 行。

### 出行 / 客服的 SSE 事件

事件名统一，`kind` 字段区分：

| kind | 字段 | 前端处理 |
| --- | --- | --- |
| `START` | （出行：`query`） | 出行：记下合并后的需求供下一轮用；客服：占位符已经显示 |
| `STEP` | `key` + `text` | 该段卡片显示「正在查询天气…」之类的进度提示 |
| `TOKEN` | `key`? + `text` | 逐字追加到对应段落（出行带 `key`，客服不带） |
| `DONE` | `key`? + `text` | 用整段文本定稿，纠正逐字拼接的偏差 |
| `CHAT` | `message` | 出行判定为闲聊，直接回一句 |
| `ERROR` | `message` | 显示错误卡片 |

出行的 `key` 与四段卡片一一对应：`weather` → `spots` → `itinerary` → `route_plan`。

解析器同时兼容两种 SSE 写法：当前的 `data: {json}`（按 `kind` 分派），以及
`event: weather` + `data: ...`（event 名会被当作 kind；纯文本 `data` 则当作该段的增量文本）。

## 出行模块的页面结构（重要）

```
#view-trip
├── .trip-scroll-wrap        唯一的滚动容器
│   ├── #trip-fixed          常驻骨架：标题 + 四步流程条 + 示例卡（带 data-sticky-head）
│   └── #trip-feed           只有对话流：用户气泡 / 四段卡片 / 闲聊回复
└── .bottom-section
```

- **发消息时只清 `#trip-feed`**，`#trip-fixed` 永远不动 —— 这就是之前「一片黑、只剩用户气泡」的修复点。
- **多轮对话不覆盖**：每次发送都会在 `#trip-feed` 末尾新建一个 `.trip-turn`（用户这句话 + 这一轮的四段卡片），
  旧的轮次原样留在上面，可以往上翻看。轮与轮之间用一条虚线分隔。
  只有「新会话」才清空整个对话流。
  页面上往上翻时，右下会出现「回到最新」浮标，一键回到底部。
- **左侧出行记录 = 一条会话一行**（和闲聊模块一致）。后端 `trip_chats` 一次会话存一行，
  里面挂着多轮对话；列表显示「标题 + 轮数」，当前打开的那条高亮。
  - 同一次会话里连续聊几轮 → 左侧**只更新轮数**，不会多出一条；
  - 点「新会话」→ 下一条消息由后端新开一个会话，左侧多出一行；
  - 点开左侧任意一条 → 这个会话的**全部轮次**按顺序恢复出来，并可以接着在这个会话里聊。
- 旧数据库里的出行记录（一轮一条）会在启动时自动迁移成「一会话一轮」，不会丢。
- **三张示例卡只属于空状态**：只有空闲（没开始规划、没有对话内容）时显示；
  一按发送就立刻收起，骨架只剩下标题 + 流程条（高度从约 229px 收到约 125px）。
  回到空状态（「新会话」、删掉当前记录、首次进入）时会重新出现。
  显隐统一走 `tripCardsShow(show)`，它同时会重新测量骨架高度，避免留白错位。
- 流程条是动态的：`STEP` / `TOKEN` / `DONE` 会按段的 `key` 点亮 01~04，
  状态为 `wait / busy / done / error`（对应 `modules.css` 里的 `.process-step[data-state]`）。
- `#trip-feed` 通过 `padding-top: var(--sticky-h)` 给吸顶骨架让位，`--sticky-h` 由
  `app.js` 的 `syncStickyHeads()` 实测骨架高度写入，改标题字号也不会错位。
- 闲聊分流（`CHAT` 事件）不跑图，进度条保持原状，不会误标成全部完成。

## 流式渲染的手感

- **扫描占位**：请求发出后气泡先显示「接入大模型中...」，带模板里的 `.loading-bubble` 扫描动画。
- **打字机**：第一个片段到达即换成正文，末尾挂模板里的 `.type-cursor` 闪烁光标；
  之后每来一个片段立刻追加，只有「同一帧积压太多字符」时才按帧拆分（防一次糊出一大片）。
- **定稿**：`DONE` 或流结束时去掉光标，把换行渲染成 `<br>`，文本一律转义后再写入，不做 HTML 解析。

想调节奏，改 `app.js` 顶部的 `TYPE_FRAME_MS` / `TYPE_MIN_CPS` / `TYPE_MAX_CPS` 三个常量。

### 为什么有时看起来「卡很久」

出行图要串行跑完四个节点（天气 → 景点 + 联网搜索 → 行程 → 路线），每个节点都是一次完整的模型调用，
单段往往就要 20~30 秒。实测一次完整规划的 `DONE` 到达时间约为 **28s / 58s / 77s / 77s**。
所以「某一段 20 多秒没有新字」是模型在生成，不是前端没渲染：

- `STEP` 到达时该格会立刻闪烁，卡片显示「正在查询天气…」，说明连接是通的；
- 那一段的第一批 `TOKEN` 到达后才会开始逐字出字；
- 每段结束的 `DONE` 会把该段定稿，并把进度条那一格标绿。

如果要在等待期间看到更多反馈，可以在 `trip.js` 的 `STEP` 分支里加一个「已等待 Ns」的计时器
（`tripSeconds()` 已经算好了）。


## 侧边栏与「新会话」

- 会话列表从 `GET /sessions` 渲染，点击切换会按需拉该会话的消息；垃圾桶按钮调用
  `DELETE /sessions/{id}`（出行记录对应 `DELETE /trip/{id}`）。
- 「新会话」保留模板的全息光幕动画：光幕扫下 → 0.3 秒后清空对话区 → 开一个待入库的新对话，
  下一条消息由后端建会话并通过 `X-Session-Id` 回传 id。
  出行视图下「新会话」= 回到空状态引导并清掉多轮上下文；客服视图下 = 清空回到引导页。

## 三个模块的界面切换

顶栏的 `nav-tab` 直接调用 `switchView('chat' | 'trip' | 'customer')`，
主视图、右上状态标签、左侧列表、底部端点标签、输入框提示语会跟着切换。

## 后端怎么提供这些静态文件

静态目录要能被浏览器访问，后端必须挂载它。相关代码在 `api/main.py` 里：

```python
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")
```

`mount` 挂在 `/static` 前缀下，与其他路由（`/chat`、`/sessions`、`/trip/...`、`/customer/...`）不冲突。
根路径 `/` 直接返回 `index.html`，所以访问 <http://127.0.0.1:8080/> 就是本地页面，
<https://ctos2.cn/> 就是线上页面。

## 改完前端怎么自检

以前有一个 `_selftest.html` 自检页（用隐藏 iframe 逐个检查函数是否就绪），已经删掉了：
它只能验证"函数存在"，验证不了真实行为，而且部署后会被公网直接访问。

现在改用浏览器 DevTools：

1. 打开 <http://127.0.0.1:8080/>，按 F12 打开 Console
2. 刷新页面，**看有没有红色报错** —— 有就说明脚本加载失败
3. 直接在 Console 里调用要验证的函数，例如：

```js
typeof sendTrip        // "function"
createSseParser        // 能看到函数体
state.view             // 当前在哪一屏
```

真要看行为，就实际点一遍三个模块。这比自检页更接近真实情况。

## 改完前端怎么验证线上

本地自测通过后，按 `docs/deployment.md` 第九节上线，然后：

1. 打开 <https://ctos2.cn/>，按 Ctrl+F5 强制刷新
2. **重新登录一次**（token 存在浏览器里，换域名或换环境不会带过去）
3. 三个模块各点一遍：闲聊发一句、出行问「杭州玩 3 天」、客服问「端口怎么改」

