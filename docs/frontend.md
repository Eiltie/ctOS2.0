# ctOS 2.0 前端

> Vue 3 + TypeScript。这份文档回答两个问题：**文件都在哪**、**要加东西改哪里**。

---

## 一、两处位置

| 目录 | 是什么 | 谁用 |
| --- | --- | --- |
| `web/` | 源码，你写代码的地方 | 只有开发时 |
| `static/dist/` | 打包产物（自动生成，不要手改） | 浏览器 / Docker |

**改完代码要构建**，否则浏览器看到的还是旧的：

```bash
cd web
npm install        # 第一次
npm run build      # 生成 static/dist
```

后端 `api/routes/system.py` 的 `/` 会返回 `static/dist/index.html`。
WSL / 容器里挂载的是 `static/`，所以产物放这里不用改任何部署配置。

---

## 二、日常开发

```bash
cd web
npm run dev        # 开发服务器，改代码自动刷新（端口 5174）
```

开发服务器会把接口请求转发给 `127.0.0.1:8080`。
后端跑在别的地址时：

```bash
CTOS_BACKEND=http://127.0.0.1:8081 npm run dev
```

后端要单独启动：`python -X utf8 -m api.main`

---

## 三、目录结构

```
web/src/
├── main.ts                 入口：装路由、启动登录、挂载
├── App.vue                 根组件
├── AppShell.vue            壳层：顶栏 + 玩法条
├── router.ts               路由表
│
├── shared/                 所有模块共用
│   ├── api/
│   │   ├── http.ts         请求封装（带 token、错误转中文）
│   │   └── stream.ts       流式读取（纯文本流 + SSE 事件流）
│   ├── auth/authStore.ts   登录、访客自动登录
│   ├── components/         通用组件（顶栏、玩法条、输入框、空状态）
│   ├── lib/
│   │   ├── navigation.ts   顶部有哪些模块、每个模块有哪些玩法
│   │   └── typewriter.js   流式文字合并（纯 JS，有 node 测试）
│   ├── styles/tokens.css   配色、字号、间距 —— 改配色只改这里
│   └── types/api.ts        后端返回的字段类型（全项目唯一一份）
│
└── features/               各模块，互不引用
    ├── chat/               对话（闲聊 + 角色扮演）
    │   ├── ChatView.vue        两种玩法共用这一个页面
    │   ├── SessionList.vue     左侧会话列表
    │   ├── MessageBubble.vue   一条消息
    │   ├── store.ts            会话与消息状态
    │   ├── api.ts              /sessions、/chat/attachment
    │   └── roleplay/           角色扮演（对话的子玩法）
    │       ├── RolePickerView.vue   选角色
    │       ├── RoleCardItem.vue     一张角色卡
    │       ├── RoleFormPanel.vue    自己写 / 确认 AI 草稿
    │       ├── RoleSearchPanel.vue  AI 帮我查
    │       ├── RoleProfilePanel.vue 角色档案
    │       ├── RoleMemoryPanel.vue  角色记忆
    │       ├── store.ts             角色状态
    │       └── api.ts               /roleplay/*
    ├── trip/               智能出行
    └── customer/           智能客服
```

**模块边界是硬的**：`features/chat` 不能 import `features/trip`，`shared` 不能 import `features`。
写错了 ESLint 会直接报错。要共用代码就挪到 `shared/`。

---

## 四、加功能改哪里

这张表是这个文档最重要的部分。

| 我想… | 改哪里 | 要改几个文件 |
| --- | --- | --- |
| **改配色** | `shared/styles/tokens.css` | 1 |
| **加一个玩法**（如语音陪练） | `shared/lib/navigation.ts` 的 `CHAT_MODES` 加一项<br>+ `features/chat/` 新建页面<br>+ `router.ts` 加一条子路由 | 3 |
| **加一个模块** | `shared/lib/navigation.ts` 的 `MODULES` 加一项<br>+ `features/新模块/` 新建<br>+ `router.ts` 加一条路由 | 3 |
| **后端加了一个字段** | `shared/types/api.ts` 加一行，用到的地方跟着改 | 1~2 |
| **后端加了新的 SSE 事件** | `features/对应模块/` 里处理这个 `kind`<br>+ `shared/types/api.ts` 加类型 | 2 |
| **加一个通用组件** | `shared/components/` 新建 | 1 |
| **改某个页面的样子** | `features/某模块/` 下对应 `.vue` | 1 |

