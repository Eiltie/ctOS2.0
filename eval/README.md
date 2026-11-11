# ctOS 2.0 最小测评

这不是模型排行榜，是一个能重复跑的验收工具。

## 跑一次

```powershell
.\venv\Scripts\python.exe -X utf8 eval\run_eval.py
```

只跑某几条：

```powershell
.\venv\Scripts\python.exe -X utf8 eval\run_eval.py --only role-identity,trip-weather
```

结果会写到 `eval/results/`：

- `xxx.json`：完整明细，包含每道题的回答
- `xxx.md`：一页报告，适合直接看

## 现在覆盖什么

| 模块 | 题数 | 看什么 |
|---|---:|---|
| 普通聊天 | 4 | 有没有正常回答、指令遵循、格式、长度 |
| 角色扮演 | 8 | 人设、边界、6 轮记忆、不同角色、追问 |
| 智能客服 | 10 | 模块、安装、入库、启动、端口、表、检索、库外问题 |
| 智能出行 | 8 | 路线、攻略、老人/小孩、预算、天气 |
| 平台 | 2 | 会话保存/删除、角色会话识别 |

共 32 条。这是整个系统的题量，不是每个模块几十条。

## 怎么打分

自动检查这些：

- `must_have_all`：这些词必须都有
- `must_have_any`：至少命中一个
- `must_have_groups`：每一组至少命中一个
- `must_not`：出现就失败，比如角色承认自己是 AI
- `min_chars` / `max_chars`
- `max_seconds`
- 有没有报错、有没有返回内容

`critical: true` 的题一失败就属于严重失败，比如角色边界、数据保存。

## 加一条题

打开 `eval/cases.json`，按模块加：

```json
{
  "id": "trip-weather",
  "module": "trip",
  "input": "杭州今天天气怎么样？",
  "must_have_all": ["杭州"],
  "must_have_any": ["℃", "°C", "气温", "温度"],
  "must_not": ["查不了"],
  "max_seconds": 60
}
```

角色多轮题用 `role_id` + `turns`；平台题用 `kind: session` 或 `kind: role_session`。

## 目前基线

2026-11-11：

- 32 条全部通过，严重失败 0
- 平均 8.6s，P95 45.5s（P95 主要来自带小孩/带老人的完整攻略）
- 客服检索 40 题：命中@4 100%，命中@1 48%

这些是**硬规则通过率**，不等于“回答一定完美”。语气、行程合理性、有没有编造细节，还需要人工抽样看。

## 已经跑出的一次闭环

第一次跑时，`trip-weather` 失败：

> 杭州今天天气我这边暂时查不了实时数据……

原因：出行模块把它当成了普通闲聊。

修法：在 `modules/trip/stream.py` 里加天气意图，直接走天气节点。

修完后重跑：

> 杭州未来三天……气温 4~18°C……

`trip-weather` 从失败变成通过，当次那套 14 条回到 14/14。

## 下一步

- 每条题支持跑 2~3 次，统计稳定性
- 给角色/行程加 1~5 分的人工评分表
- 把每次失败自动追加成回归题
- 加一条客服“答案有没有引用原文”的检查
