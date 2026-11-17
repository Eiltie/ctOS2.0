# 主题维护说明

前端现在分成 **两套主题**（完全独立的两个页面），各自内部再分 **风格**（配色）。

| 主题 | 名字 | 版式 | 适合 |
| --- | --- | --- | --- |
| `A` | 经典版 | 左侧栏 + 顶栏 tab + 气泡对话 | 所有屏幕，**手机端只用它** |
| `B` | 指挥台版 | 图标导轨 + 右侧控制台 | 只给宽屏（≥ 900px） |

每套主题自己的风格：

| 主题 | 风格（`data-theme` 值） |
| --- | --- |
| A 经典版 | `clean` 简洁现代（默认）/ `street` 街头黑客 / `cyber` 赛博暗色 |
| B 指挥台版 | `console-light` 晨光控制台（默认）/ `console` 指挥台 |

## 目录结构

```
static/
├── index.html              入口页：读偏好 + 判断屏幕宽度，然后跳转
├── themeA/                 经典版（旧版页面 + 3 种风格）
│   ├── index.html
│   ├── css/
│   └── js/
├── themeB/                 指挥台版（新版页面 + 2 种风格）
│   ├── index.html
│   ├── css/
│   └── js/
└── shared/                 两套共用
    ├── image/
    └── js/common/          prefs / presence / config / auth / sse …
```

两套主题 *互不引用*：删掉 `themeB/` 不影响 `themeA/`，反之亦然。
只有 `shared/` 里的文件是两边共用的。

## 文件分工

### 入口与偏好

| 文件 | 管什么 |
| --- | --- |
| `static/index.html` | 入口页。读偏好、判断屏幕宽度，用 `location.replace()` 分流 |
| `static/shared/js/common/prefs.js` | 主题/风格的读写；`isDesktop()` 判断屏幕；手机端锁定经典版 |

### 经典版（themeA）

| 文件 | 管什么 |
| --- | --- |
| `themeA/index.html` | 页面结构 |
| `themeA/css/style.css` | 基础布局和模板原样式（光标、滚动条、光幕等） |
| `themeA/css/modules.css` | 三个模块的布局和组件骨架 |
| `themeA/css/theme.css` | 三套风格的变量定义 |
| `themeA/css/ui.css` | 视觉层：圆角、阴影、气泡、排版细化 |
| `themeA/css/theme-ui.css` | 「主题 / 风格」两个菜单的样式 |
| `themeA/css/presence.css` | 侧栏底部在线人数 |
| `themeA/css/mobile.css` | **手机端适配**，最后加载，只在 ≤768px 生效 |
| `themeA/js/common/theme-ui.js` | 主题/风格菜单的渲染与切换 |

### 指挥台版（themeB）

| 文件 | 管什么 |
| --- | --- |
| `themeB/index.html` | 页面结构；窄屏会自动送回经典版 |
| `themeB/css/base.css` | 复用旧版的布局骨架（从 themeA 复制） |
| `themeB/css/components.css` | 复用旧版的弹窗/组件类（从 themeA 复制） |
| `themeB/css/style.css` | 指挥台版自己的版式 |
| `themeB/css/theme-light.css` | 两套风格的配色令牌 |
| `themeB/js/console.js` | 右侧控制台：目录、操作日志、系统负载 |
| `themeB/js/theme-ui.js` | 浮动面板形式的主题/风格切换 |

## 手机端规则

**手机上永远用经典版**，不给切换入口。这条规则由三层保证：

| 层 | 位置 | 作用 |
| --- | --- | --- |
| ① 入口页 | `static/index.html` | 从 `/` 进来的按屏幕宽度分流 |
| ② 页面自检 | `themeB/index.html` | 直接访问 themeB 地址也会被送回 |
| ③ 函数拦截 | `prefs.js` 的 `goLayout()` | 强行调用也留在经典版 |

判定阈值是 `prefs.js` 里的 `DESKTOP_MIN_WIDTH = 900`（px）。

原因：指挥台版靠「左侧图标导轨 + 右侧控制台」两块固定宽度撑起来，
手机上这两块都没有空间。

## 以后改前端，要改几处

| 改动 | 去改哪里 |
| --- | --- |
| 只改经典版 | `themeA/` 下对应文件 |
| 只改指挥台版 | `themeB/` 下对应文件 |
| 两套一起改 | 各改一次（这是「两套独立」的代价） |
| 改共用逻辑（请求、认证、SSE） | `shared/js/common/`，两边自动生效 |
| 加一种风格 | 在 `prefs.js` 的 `STYLES` 里加一项 + 对应 CSS 变量块 |
| 加一套新主题 | 新建 `static/themeC/` + `prefs.js` 的 `LAYOUTS` 加一项 |

## 加新组件时的做法

1. 先确认它属于哪套主题：只有一套需要就写在那套的 `modules.css` / `style.css`；
   两套都要就在各自的骨架里各写一份。
2. 颜色一律用变量，不要写死色值：
   ```css
   .my-card {
       background: var(--bubble-ai);
       border: 1px solid var(--border-color);
       color: var(--text-main);
   }
   ```
3. 改完在**三处**各看一遍：桌面亮色、桌面暗色、手机（约 390px）。

## 预览与调试

- 正常方式：侧栏（经典版）/ 导轨（指挥台版）里的「主题」「风格」按钮。
- 控制台快速切风格：
  ```js
  ctosPrefs.setStyle('cyber', 'A'); ctosPrefs.applyStyle('cyber')
  ```
- 控制台快速切主题：
  ```js
  ctosPrefs.goLayout('B')
  ```
- 想强制看成经典版：清掉 `localStorage` 的 `ctos_layout` 即可。

## 改完之后别忘了

站点走 Cloudflare，`.js` / `.css` 会被缓存 4 小时（覆盖了后端的 `no-cache`）。
改完前端要跑一次版本号脚本，否则用户看到的还是旧文件：

```bash
node scripts/stamp-static.js
```