### 加玩法为什么这么改

玩法不在顶栏，在对话页内部那条**玩法条**上。
`navigation.ts` 里 `CHAT_MODES` 是个数组，加一项就多一个按钮，
横向自动排开，顶栏和布局都不用动。

---

## 五、四条硬约束

前三条是 `npm` 脚本，第四条要单独起服务。

### 1. 类型检查 —— 字段名写错编译就报

```bash
npm run typecheck
```

`shared/types/api.ts` 里的字段名和后端一一对应。
写错成 `turnCount`（后端叫 `turn_count`）会直接报错：

```
Property 'turnCount' does not exist on type 'TripSummary'. Did you mean 'turn_count'?
```

### 2. 接口契约校验 —— 后端改字段前端立刻知道

```bash
npm run check:api
```

会去拉后端的 `GET /contract`，和前端认的字段逐项比对。
对不上就红，并指出是哪个接口的哪个字段。

也可以校验线上：

```bash
CTOS_BACKEND=https://ctos2.cn npm run check:api
```

**注意**：后端没启动时这个检查会**失败**（而不是跳过）。
这是故意的 —— 跳过会让 CI 里出现「假绿」，等于没查。

### 3. 模块边界 —— 跨模块引用直接报错

```bash
npm run lint
```

`features` 下的模块不能互相引用，`shared` 不能引用 `features`。
错误提示是中文的，会告诉你该挪到哪。

### 4. 端到端行为测试 —— 改完代码知道有没有弄坏别处

```bash
# 需要先起后端（PORT=8082 python -X utf8 -m api.main）
cd web
npm run test:e2e              # 全部
npm run test:e2e -- chat      # 只跑某一组
```

会驱动真实浏览器点真实界面，检查「点击之后发生了什么」。

**为什么需要这一条**：
前三条都是结构性检查 —— 类型对了、边界没破、字段没改，代码依然可能行为出错。
真实例子：给会话列表加静默刷新之前，点一下会话左侧就会闪「加载中」。
类型、lint、契约三条全绿，但用户体验是坏的。
只有连续采样（每 30ms 看一次页面）才能发现。

**测试分组**：

| 分组 | 测什么 |
| --- | --- |
| `infra` | 页面能打开、无 JS 报错、契约可用 |
| `chat` | 会话列表加载、切换不闪烁、点开显示消息 |
| `roleplay` | 角色卡片、开始对话、档案/记忆面板、表单校验 |
| `nav` | 三个模块切换、玩法条切换 |
| `send` | 真实发消息、收到流式回复、按钮状态恢复 |
| `image` | 上传图片、缩略图预览、发出去、删除待发图片 |
| `customer` | 欢迎页、引导问题、流式回答、清空对话 |
| `trip` | 空状态、两套数据独立、直接回答、路线全流程、攻略全流程、历史回放、切换不闪、同会话不拆记录 |
| `auth` | 登录弹层、注册成功切换身份、表单校验 |
| `feature` | 访客刷新不丢、会话多选删除、出行记录多选删除、反馈提交 |
| `tripimg` | 出行跑完主动提议生成图（只验证提议，不真画） |

**共 11 组 35 个测试，全跑约 6 分钟。**

关于费用：`tripimg` 这组**故意不真调生图接口**（画一张要花调用额度）。
所以生图这条链路的判断逻辑靠 Python 单测覆盖，e2e 只保证「提议会出现、不会自动画」。

**写新测试**：见 `web/scripts/e2e/run_all.py` 顶部的注释。要点：

