# 文件位置: backend/app/services/alert_engine.py
# 功能: 预警引擎 —— 基于分析引擎的预警列表，提供 SSE 实时推送（连接即推送存量预警 + 心跳保活）。
from __future__ import annotations

import asyncio
import datetime
import json
from typing import AsyncGenerator

from app.analysis.engine import get_engine


async def alert_stream() -> AsyncGenerator[str, None]:
    """SSE 生成器：连接后推送存量预警，随后以心跳保活。"""
    engine = get_engine()
    alerts = engine.get_alerts()
    yield _sse("connected", {"message": "预警通道已建立", "total": len(alerts)})
    # 逐条推送存量预警，模拟实时检测节奏
    for a in alerts:
        yield _sse("alert", a)
        await asyncio.sleep(1.2)
    # 心跳保活
    while True:
        await asyncio.sleep(5)
        yield _sse("heartbeat", {"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
