# 生图 Agent（modules/imagegen）

一张能独立跑完的图：**START → plan →（ask 或 generate）→ END**

不接前端、不接闲聊和出行。命令行就能用。

---

## 一、它解决什么

用户说「画一只橘猫在窗台上」，它出一张图。
用户只说「帮我画个图」，它**先停下来问**，问清楚了再画——这一步是「图」和「调一次 API」的分界线。

---

## 二、图长什么样

```
START
  ↓
plan ──把需求拆成结构化规格，判断信息够不够
  │
  ├─ 不够 且 没问过 → ask ──中断，问用户──┐
  │                          ↑              │
  │                          └── 用户回答 ──┘（回到 plan 重新判断）
  │
  └─ 够 或 问过了 → generate ──拼提示词 → 调 Seedream → 存图 → END
```

**三条边：**

| 从 | 到 | 条件 |
|---|---|---|
| START | plan | — |
| plan | ask | `status == need_more` 且 `asked_once == False` |
| plan | generate | 其他情况 |
| ask | plan | 用户回答后 |
| generate | END | — |

**为什么 ask 回的是 plan 而不是 generate**：用户回答「一只猫」之后，还需要模型把这句话补成完整规格（风格、比例、光线）。回 plan 让规格处理只有一处，不用在 ask 里再写一套解析。

---

## 三、两个工具

### `build_prompt(spec)` — 规格 → 提示词

把结构化字段拼成一段中文，按「主体 → 动作 → 场景 → 风格 → 光线 → 图内文字 → 不要出现」的顺序。

两个细节：
- **去重**：拆规格时模型常把「坐在窗台上」和「窗台」都填上，直接拼会得到冗余。后面一段如果已被前面包含，就跳过。
- **卡长度**：软上限 600 字（接口硬上限 1000），超了从尾部砍——负向词最先砍，主体永远保留。

### `call_seedream(prompt, size)` — 调用生图接口

- 端点：`https://ark.cn-beijing.volces.com/api/v3/images/generations`
- **模型名必须带日期后缀**：`doubao-seedream-5-0-flash-260915`
  （不带后缀会报 `InvalidEndpointOrModel.NotFound`，实测踩过）
- 接口返回的是**临时 URL**，拿到必须立刻下载。存 URL 过一会儿就 404
- 失败返回 `(None, 原因)`，**不抛异常**——抛异常用户只会看到 500

---

## 四、结构化规格

不是一段提示词，是一份可读可改的字段：

```python
{
    "subject": "一只橘猫",      # 主体（唯一硬要求）
    "action": "坐在窗台上",      # 动作
    "scene": "室内",           # 场景
    "style": "水彩",           # 风格
    "lighting": "清晨柔光",      # 光线
    "aspect": "1:1",           # 比例
    "text_in_image": "",       # 图内文字
    "negative": "模糊, 低质量",   # 不想要的东西
}
```

**为什么结构化**：用户能看、能改；迭代时只改字段，不用重写整段话。

---

## 五、状态

```python
class ImageState(TypedDict):
    user_query: str
    history: list
    tenant_id: int

    spec: ImageSpec
    final_prompt: str
    size: str
    missing: list

    asked_once: bool     # ← 关键：防止反复追问
    answer: str

    image_path: str      # 绝对路径
    image_url: str       # generated/xxx.jpg
    status: str          # ok / need_more / api_failed / prompt_failed
    problem: str
```

**`asked_once` 为什么必须有**：需求不足时停下来问一次，问过还不足就直接按随机主题画。没有这个字段，用户回一句「随便」，plan 又觉得不够，又跳 ask，**死循环**。

---

## 六、怎么用

### 命令行

```powershell
# 交互式
.\venv\Scripts\python.exe -m modules.imagegen.cli

# 一句话
.\venv\Scripts\python.exe -m modules.imagegen.cli "画一只橘猫在窗台上"
```

### 代码里

```python
from modules.imagegen.stream import run_graph, resume_image

result = run_graph("画一只橘猫在窗台上")
if result["status"] == "ok":
    print(result["image_path"])

# 需求不够，图会停住
result = run_graph("帮我画个图")
if result["status"] == "need_more":
    print(result["question"])          # 你想画点什么…
    result = resume_image(result["thread_id"], "一只猫在看雪")
```

### 返回形状

```python
{
    "status": "ok" | "need_more" | "api_failed" | "prompt_failed",
    "thread_id": "image-xxx",
    "question": "想画点什么…",      # need_more 时
    "image_path": "E:\...\xxx.jpg",
    "image_url": "generated/xxx.jpg",
    "spec": {...},
    "prompt": "实际发出去的提示词",
    "size": "1536x1536",
    "problem": "",               # 失败原因
}
```

---

## 七、配置

`.env`：

```env
SEEDREAM_API_KEY=ark-xxxxxxxx
# 下面两个可不填，代码里有默认值
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_IMAGE_MODEL=doubao-seedream-5-0-flash-260915
```

**Key 没配时**，`call_seedream` 返回「没配置生图 Key（SEEDREAM_API_KEY）」，不会崩。

**模型名要写对**。查账号里有哪些模型：

```python
import httpx, os
from dotenv import load_dotenv
load_dotenv(".env")
r = httpx.get("https://ark.cn-beijing.volces.com/api/v3/models",
              headers={"Authorization": f"Bearer {os.getenv('SEEDREAM_API_KEY')}"})
for m in r.json()["data"]:
    if m.get("domain") == "ImageGeneration":
        print(m["id"])
```

---

## 八、实测数据

| 项 | 值 |
|---|---|
| 生图耗时 | 10~12 秒 |
| 输出 | 1536×1536 JPG，约 600 KB |
| 价格 | 0.12 元/张（Seedream 5.0 Flash，全档同价） |
| 免费额度 | 实测调用没扣费，具体额度看控制台 |

**已验证的场景：**

- 需求明确 → 直接出图
- 只说「帮我画个图」→ 停下来问；回答后出图
- 回答「随便吧」→ 走随机主题出图，**不反复追问**
- 空输入 → 停下来问，不崩
- 没配 Key → 明确报错，不崩

---

## 九、没做的部分

按约定，这一版**只做独立图**，下面都没做：

| 项 | 说明 |
|---|---|
| 闲聊联动 | 闲聊里说「画个图」目前不会触发它 |
| 出行联动 | `trip/agent.py` 的 action 里还没有 `image` |
| 前端 | 没有界面入口，只能命令行 |
| 限额 | 没有「每人每天几张」的限制 |
| 改图迭代 | 用户说「改一下」不会重画 |
| 数据库 | 生图记录只存文件，没记 `image_generations` 表 |

**下一版接联动时**，只需在调用方 import `run_graph`，把 `need_more` 的 `thread_id` 存下来，用户回答时调 `resume_image`。
