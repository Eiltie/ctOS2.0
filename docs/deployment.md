# 部署说明

> 三种跑法，按需要选。

---

## 〇、线上实例

项目已上线，**随时可以打开看**：

| 项 | 值 |
| --- | --- |
| 访问地址 | <https://ctos2.cn>（裸域和 `www.ctos2.cn` 都能访问，页面完全一致） |
| 健康检查 | <https://ctos2.cn/health> → `{"ok":true,"database":"ctos2","user":"ctos_app"}` |
| 链路 | 浏览器 → Cloudflare（TLS / CDN）→ 服务器上的 `ctos2-app` 容器（8080）→ `ctos2-db` 容器（PostgreSQL 17） |
| 访问方式 | 进入页面先注册账号（一人一户，数据按租户隔离），然后即可用三个模块 |

> Cloudflare 默认**不缓存** HTML/SSE，`cf-cache-status` 是 `DYNAMIC`，流式输出不受影响。

**线上和本地唯一的区别是域名和 TLS**：应用代码、Dockerfile、Compose 文件都完全一样，
容器内部仍然监听 `0.0.0.0:8080`，HTTPS 由 Cloudflare 那一层负责。

**线上体感的前提**：服务器上 `config/.env` 里的密钥必须有效（DeepSeek / 智谱 / 高德），
且账户有余额。缺密钥或余额不足时，对应模块会返回「这次没跑通」。

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

### 线上打不开 / 打开是旧页面

1. 先访问 <https://ctos2.cn/health>：有 `{"ok":true,...}` 说明应用本身活着，问题在域名或 CDN 层
2. 没响应就看服务器上容器状态：`docker compose --env-file config/.env ps`
3. Cloudflare 里确认 `ctos2.cn` 和 `www.ctos2.cn` 两条 DNS 记录都在，并且是**已代理**（橙云）
4. 改了代码上线后看到的还是旧页面，先强制刷新（Ctrl+F5）；HTML 不被 CDN 缓存，一般刷新即可

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

---

## 九、上线流程（线上 www.ctos2.cn 就是这样上线的）

代码和配置都在本地改，**上线只做一件事：把改动同步到服务器再重建容器**。

```powershell
# 1. 本地确认能跑（可选，但推荐）
docker compose --env-file config/.env up -d
#    浏览器打开 http://127.0.0.1:8080/ 自测三个模块

# 2. 改完提交
git add -A
git commit -m "说明改了什么"

# 3. 把代码同步到服务器（按你的实际方式二选一）
#    git 方式：服务器上 git pull
#    镜像方式：本地 docker compose build 后，把镜像推到仓库再在服务器 pull
#    （.dockerignore 保证 venv/、config/.env、向量库、数据库文件都不会进镜像）

# 4. 服务器上重建并重启
docker compose --env-file config/.env build
docker compose --env-file config/.env up -d

# 5. 验证
curl https://ctos2.cn/health
# 期望：{"ok":true,"database":"ctos2","user":"ctos_app"}
```

**上线前必须检查的三件事：**

| 检查 | 为什么 |
| --- | --- |
| 服务器上的 `config/.env` 是最新的 | 密钥只在服务器上有一份，本地改了不会自动同步过去 |
| 服务器上的 `modules/customer/data/chroma/` 存在 | 向量库是目录挂载，**不进镜像**，服务器第一次部署必须先跑一次入库脚本 |
| 服务器上跑过 `python -m core.db` | 建表是一次性的，没建表的话注册登录会直接报错 |

**线上第一次部署的完整步骤：**

```bash
# 1. 拉代码到服务器
git clone <仓库地址> && cd ctOS2.0

# 2. 准备配置
cp config/YOUR_config.env config/.env    # 填好密钥

# 3. 起容器
docker compose --env-file config/.env up -d

# 4. 建表（一次性）
docker exec ctos2-app python -m core.db

# 5. 知识库入库（一次性，结果落进挂载的 chroma 目录）
docker exec ctos2-app python -m modules.customer.rag_ingest

# 6. 验证
curl http://127.0.0.1:8080/health
```

**域名和 TLS**：在域名商处把 `ctos2.cn` 和 `www.ctos2.cn` 都指向服务器 IP，
这两条记录都在 Cloudflare 里托管（走代理），HTTPS 证书由 Cloudflare 自动签发和续期，
应用本身**不需要**配任何证书或反向代理。

**改知识库要重新入库**：线上改了 `modules/customer/data/docs/*.md` 之后，
必须重跑 `docker exec ctos2-app python -m modules.customer.rag_ingest` 并**重启应用容器**，
否则客服读到的还是内存里的旧知识库。
