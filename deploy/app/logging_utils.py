# 文件位置: backend/app/logging_utils.py
# 功能: 结构化 JSON 日志 + 请求 ID 上下文。不记录密码、令牌与隐私数据。
from __future__ import annotations

import json
import logging
import sys
import time
from contextvars import ContextVar

# 每个请求一个 request_id，贯穿日志链路
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return request_id_var.get()


def set_request_id(rid: str) -> None:
    request_id_var.set(rid)


class JsonFormatter(logging.Formatter):
    """将日志记录格式化为单行 JSON，便于日志采集。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": get_request_id(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """配置根日志为 JSON 输出，降低第三方库噪声。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