- 用 `check(条件, 说明)` 断言，不用 `assert` —— 一次能看到所有失败点
- 用 `sample(...)` 连续采样检查「闪一下」这类瞬时问题
- 测试会真的调模型，关键路径上发一两句就够，别每处都发

---

## 六、和后端接口的对应关系

后端所有接口的字段约定写在 `api/contract.py`，通过 `GET /contract` 暴露。

**改了后端字段要做的**：

1. 改真实代码
2. 改 `api/contract.py` 里对应的声明，并更新 `CONTRACT_VERSION`
3. 改 `web/src/shared/types/api.ts`
4. 改 `web/scripts/check-api-contract.mjs` 里的 `FRONTEND_*`
5. 跑 `npm run check:api` 确认绿了

### 流式接口的两种格式

前端的 `shared/api/stream.ts` 负责解析，业务层只管收事件。

| 接口 | 格式 | 说明 |
| --- | --- | --- |
| `POST /chat` | 纯文本 | 会话 id 在响应头 `X-Session-Id` |
| `POST /trip/chat` | SSE 事件 | 每行 `data: {...}`，看 `kind` 字段 |
| `POST /trip/route/choose` | SSE 事件 | 同上 |
| `POST /trip/route/place` | SSE 事件 | 同上 |
| `POST /guide/spots` | SSE 事件 | 同上 |
| `POST /customer/chat` | SSE 事件 | 同上 |

出行的事件有 11 种：`SAY` `START` `STEP` `TOKEN` `DONE` `CHAT` `SAVED` `ERROR` `ASK` `ASK_PLACE` `ASK_SPOTS`。
完整说明见 `api/contract.py` 的 `SSE_KINDS`。

---

## 七、几个容易搞混的概念

### 角色扮演不是一个模块

它是**对话**下面的一个玩法，路由是 `/chat/roles`。
后端也一致：角色会话和闲聊共用 `sessions` 表，靠 `role_id` 区分。

**同一条消息，两种玩法走同一个接口**：

```
普通闲聊    POST /chat                    不带 role_id
角色扮演    POST /chat  带 role_id         后端换提示词和温度
```

所以 `features/chat/store.ts` 的 `send()` 会自动带上 `state.activeRoleId`。
界面上的区别只有一个：角色会话的标题栏多出「档案 / 记忆 / 换个角色」。

**新建角色有两条路，用的都是同一个表单**：

| 入口 | 流程 |
| --- | --- |
| 自己写一个 | `RoleFormPanel`（空白）→ `POST /roleplay/roles` |
| AI 帮我查 | `RoleSearchPanel` → `POST /roleplay/roles/search`（联网+模型，十几秒）→ `RoleFormPanel`（预填、可改）→ 保存 |

**开场白的约定**：后端没有单独的开场白字段，约定写在「补充说明」里，格式是
`开场白：xxx`（见 `modules/chat/roleplay/openings.py` 的 `split_opening`）。
前端做成了独立输入框，提交时拼进 `extra`。不填就让模型生成一句。

### 图片上传

**分两步**，和后端设计一致：

```
1. POST /chat/attachment      选图后立刻上传，拿到 image_id
2. POST /chat  带 image_ids   发消息时把 id 带上
```

这样用户可以传三张删两张、传完再改文字，最后只发一次。

**后端的限制**（`modules/chat/attachments.py`）：

| 项 | 值 |
| --- | --- |
| 单张大小 | 8 MiB |
| 一条消息最多 | 3 张 |
| 支持的格式 | JPEG / PNG / GIF / WebP |

前端在 `features/chat/api.ts` 里也放了一份同样的常量，**本地先校验**，
免得传完几 MB 才收到 400。

**几个必须注意的实现细节**：

1. **图片要用 blob 取，不能直接 `<img src>`**
   `GET /chat/attachment/{id}` 要求带 token，而 `<img>` 加不了请求头。
   所以 `AttachmentImage.vue` 先 fetch 成 Blob 再转 objectURL。
   **用完必须 `revokeObjectURL`**，否则内存不回收。

