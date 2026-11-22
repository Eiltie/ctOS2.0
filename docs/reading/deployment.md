# 部署说明

> 本地直接跑：装好 Python 和 PostgreSQL，一条命令拉起服务。

---

## 〇、线上实例

项目已上线，**随时可以打开看**：

| 项 | 值 |
| --- | --- |
| 访问地址 | <https://ctos2.cn>（裸域和 `www.ctos2.cn` 都能访问，页面完全一致） |
| 健康检查 | <https://ctos2.cn/health> → `{"ok":true,"database":"ctos2","user":"ctos_app"}` |
| 链路 | 浏览器 → Cloudflare（TLS / CDN）→ 服务器上的 uvicorn 进程（8080）→ PostgreSQL 17 |
| 访问方式 | 打开页面先进访客空间（独立租户，记录只存在当前浏览器），也可注册账号（一人一户，数据按租户隔离），然后即可用四个能力 |

> **HTML 和 SSE 不被缓存**：`cf-cache-status` 是 `DYNAMIC`，流式输出不受影响。
>
> ⚠️ **但 `.js` / `.css` 会被 Cloudflare 缓存 4 小时**（响应头被 CF 覆盖成
> `max-age=14400`，后端设的 `no-cache` 不起作用）。所以改完前端必须跑
> `node scripts/stamp-static.js` 给资源加版本号，否则线上用户要等 4 小时才看到改动。

**线上和本地唯一的区别是域名和 TLS**：应用代码完全一样，
进程监听同一个端口，HTTPS 由 Cloudflare 那一层负责。

**线上体感的前提**：`config/.env` 里的密钥必须有效（DeepSeek / 高德），
且账户有余额。缺密钥或余额不足时，对应模块会返回「这次没跑通」。
客服的向量化跑在 Ollama 上，不占外网、也不需要密钥。

---

## 一、本地运行

### 前提

- Python 3.14
- PostgreSQL 17（装在 `D:\PostgreSQL`）

### 启动

```powershell
# 1. 启动 PostgreSQL
D:\PostgreSQL\pgsql\bin\pg_ctl.exe -D D:\PostgreSQL\data -l D:\PostgreSQL\server.log -o "-p 5432" start

# 2. 建表（第一次，或改了表结构）
cd D:\ctOS2.0
venv\Scripts\python.exe -X utf8 -m common.db

# 3. 启动应用（这条就把服务拉起来了）
venv\Scripts\python.exe -X utf8 -m api.main

# 4. 浏览器打开
# http://127.0.0.1:8080/
```

改 Python 代码重启这一步即可；改前端要 `cd web && npm run build`，产物落到 `static/dist/`。

### 停止

```powershell
# 应用：在运行它的终端按 Ctrl+C
# 数据库：
D:\PostgreSQL\pgsql\bin\pg_ctl.exe -D D:\PostgreSQL\data stop
```

---

## 二、数据存在哪

| 东西 | 位置 |
| --- | --- |
| 业务数据（用户、会话、消息） | PostgreSQL 的数据库 `ctos2` |
| 客服向量库 | `modules/customer/data/chroma/` |
| 人工确认的暂停现场 | `databases/checkpoints/route_checkpoints.sqlite` |
| 前端构建产物 | `static/dist/` |

数据库备份：

```powershell
D:\PostgreSQL\pgsql\bin\pg_dump.exe -U ctos_app -d ctos2 -f backup.sql
# 恢复
D:\PostgreSQL\pgsql\bin\psql.exe -U ctos_app -d ctos2 -f backup.sql
```

---

## 三、环境变量

所有配置只在 `config/.env` **一份**，代码通过 `common/llm.py` 里的 `load_dotenv` 读取。

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | ✅ | 所有对话和推理 |
| `DEEPSEEK_BASE_URL` | ✅ | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | ✅ | 模型名 |
| `SEEDREAM_API_KEY` | ✅ | 生图（火山方舟） |
| `OLLAMA_HOST` | ✅ | 客服向量化，默认 `http://127.0.0.1:11434` |
| `AMAP_KEY` | ✅ | 出行的路线计算；缺了路线决策不可用，攻略流程仍能跑 |
| `JWT_SECRET_KEY` | ✅ | 登录 token 签名密钥（缺了启动就报错，没有默认值） |
| `PG_HOST` / `PG_PORT` / `PG_DBNAME` / `PG_USER` / `PG_PASSWORD` | ✅ | 数据库连接 |
| `HOST` / `PORT` | 可选 | 监听地址，默认 `127.0.0.1:8080` |

> 天气用的是 Open-Meteo，**免密钥**，不需要额外申请。

**生成 JWT 密钥：**

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 四、局域网访问

默认只监听 `127.0.0.1`，本机才能访问。想让同一 WiFi 下其他设备打开：

```powershell
$env:HOST="0.0.0.0"
venv\Scripts\python.exe -X utf8 -m api.main
```

查你的内网 IP：

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -match '^192\.168\.|^10\.' }
```

假设是 `192.168.1.247`，其他设备访问 `http://192.168.1.247:8080/`。

**Windows 防火墙可能要放行 8080 端口。**

---

## 五、常见问题

### 服务起不来

看终端报错。最常见是 `JWT_SECRET_KEY` 没配，或 PostgreSQL 没启动。

### 健康检查失败

```powershell
venv\Scripts\python.exe -c "from common.db import check_connection; print(check_connection())"
```

连不上就是 `config/.env` 里的 `PG_*` 配置不对，或者数据库没起。

### 端口被占用

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen
```

### 改了代码但没生效

- 改的是 **后端**：重启 `python -m api.main` 那个进程
- 改的是 **前端**：`cd web && npm run build`，然后强制刷新（Ctrl+F5）
  - 线上的话还要跑 `node scripts/stamp-static.js` 加版本号，否则 `.js` / `.css` 会被 Cloudflare 缓存 4 小时
- 改的是 **知识库文档**：要重跑入库（见下一条）并重启服务

### 更新客服知识库

知识库文档在 `docs/corpus/*.md`，改了必须重新入库：

```powershell
venv\Scripts\python.exe -X utf8 -m modules.customer.rag_ingest
```

然后重启服务。

### 想重置所有数据

```powershell
venv\Scripts\python.exe -X utf8 -m databases.tools.clean   # 菜单里选清理项
venv\Scripts\python.exe -X utf8 -m common.db                # 重建表
```

---

## 六、上线流程

```powershell
# 1. 本地确认能跑
#    浏览器打开 http://127.0.0.1:8080/ 自测四个模块

# 2. 改完提交
git add -A
git commit -m "..."

# 3. 同步到服务器（git pull 或 rsync，按你的方式）

# 4. 服务器上重启进程，并确认：
curl http://127.0.0.1:8080/health
# 期望：{"ok":true,"database":"ctos2","user":"ctos_app"}

# 5. 第一次上线或改了表结构时：
python -X utf8 -m common.db
python -X utf8 -m modules.customer.rag_ingest   # 只有改了知识库文档才需要
```
