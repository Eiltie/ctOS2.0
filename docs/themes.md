# 主题维护说明

页面现在有三套主题，右上角「主题」按钮切换：

| 值 | 名字 | 特点 |
| --- | --- | --- |
| `clean` | 简洁现代 | 白底、细边框、紫色主色（默认） |
| `street` | 街头黑客 | 米白纸底、黑描边、硬阴影、荧光色 |
| `cyber` | 赛博暗色 | 深色底、玻璃面板、青紫渐变 |

选择存在浏览器 `localStorage` 的 `ctos_theme` 里，刷新后保留。

## 文件分工

| 文件 | 管什么 |
| --- | --- |
| `static/index.html` | 页面结构；头部内联脚本在 CSS 前设好主题，避免刷新闪一下 |
| `static/css/style.css` | 基础布局和模板原样式（光标、滚动条、光幕等） |
| `static/css/modules.css` | 三个模块的布局和组件骨架 |
| `static/css/theme.css` | 三套主题的颜色、边框、阴影、圆角、字体覆盖 |
| `static/js/common/theme.js` | 切换按钮、菜单、localStorage 记忆 |

**布局只写一份。** 三套主题共用同一份 HTML 和 `style.css` / `modules.css` 的布局；
`theme.css` 只负责“换皮”。

## 以后改前端，要改几处？

| 改动 | 要改几处 | 去哪改 |
| --- | --- | --- |
| 改排版、间距、HTML 结构 | **1 处** | `index.html` / `style.css` / `modules.css` |
| 改文案、按钮文字 | **1 处** | `index.html` / 对应的 JS |
| 改主色、边框、阴影、圆角 | **3 套主题各一次**，但通常只是改变量或几行覆盖 | `theme.css` |
| 加一个新组件 | **1 份基础样式 + 检查三套主题** | `modules.css` 写骨架，`theme.css` 补差异 |
| 加第四套主题 | 复制一个变量块 + 菜单加一项 | `theme.css` / `theme.js` / `index.html` |

重点是：**不是把整个页面写三遍**。布局和结构只有一份，主题层只覆盖视觉差异。

## 加新组件时的做法

1. 在 `modules.css` 里用基础变量写一份样式，例如：
   ```css
   .my-card {
       background: var(--bubble-ai);
       border: 1px solid var(--border-color);
       color: var(--text-main);
   }
   ```
2. 如果三套主题都需要不同的值，优先加变量，而不是给三套各写一遍选择器。
3. 只有“街头黑客”的黑描边、硬阴影、警戒条这类结构差异，才在
   `theme.css` 的 `html[data-theme="street"]` 段里单独补。
4. 三套主题各看一眼，再在手机宽度（约 390px）看一次。

## 预览主题

- 正常方式：右上角「主题」按钮。
- 控制台快速切：
  ```js
  ctosApplyTheme("clean")
  ctosApplyTheme("street")
  ctosApplyTheme("cyber")
  ```
- 临时改默认主题：改 `theme.js` 里的 `DEFAULT_THEME`，同时改 `index.html`
  的 `<html data-theme="clean">` 兜底值。

## Shoelace 组件

主题菜单和反馈弹窗已经换成 Shoelace（Web Components）：

- 本地文件在 `static/vendor/shoelace/`，是 2.20.1 的 `cdn` 构建，**不走 CDN、不需要构建**。
- `index.html` 引入 `themes/light.css`、`themes/dark.css` 和 `shoelace-autoloader.js`。
- 三套主题通过 `theme.css` 里的 `--sl-*` 变量和 `::part()` 覆盖颜色、边框、圆角。
- 赛博主题会给 `<html>` 加 `sl-theme-dark` 类。
- 这个目录不要删；删了主题菜单和反馈弹窗会变回未注册的自定义元素。

## 当前主题层的取舍

- `clean` 和 `cyber` 大部分共用布局，只换颜色/圆角/阴影/字体。
- `street` 额外加了 2px 黑边、硬阴影、方角、警戒条和贴纸标签；这些是它独有的，
  集中在 `theme.css` 的 street 段，不影响另外两套。
- 主题层只改样式，不改 SSE、人工确认、计时器和数据库逻辑。

以后如果主题样式继续变大，可以把 `theme.css` 拆成
`theme-clean.css` / `theme-street.css` / `theme-cyber.css` 三个文件，
按当前主题动态加载；现在还没必要。
