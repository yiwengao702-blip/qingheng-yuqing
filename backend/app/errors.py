# 文件位置: backend/app/errors.py
# 功能: 类型化错误体系 + 全局异常处理。客户端只看到规范化错误结构，绝不返回堆栈。
from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.logging_utils import get_request_id

logger = logging.getLogger("yuqing")


class AppError(Exception):
    """业务错误基类：携带 machine-readable 错误码、用户可读信息、HTTP 状态码。"""

    def __init__(self, code: str, message: str, status_code: int = 400, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class ValidationError(AppError):
    def __init__(self, message: str = "请求参数校验失败", details: Any = None):
        super().__init__("VALIDATION_ERROR", message, 422, details)


class NotFoundError(AppError):
    def __init__(self, message: str = "资源不存在", details: Any = None):
        super().__init__("NOT_FOUND", message, 404, details)


class AuthError(AppError):
    def __init__(self, message: str = "未认证或令牌无效", details: Any = None):
        super().__init__("UNAUTHORIZED", message, 401, details)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "权限不足，无法执行该操作", details: Any = None):
        super().__init__("FORBIDDEN", message, 403, details)


class ConflictError(AppError):
    def __init__(self, message: str = "资源状态冲突", details: Any = None):
        super().__init__("CONFLICT", message, 409, details)


def _error_body(code: str, message: str, request_id: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id, "details": details}}


def register_exception_handlers(app) -> None:
    """注册全局异常处理器（FastAPI 应用工厂调用）。"""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        logger.warning("业务错误 [%s] %s rid=%s", exc.code, exc.message, get_request_id())
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, get_request_id(), exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(request: Request, exc: RequestValidationError):
        # FastAPI 默认把校验错误返回成 {"detail":[...]}，与前端约定的 {"error":{...}} 不一致，
        # 会导致页面只显示泛化文案。这里统一成标准错误结构，并附上字段级中文说明。
        msgs = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", []) if x not in ("body", "query", "path"))
            msg = err.get("msg", "参数不合法")
            msgs.append(f"{loc}: {msg}" if loc else msg)
        detail = "；".join(msgs) or "请求参数校验失败"
        logger.warning("参数校验失败 [%s] rid=%s", detail, get_request_id())
        return JSONResponse(
            status_code=422,
            content=_error_body("VALIDATION_ERROR", f"请求参数校验失败：{detail}", get_request_id()),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        logger.exception("未捕获异常 rid=%s", get_request_id())
        return JSONResponse(
            status_code=500,
            content=_error_body("INTERNAL_ERROR", "服务器内部错误，请稍后重试", get_request_id()),
        )
