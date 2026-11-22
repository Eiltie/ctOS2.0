# 前端样式维护说明

> 当前前端是 **Vue 3 + TypeScript + Vite**，全在 `web/` 下。
> 本文讲样式怎么组织、改配色改哪里。

---

## 一、样式怎么组织

**每个 `.vue` 文件自带自己的样式**，写在文件末尾的 `<style scoped>` 里。

`scoped` 的意思是：**这段样式只对当前组件生效**，不会影响别的组件。
所以你可以放心写 `.title { ... }`，不会和别处的 `.title` 打架。

```
web/src/
├── features/chat/ChatView.vue       ← 它的样式写在 ChatView.vue 自己的 <style scoped> 里
├── features/trip/TripView.vue       ← 同理
└── shared/styles/tokens.css         ← 全局的配色和尺寸变量（唯一的全局样式）
```

**全局只有一个样式文件**：`web/src/shared/styles/tokens.css`。

---

## 二、配色和尺寸：只改 tokens.css

`tokens.css` 里定义了 CSS 变量（自定义属性），全项目的颜色、字号、圆角、间距都从这里取：

```css
:root {
  --bg: #ffffff;
  --text: #1a1a1a;
  --accent: #4a7cff;
  --radius: 12px;
  --gap: 16px;
}
```

组件里这样用：

```css
.btn {
  background: var(--accent);
  border-radius: var(--radius);
}
```

**想换配色，只改 `tokens.css` 一个文件**，所有组件跟着变。

> 不要在组件里写死颜色（`#4a7cff`），一律用变量。

---

## 三、手机端适配

组件里的媒体查询这样写：

```css
@media (max-width: 768px) {
  .sidebar { display: none; }
}
```

**断点统一用 768px**，别在组件里各写各的。

---

## 四、改样式的工作流程

1. 改对应组件的 `<style scoped>`，或者改 `tokens.css`
2. **必须重新构建**（Vue 不能直接跑）：

```powershell
cd web
npm run build
```

3. 刷新浏览器看效果

**开发时更快的方式**：用热更新服务器，改代码浏览器自动刷新：

```powershell
cd web
npm run dev        # 打开 http://127.0.0.1:5174
```

> 线上的话还要跑 `node scripts/stamp-static.js` 给资源加版本号，
> 否则 Cloudflare 的 4 小时缓存会让用户看不到改动。

---

## 五、加一个新组件

1. 在 `web/src/shared/components/` 下新建 `Xxx.vue`
2. 样式写在它自己的 `<style scoped>` 里
3. 颜色和尺寸用 `tokens.css` 的变量

**不要**在 `web/src/` 下另建一个全局 `.css` 文件来放组件样式，
那会绕开 `scoped`，容易误伤别的组件。