2. **只发图不打字时，给个占位文字**
   后端 `messages` / `query` 都是必填的，空字符串会被拒。
   前端在 `store.send()` / `tripStore.ask()` 里补一句「（发了一张图片）」。

3. **一张图只能发一次**
   后端 `resolve_images` 会过滤掉 `message_id` 不为空的图（防止一张图挂到多条消息上）。
   所以同一张图第二次发出去，后端会当作没带图 —— 这是**正确行为**，不是 bug。
   测识图时要用新上传的图。

4. **待发图片挂在 store 上，不是组件里**
   因为「选图 → 打字 → 发送」跨多个交互，放组件里一切换会话就丢了。
   切换会话 / 新建会话时会清空。

### 图片相关代码在哪

对话和出行都要传图，所以这部分放在 `shared/`：

```
src/shared/
├── attachments/
│   ├── api.ts              上传、取图、大小/数量限制
│   ├── AttachmentImage.vue 带鉴权的图片（blob → objectURL）
│   ├── PendingImages.vue   输入框上方的待发预览条
│   └── ImageLightbox.vue   点开看大图
└── lib/imageQueue.ts       待发图片队列（两个模块各一个实例）
```

两个模块都用 `createImageQueue()` 各建一个队列，互不干扰。

### 出行的识图：提示词里必须写清楚

**踩过的坑**：前端把图传上去了，模型却说「我识别不了图片」。

原因是 `modules/trip/prompts.py` 里的提示词只讲「怎么判断动作」，
没提图片；而且有一条「和出行无关的问题 → 说明你只管出行」的规则，
模型看到「这是啥」就按规则回避了。

现在提示词里单独有一段「用户发了图片」，明确要求：

- 先如实描述图里是什么，再联系出行
- 非旅游的图也要说出来是什么，不能装作没看见
- **禁止说「我识别不了」「我看不到图」**

**改了 Python 代码必须重启后端**，否则跑的还是旧代码。
前端改完只需要 `npm run build`，后端改完两个都要 —— 这点容易忘。

对话模块（`modules/chat/prompts.py`）目前没有这段规则，
但它的提示词很短、没有回避规则，所以看图是正常的。

### 对话列表和出行记录是两套数据

| | 对话 | 出行 |
| --- | --- | --- |
| 接口 | `GET /sessions` | `GET /trip/list` |
| 表 | `sessions` / `messages` | `trip_chats` 等 4 张 |

**互不相干**，同一个名字可能两边各有一条，是两个不同的会话。

### 路线/攻略是「每一轮」的能力，不是会话的属性

出行的一个会话里，每一轮由后端单独判断走哪条路：
`action=route` 调路线子图、`action=guide` 调攻略子图、`action=answer` 直接回答。

所以：

- **左侧出行记录**只显示标题和轮次数，**不标类型**
- **每一轮**各自的卡片上才标「路线」或「攻略」

### 出行的四种走向

用户不需要选「我要路线还是攻略」。说一句话，Agent 自己判断：

| 用户说了什么 | 事件序列 | 界面表现 |
| --- | --- | --- |
| 「北京有什么好玩的」 | `SAY` → `CHAT` | 一个普通气泡 |
| 「从A到B怎么走」 | `SAY` → `START(ROUTE)` → `STEP` → `DONE` → `STEP` → `ASK` | 需求确认卡片 + **方案选择面板** |
| 选完方案后 | `SAY` → `TOKEN/DONE` ×3 → `SAVED` | 剩下三段卡片逐字填满 |
| 「下周去杭州玩3天」 | `SAY` → `START(TRAVEL)` → `STEP` → `DONE/DONE` → `ASK_SPOTS` | 天气、景点卡片 + **勾选面板** |
| 勾完景点后 | `SAY` → `TOKEN/DONE` ×2 → `SAVED` | 行程、建议两段填满 |

**这些判断全部收在 `features/trip/events.ts`**，组件只负责按状态画。
加新事件或改某段的处理，只动那个文件。

### 出行的三个等待面板

