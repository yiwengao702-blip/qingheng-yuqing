# 文件位置: backend/app/main.py
# 功能: FastAPI 应用工厂。装配中间件（请求 ID / CORS / 安全头）、静态前端、路由、
#       全局异常处理、健康检查与优雅停机。启动时校验配置并预热分析引擎。
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.analysis.engine import get_engine
from app.api.routes import router
from app.config import settings
from app.errors import register_exception_handlers
from app.logging_utils import set_request_id, setup_logging

# 启动即初始化日志
setup_logging()
logger = logging.getLogger("yuqing")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期（替代已弃用的 @app.on_event）。

    启动阶段：校验配置 + 预热分析引擎（一次性计算全部派生指标）；
    yield 之后的停机阶段：当前无持久连接需要清理，预留扩展位。
    """
    settings.validate()
    get_engine()
    logger.info("分析引擎预热完成，服务就绪")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

    # 请求 ID 中间件
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        set_request_id(rid)
        resp = await call_next(request)
        resp.headers["X-Request-ID"] = rid
        return resp

    # CORS（显式来源，生产禁用通配符）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 安全头 + 静态资源缓存策略
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        # 前端 JS/CSS 属于高频迭代资源：强制浏览器每次回源校验，
        # 避免迭代修复后浏览器仍执行旧缓存代码（登录 401 死循环即由此引起）。
        p = request.url.path
        if p.startswith(("/js/", "/css/", "/vendor/")):
            resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        # HTML 入口（/ 与 *.html）：完全不缓存。入口里带资源版本号，
        # 若入口本身被缓存，版本号就失去意义，用户会一直看到旧页面。
        if p == "/" or p.endswith(".html"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # 全局异常处理
    register_exception_handlers(app)

    # 路由（统一前缀 /api）
    app.include_router(router, prefix="/api")

    # 静态前端（态势大屏 / 研判工作台 / 报告中心 / 监测配置）
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


app = create_app()
