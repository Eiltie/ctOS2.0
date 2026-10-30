# ctOS 2.0 的 Docker 镜像
#
# 构建：docker build -t ctos2 .
# 运行：docker run -p 8080:8080 --env-file config/.env ctos2
#
# 设计要点：
#   1. python:3.14-slim 本身带 openssl、decimal 等，大多依赖不用额外编译
#   2. 只装两个必需的运行时库：libpq5（psycopg 连 PostgreSQL）+ curl（健康检查）
#   3. pip 用阿里云源，国内装包从几十分钟降到几分钟
#   4. 先装依赖再拷代码，改代码时不用重装依赖
#   5. 非 root 运行

FROM python:3.14-slim

# 只装运行时需要的系统库，不装 gcc（chromadb 1.5.9 用 Rust 预编译包，不需要编译）
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 容器里必须监听 0.0.0.0，否则 Docker 端口映射转发不进来
# （本机开发默认是 127.0.0.1，只有自己访问）
ENV HOST=0.0.0.0
ENV PORT=8080

# pip 源：阿里云
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
    && pip config set global.trusted-host mirrors.aliyun.com \
    && pip config set global.timeout 120 \
    && pip config set global.retries 5

WORKDIR /app

# 先装依赖（利用层缓存）
COPY config/requirements.txt /app/config/requirements.txt
RUN pip install --no-cache-dir -r /app/config/requirements.txt

# 再拷代码
COPY core/ /app/core/
COPY databases/ /app/databases/
COPY modules/ /app/modules/
COPY api/ /app/api/
COPY static/ /app/static/

# 非 root 用户
RUN useradd -m -u 1000 ctos && chown -R ctos:ctos /app
USER ctos

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://127.0.0.1:8080/health || exit 1

CMD ["python", "-m", "api.main"]
