# 文件位置: deploy/run.py
# 功能: 线上发布入口。读取 PORT 环境变量并以 0.0.0.0 绑定，适配单端口沙箱反向代理。
#       本地开发仍可用: python -m uvicorn app.main:app --port 8000
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
