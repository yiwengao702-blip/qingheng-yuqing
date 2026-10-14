# 文件位置: backend/app/api/sse.py
# 功能: SSE 实时预警端点。鉴权后建立事件流，持续推送预警与心跳。
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.security import require_permissions
from app.services.alert_engine import alert_stream

router = APIRouter()


@router.get("/stream/alerts")
async def stream_alerts(_user=Depends(require_permissions("alert:receive"))):
    """实时风险预警 SSE 流（text/event-stream）。"""
    return StreamingResponse(
        alert_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
