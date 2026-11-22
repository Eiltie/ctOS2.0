"""项目总启动入口：跑这个文件就把服务拉起来。

    python -X utf8 app.py

默认监听 127.0.0.1:8080，浏览器打开 http://127.0.0.1:8080/ 即可。

想改端口：环境变量 PORT=9000 python app.py
想让同一 WiFi 下的手机也能访问：设 HOST=0.0.0.0
"""

import os

import uvicorn

from api.main import app


def main():
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8080"))

    print(f"ctOS 2.0 启动中…  http://{host}:{port}/")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