| 面板 | 触发事件 | 用户做什么 |
| --- | --- | --- |
| `RouteAskPanel` | `ASK` | 从几个方案里选一条（带推荐标记） |
| `PlaceAskPanel` | `ASK_PLACE` | 地名有歧义时挑具体位置 |
| `SpotsAskPanel` | `ASK_SPOTS` | 勾掉不想要的景点，或补一个 |

后端的约定：`removed` 是用户去掉的景点名数组，`added` 是额外加的一个。
所以勾选面板默认全选，取消勾的进 `removed`。

### 客服不存会话

后端客服不写数据库，刷新就没了。
所以客服页没有左侧列表，界面上也明确写了「刷新后对话不保留」。

**上下文完全靠前端带**：

```ts
// features/customer/api.ts
buildHistory(messages, turns = 3)   // 只带最近 3 轮
```

后端收到 `history` 后自己也会截到最近 3 轮（`modules/customer/node.py` 的 `HISTORY_TURNS`），
前端先截一次只是省点带宽。

**事件流比出行简单得多**，只有 4 种：

| 事件 | 含义 |
| --- | --- |
| `START` | 开始处理（界面显示「正在检索资料…」） |
| `TOKEN` | 逐字输出 |
| `DONE` | 定稿（带全文） |
| `ERROR` | 出错 |

注意：固定话术（寒暄、拒答）会把整段补发成 TOKEN，再发 DONE 全文。
合并规则和闲聊一样 —— 用 `StreamText`，有 DONE 就以 DONE 为准，避免文字重复。

---

## 八、验证

```bash
cd web
npm run typecheck    # 类型
npm run lint         # 模块边界 + 代码质量
npm run check:api    # 后端字段一致性（需要后端在跑）
npm run build        # 构建
```

浏览器端冒烟测试（会真的发一条消息给模型）：

```bash
python -X utf8 web/scripts/smoke_chat.py
```

前置：后端在 8082 端口跑着，`config/.env` 里配好了 `DEEPSEEK_API_KEY`。

截图会存到 `web/design-preview/`。

---

## 九、生图能力（没有前端入口）

生图**不是**前端的一个功能入口，而是对话和出行背后的能力。
界面上没有任何「生成图片」的按钮，用户要在聊天里说出来。

### 对话：用户要图就画

```
用户："帮我画一只橘猫"
  ↓
① 关键词粗筛（modules/chat/image_intent.py 的 _IMAGE_PATTERNS）
  ↓
② 模型确认一次（YES/NO）
  ↓
③ 跑正常对话，边跑边吐字
  ↓
④ 流末尾追加 [IMAGE:42]
  ↓
前端 MessageBubble 解析标记 → 渲染 GeneratedImage（带下载）
```

**为什么两层判断**：第一层不调模型（省钱），挡掉「我很喜欢画画」这类；
第二层才让模型确认，挡掉第一层的误判。

**关键词用正则不用短语列表**：中文里「画/生成/做」后面能接的量词太多
（一张、一只、一个、一幅……），写死短语一定会漏。踩过这个坑：
只写了「生成一张」，用户说「生成一只柴犬」就完全没反应。

### 出行：主动提议，更像「能力补充」

出行是专做出行的模块，生图不能喧宾夺主。所以不是用户一说就画，而是：

```
路线/攻略有产出了 → Agent 主动问："要不要生成一张路线示意图？"
  ↓ 用户说"要"
才画
```

用户自己明确说「要图片」也会直接画，不用等提议。

**图的内容**：路线画成「信息卡」（起点终点、交通方式、要点），
攻略画成「行程海报」（几天、每天去哪）。
**明确要求不画真实地图** —— 生图模型画不准路网，与其画一张似是而非的地图，不如画信息卡。

### 图存在哪、怎么取

```python
save_generated(content, tenant_id=42)
# → databases/images/42/xxxx.jpg    和用户上传的图同一个目录
```

不复制、不占双份空间。图会登记进 `message_images`，
前端统一走 `GET /chat/attachment/{id}` 取（有租户校验）。

