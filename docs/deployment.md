# 部署说明

> 三种跑法，按需要选。

---

## 一、Docker 部署（推荐）

### 前提

装了 Docker Desktop。检查：

```powershell
docker --version
```

### 启动

> **所有 `docker compose` 命令都要带 `--env-file config/.env`。**
> 配置只有一份，放在 `config/.env`；根目录不再放副本。
> 忘了带会直接报错，并在报错信息里告诉你正确命令。

```powershell
cd D:\ctOS2.0
docker compose --env-file config/.env up -d
```

**它会做这些事：**

1. 启动 `ctos2-db` 容器（PostgreSQL 17）
2. 等数据库健康检查通过
3. 启动 `ctos2-app` 容器（你的应用）
4. 应用连上数据库，监听 8080

### 验证

```powershell
# 看容器状态
docker compose --env-file config/.env ps

# 健康检查
curl http://127.0.0.1:8080/health
# 期望：{"ok":true,"database":"ctos2","user":"ctos_app"}
```

浏览器打开 <http://127.0.0.1:8080/>

### 常用命令

| 命令 | 作用 |
| --- | --- |
| `docker compose --env-file config/.env up -d` | 启动（后台） |
| `docker compose --env-file config/.env ps` | 看状态 |
| `docker compose --env-file config/.env logs -f app` | 跟看应用日志 |
| `docker compose --env-file config/.env logs -f db` | 跟看数据库日志 |
| `docker compose --env-file config/.env restart app` | 只重启应用 |
| `docker compose --env-file config/.env down` | 停止（**数据保留**） |
| `docker compose --env-file config/.env down -v` | 停止并删除数据（⚠️ 慎用） |
| `docker compose --env-file config/.env build` | 改代码后重新构建 |

### 改代码后怎么生效

```powershell
docker compose --env-file config/.env build
docker compose --env-file config/.env up -d
```

### 第一次部署时要建表

```powershell
docker exec ctos2-app python -m core.db
```

---

## 二、容器结构和端口

```
┌────────────────────────────────────────┐
│  宿主机（你的电脑）                     │
│                                        │
│  浏览器 ──→ localhost:8080             │
│                  │                     │
│           ┌──────▼──────┐              │
│           │ ctos2-app   │              │
│           │ 端口 8080   │              │
│           └──────┬──────┘              │
│                  │ 内部网络 ctos2-net   │
│           ┌──────▼──────┐              │
│           │ ctos2-db    │              │
│           │ 端口 5432   │              │
│           └─────────────┘              │
│                  │                     │
│        localhost:5433（外部可访问）      │
└────────────────────────────────────────┘
```

**为什么数据库映射到 5433 而不是 5432：**

你电脑上可能已经装了 PostgreSQL（用 5432），映射到 5433 避免冲突。

**应用连数据库用的是容器名 `db`，不是 127.0.0.1。** 这是 Docker 的 DNS，容器之间用服务名互相访问。

---

## 三、数据存在哪

| 数据 | 位置 | 说明 |
| --- | --- | --- |
| PostgreSQL 数据 | Docker 卷 `ctos2-pgdata` | 删容器不丢 |
| Chroma 向量库 | `./modules/customer/data/chroma`（挂载） | 改文档后要重跑入库 |
| 代码 | 镜像里 | 改代码要 `docker compose build` |

**查看卷在哪：**

```powershell
docker volume inspect ctos2-pgdata
```

**备份数据库：**

```powershell
docker exec ctos2-db pg_dump -U ctos_app ctos2 > backup.sql
```

**恢复：**

```powershell
docker exec -i ctos2-db psql -U ctos_app ctos2 < backup.sql
```

---

## 四、本地开发（不用 Docker）

**适合改代码时用，改完刷新就生效（Docker 要重新 build）。**

### 前提

- Python 3.14
- PostgreSQL 17（装在 `D:\PostgreSQL`）

### 启动

```powershell
# 1. 启动 PostgreSQL
D:\PostgreSQL\pgsql\bin\pg_ctl.exe -D D:\PostgreSQL\data -l D:\PostgreSQL\server.log -o "-p 5432" start

# 2. 建表（第一次）
cd D:\ctOS2.0
venv\Scripts\python.exe -X utf8 -m core.db

# 3. 启动应用
venv\Scripts\python.exe -X utf8 -m api.main
```

### 停止

```powershell
D:\PostgreSQL\pgsql\bin\pg_ctl.exe -D D:\PostgreSQL\data stop
```

### 重要：本地和 Docker 不能同时跑

两者都占 8080 端口，**同时只能跑一个**。

---

## 五、环境变量

所有配置只在 `config/.env` **一份**。代码和 Docker 都读它——Docker 通过 `--env-file config/.env` 指定，代码通过 `core/llm.py` 里的 `load_dotenv` 读取。

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | ✅ | 所有对话和推理 |
| `DEEPSEEK_BASE_URL` | ✅ | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | ✅ | 模型名 |
| `ZHIPU_API_KEY` | ✅ | 客服的向量化 |
| `AMAP_KEY` | 建议 | 出行的路线计算（缺失时退化为估算） |
| `JWT_SECRET_KEY` | ✅ | 登录 token 签名密钥 |
| `PG_HOST` / `PG_PORT` / `PG_DBNAME` / `PG_USER` / `PG_PASSWORD` | ✅ | 数据库连接 |
| `HOST` / `PORT` | 可选 | 监听地址，默认 `127.0.0.1:8080`；Docker 里设 `0.0.0.0` |

**生成 JWT 密钥：**

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 六、局域网访问

Docker 默认监听 `0.0.0.0`，**同一 WiFi 下其他设备可以直接访问**。

查你的内网 IP：

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -match '^192\.168\.|^10\.' }
```

假设是 `192.168.1.247`，其他设备访问：

```
http://192.168.1.247:8080/
```

**Windows 防火墙可能要放行 8080 端口。**

---

## 七、常见问题

### 容器起不来

```powershell
docker compose --env-file config/.env logs app
```

### 健康检查失败

```powershell
# 看是不是连不上数据库
docker exec ctos2-app python -c "from core.db import check_connection; print(check_connection())"
```

### 端口被占用

```powershell
# 查谁占了 8080
Get-NetTCPConnection -LocalPort 8080 -State Listen
```

### 改了代码但没生效

Docker 里代码是打包进镜像的，**改完必须重新构建**：

```powershell
docker compose --env-file config/.env build
docker compose --env-file config/.env up -d
```

### 想重置所有数据

```powershell
docker compose --env-file config/.env down -v      # ⚠️ 删数据卷
docker compose --env-file config/.env up -d
docker exec ctos2-app python -m core.db
```

---

## 八、构建镜像的耗时说明

| 步骤 | 耗时 | 说明 |
| --- | --- | --- |
| 拉基础镜像 | 首次约 4 分钟 | 有缓存后 1 秒 |
| 装 apt 包 | 约 2 分钟 | libpq5 + curl |
| pip 装依赖 | 约 6 分钟 | 走阿里云源 |
| 拷代码 | 几秒 | — |
| **首次总计** | **约 8 分钟** | — |
| **改代码后重建** | **约 20 秒** | 依赖层命中缓存 |

**为什么用阿里云 pip 源：** 走 PyPI 官方源在国内要几十分钟。
