# 前端文件说明

> 本文是 `static/README.md` 的副本，放在知识库里供智能客服检索。
> 行数和字节数是**写本文时的实测值**，前端一改就会变，以实际文件为准。

前端没有构建步骤。`index.html` 只放页面结构，CSS 和 JS 都在独立文件里，
**改前端直接改 `css/` 和 `js/` 即可，改完刷新浏览器就生效，不需要任何编译或打包**。

```
static/
├── index.html        ← 页面结构，112 行 / 4385 字节
├── README.md         ← 本说明
├── css/
│   └── style.css     ← 全部样式，693 行
└── js/
    ├── app.js        ← 核心脚本：状态、侧边栏、闲聊、模块切换，915 行
    ├── trip.js       ← 智能出行，363 行
    ├── customer.js   ← 智能客服，147 行
    └── app.js.bak    ← 旧版单文件备份，未被页面加载
```

`index.html` 用下面这几行引用外部文件：

```html
<link rel="stylesheet" href="/static/css/style.css" />

<script src="/static/js/app.js"></script>
<script src="/static/js/trip.js"></script>
<script src="/static/js/customer.js"></script>
```

## 三个 JS 文件的加载顺序不能乱

必须按 `app.js → trip.js → customer.js` 的顺序加载。

`trip.js` 和 `customer.js` 里用到的 `$`、`esc`、`md`、`API`、`state`、`send`、`newAbortSignal`
等函数和变量都定义在 `app.js` 里。如果 `app.js` 排在后面，这两个文件一加载就会报错。

`app.js` 末尾的初始化写在 `DOMContentLoaded` 里，就是为了等三个文件都就绪后再调用
`tripReset()` / `customerReset()`，否则会因为函数还不存在而报错。

`app.js.bak` 是旧版备份，页面并未引用，可以删除。

## 改前端的流程

编辑 `static/css/style.css` 或 `static/js/` 下的任意文件 → 保存 → 刷新浏览器。

**就这两步**，没有生成步骤、没有构建命令、没有需要同步的副本。

## 后端怎么提供这些静态文件

静态目录要能被浏览器访问，后端必须挂载它。相关代码在 `src/ctOS_chat_api.py` 里：

```python
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")
```

`mount` 挂在 `/static` 前缀下，与其他路由（`/chat`、`/sessions`、`/trip/...`、`/customer/...`）不冲突。
根路径 `/` 直接返回 `index.html`，所以访问 <http://127.0.0.1:8080/> 就是页面。

## 前端与后端的接口约定

| 模块 | 请求 | 响应类型 | 前端文件 |
| --- | --- | --- | --- |
| 闲聊 | `POST /chat` | `text/plain` 流式文本 | `app.js` |
| 智能出行 | `POST /trip/chat` | `text/event-stream`（SSE） | `trip.js` |
| 智能客服 | `POST /customer/chat` | `text/event-stream`（SSE） | `customer.js` |

后端地址写在 `app.js` 顶部的 `API.base` 里，默认是空字符串——
也就是**同源访问**，前端用相对路径请求，换端口时前端不用改。

SSE 事件的解析逻辑在两个模块文件里各写了一份（按 `\n\n` 切分、识别 `data: ` 开头），
事件名统一是 `START` / `STEP` / `TOKEN` / `DONE` / `CHAT` / `ERROR`。

## 三个模块的界面切换

顶栏有三个按钮：闲聊、智能出行、智能客服，对应 `app.js` 里的 `state.mode`。

三个面板互斥：

- 闲聊用 `#stream`
- 出行用 `#tripPanel`
- 客服用 `#customerPanel`

切到出行时，左侧栏换成出行记录列表；切到客服时，左侧栏整个收起（因为客服不留记录）。

跑图期间也可以切换模块，不会打断正在跑的那张图——三个面板的 DOM 各自保留。