### 前端只有两个文件

- `MessageBubble.vue`：解析 `[IMAGE:id]`，剩下的是正文
- `shared/attachments/GeneratedImage.vue`：显示 + 下载

**界面结构、导航、按钮一律没动。**

## 十、移动端

断点只有一个：**≤ 768px 算手机**。

为什么不按 iPad 尺寸再细分：现在只有「侧栏 + 内容」两栏，768 以上并排放得下，
以下放不下就得收起来。多两个断点只会让维护成本翻倍。

### 侧栏怎么收起

用 `SidebarDrawer.vue` 包住侧栏就够了，三个页面（对话 / 出行 / 角色）都是同一份行为：

```vue
<SidebarDrawer>
  <SessionList />
</SidebarDrawer>
```

- **桌面端**：什么都不做，原样渲染（侧栏常驻）
- **移动端**：变成从左滑出的抽屉，有遮罩，点遮罩或按 ESC 关掉

为什么用组件而不是在每个 `<aside>` 上写 `@media`：
三个页面要同样的行为，包一层之后行为自动一致，加新页面也不用重写。

为什么用 `v-if` 判断而不是纯 CSS：
桌面端如果也渲染遮罩层，会挡住点击。纯 CSS 做不出「桌面端不渲染遮罩」。

**开合状态**在 `shared/lib/drawer.ts`。按钮在顶栏（TopBar），要控制的侧栏在页面里，
两者不在同一个组件树分支上，只能通过共享状态沟通。

### 各页面要自己写的

| 文件 | 加了什么 |
| --- | --- |
| `TopBar.vue` | 汉堡按钮、品牌只留图标、标签禁换行、账号只留头像 |
| `ModeBar.vue` | 横向滚动，藏掉「玩法」前置标签和右侧提示 |
| `ChatComposer.vue` | 输入框字号 16px（小于会被 iOS 放大页面）、按钮 38px |
| `ChatView` / `TripView` / `CustomerView` / `RolePickerView` | 左右留白 24px → 14px，标题字号缩小 |
| `SessionList` / `TripList` | 条目触摸区加大，删除按钮常显（手机没有 hover） |

### 几个容易踩的

1. **文字竖排**：手机上「对话」两个字会被挤成两行竖着排。
   所有标签都要 `white-space: nowrap`。

2. **输入框字号必须 ≥ 16px**：小于 16px 时 iOS 会主动放大整个页面，用户体验很差。

3. **高度用 `dvh` 不用 `vh`**：`vh` 算的是「地址栏收起时的高度」，键盘一弹输入框就被顶出屏幕。
   项目里用 `height: 100%` + `@supports (height: 100dvh)` 兜底，老浏览器忽略后者。

4. **横向溢出**：手机上任何一个元素超出屏幕宽度，整页就能左右拖，很难受。
   全局加了 `overflow-x: hidden`，但更根本的是每个块都要能换行或缩。

5. **安全区**：底部栏和抽屉要用 `env(safe-area-inset-bottom/left)`，
   不然 iPhone 的手势条会盖住按钮。

### 已知没做的

- **B 方案（底部标签栏）** 只留了预览图，没有实现。
  将来真要做成 App 再考虑：`web/design-preview/mobile-plans.html` 里有完整设计。
- **键盘弹出** 的行为只能在真机上验证，桌面浏览器模拟不出来。

---

## 十一、设计稿在哪

`web/design-preview/` 里保留了最终样貌的截图（对话、角色、出行、客服、
登录、多选、反馈、路线/攻略各阶段、移动端）。

- `mobile-plans.html` —— 移动端三套方案的完整设计（A 抽屉 / B 底部栏 / C 独立页）。
  现在实现的是 **A**，B 留给将来做 App 时参考。
- 桌面端截图按功能命名，改新页面时对照着看。

过程中的风格对比图（配色方案、气泡四个变体、改之前的坏样子）已经清理掉，
它们只对当时的决策有意义。
