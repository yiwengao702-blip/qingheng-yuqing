# 文件位置: backend/app/api/routes.py
# 功能: REST 路由聚合。控制器层只做「解析请求 -> 调用服务/引擎 -> 格式化响应」，不含业务逻辑。
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.analysis.engine import get_engine
from app.analysis.report import export_html, export_markdown, export_pdf
from app.config import settings
from app.data.load_dataset import get_store
from app.data.multimodal import parse_multimodal_item
from app.errors import AuthError, NotFoundError, ValidationError, PermissionDeniedError
from app.models import (DisposalUpdate, LoginRequest, NotificationChannels,
                      RegisterRequest, ResponseDraftRequest, SourceChannelUpdate,
                      ThresholdRules, TopicPack)
from app.security import create_access_token, get_current_user, require_permissions, REVOKED_TOKENS
from app.online_registry import ONLINE_ACCOUNTS, PERMANENT_USERS, register as _register_online, mark_permanent, unmark_permanent
from app.services.monitoring import get_monitoring
from app.services.users import get_users
from app.api.sse import router as sse_router

router = APIRouter()
router.include_router(sse_router)

# 在线登录账号登记表已迁移至 online_registry.py（登录/注册时登记；
# 令牌校验时对重启后失登记的账号惰性补登记），此处按原名导入复用。


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------
@router.post("/auth/login")
async def login(req: LoginRequest):
    user = get_users().authenticate(req.username, req.password)
    if not user:
        raise AuthError("用户名或密码错误")
    token = create_access_token(
        user["username"], user["role"], user["name"], user["permissions"]
    )
    _register_online(user["username"], user["role"], user["name"], token, permanent=True)
    mark_permanent(user["username"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["username"], "name": user["name"],
            "role": user["role"], "permissions": user["permissions"],
        },
    }


@router.post("/auth/register")
async def register(req: RegisterRequest):
    """页面注册：创建账号并直接签发令牌（注册即登录），返回结构与登录一致。"""
    try:
        user = get_users().create(req.username, req.password, req.role, req.name)
    except ValueError as exc:
        raise ValidationError(str(exc))
    token = create_access_token(
        user["username"], user["role"], user["name"], user["permissions"]
    )
    _register_online(user["username"], user["role"], user["name"], token, permanent=True)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["username"], "name": user["name"],
            "role": user["role"], "permissions": user["permissions"],
        },
    }


@router.get("/auth/me")
async def auth_me(user=Depends(get_current_user)):
    # 规范化返回，与登录/注册的 user 字段保持一致（JWT 载荷里用户名为 sub）
    return {
        "username": user.get("sub"),
        "name": user.get("name"),
        "role": user.get("role"),
        "permissions": user.get("permissions", []),
    }


@router.post("/auth/logout")
async def logout(user=Depends(get_current_user)):
    """登出：移除在线账号登记（进程内存，服务重启即清空）。"""
    ONLINE_ACCOUNTS.pop(user.get("sub"), None)
    return {"ok": True}


@router.get("/auth/online-accounts")
async def online_accounts(user=Depends(get_current_user)):
    """仅管理员可查看当前在线登录账号列表。"""
    if user.get("role") != "admin":
        raise PermissionDeniedError("仅管理员可查看在线账号")
    return {"accounts": list(ONLINE_ACCOUNTS.values())}


@router.get("/auth/all-users")
async def all_users(user=Depends(get_current_user)):
    """管理员查看系统中所有已注册用户（含在线/离线状态）。在线状态取自内存登记表；
    永久账号（注册账号 / 演示种子）即使离线也显示「—」表示不过期。"""
    if user.get("role") != "admin":
        raise PermissionDeniedError("仅管理员可查看用户列表")
    # 在线集合：便于 O(1) 查
    online_set = set(ONLINE_ACCOUNTS.keys())
    users = []
    for u in get_users()._users.values():
        is_online = u["username"] in online_set
        rec = ONLINE_ACCOUNTS.get(u["username"], {})
        # 永久账号（包括离线）统一显示 "—"，非永久账号才显示真实有效期
        expire_at = rec.get("expire_at")
        if expire_at is None and u["username"] in PERMANENT_USERS:
            expire_at = "—"
        # 任何已注册用户（包括离线）都显示 "—"，因为注册账号不过期
        if expire_at is None:
            expire_at = "—"
        users.append({
            "username": u["username"],
            "name": u["name"],
            "role": u["role"],
            "online": is_online,
            "login_at": rec.get("login_at"),
            "expire_at": expire_at,
        })
    # 按在线优先排序（在线在前），其次按注册顺序
    users.sort(key=lambda x: (not x["online"], x["username"]))
    return {"users": users}


@router.post("/auth/online-accounts/{username}/revoke")
async def revoke_online(username: str, user=Depends(get_current_user)):
    """管理员踢出某在线账号：移除登记并吊销其当前令牌（下次请求即 401）。"""
    if user.get("role") != "admin":
        raise PermissionDeniedError("仅管理员可操作")
    rec = ONLINE_ACCOUNTS.pop(username, None)
    if rec and rec.get("token"):
        REVOKED_TOKENS.add(rec["token"])
    # 永久账号被删除后也移出永久名单（管理员明确删除的账号不应再自动恢复为永久）
    unmark_permanent(username)
    return {"ok": True, "removed": rec is not None}


@router.post("/auth/online-accounts/{username}/extend")
async def extend_online(username: str, user=Depends(get_current_user)):
    """管理员为某账号加时：
    - 在线账号：在当前有效期上追加 30 天；
    - 离线账号：重新登记为「当前 +30 天」并标为在线（相当于手动踢回登录状态）。
    """
    if user.get("role") != "admin":
        raise PermissionDeniedError("仅管理员可操作")
    now = datetime.now()
    rec = ONLINE_ACCOUNTS.get(username)
    if rec:
        # 在线账号：在原 expire_at 基础上 +30 天
        try:
            base = datetime.fromisoformat(str(rec.get("expire_at")))
        except (ValueError, TypeError):
            base = None
        if base is None or base <= now:
            base = now
        rec["expire_at"] = (base + timedelta(days=30)).isoformat(timespec="seconds")
        rec["login_at"] = now.isoformat(timespec="seconds")
        return {"ok": True, "expire_at": rec["expire_at"], "online": True}
    # 离线账号：重新登记为在线（30 天有效期）
    u_data = get_users()._users.get(username)
    if not u_data:
        raise NotFoundError("该账号不存在")
    _register_online(username, u_data["role"], u_data["name"],
                     create_access_token(username, u_data["role"], u_data["name"], []),
                     login_at=now, expire_at=now + timedelta(days=30), permanent=True)
    mark_permanent(username)
    return {"ok": True, "expire_at": (now + timedelta(days=30)).isoformat(timespec="seconds"), "online": True}


@router.post("/auth/users/{username}")
async def delete_user(username: str, user=Depends(get_current_user)):
    """管理员删除任意注册用户（在线则同时吊销令牌并移除在线状态）。"""
    if user.get("role") != "admin":
        raise PermissionDeniedError("仅管理员可操作")
    # 1) 移出在线表 + 吊销令牌
    rec = ONLINE_ACCOUNTS.pop(username, None)
    if rec and rec.get("token"):
        REVOKED_TOKENS.add(rec["token"])
    unmark_permanent(username)
    # 2) 从用户库删除
    deleted = get_users().delete(username)
    return {"ok": deleted}


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------
@router.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "time": datetime.now().isoformat()}


@router.get("/ready")
async def ready():
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# 态势总览
# ---------------------------------------------------------------------------
@router.get("/overview")
async def overview(_u=Depends(require_permissions("feed:view"))):
    return get_engine().overview()


@router.get("/events")
async def events(_u=Depends(require_permissions("event:view"))):
    return {"events": get_engine().event_list()}


@router.get("/events/{event_id}")
async def event_detail(event_id: str, _u=Depends(require_permissions("event:view"))):
    d = get_engine().event_detail(event_id)
    if not d:
        raise NotFoundError(f"事件不存在: {event_id}")
    return d


@router.get("/feed")
async def feed(
    event_id: Optional[str] = None,
    source_types: Optional[List[str]] = Query(None),
    sentiments: Optional[List[str]] = Query(None),
    risk_grades: Optional[List[str]] = Query(None),
    q: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _u=Depends(require_permissions("feed:view")),
):
    return get_engine().feed(
        event_id=event_id, source_types=source_types, sentiments=sentiments,
        risk_grades=risk_grades, q=q, time_from=time_from, time_to=time_to,
        page=page, page_size=page_size,
    )


@router.get("/alerts")
async def alerts(_u=Depends(require_permissions("alert:receive"))):
    al = get_engine().get_alerts()
    return {"alerts": al, "total": len(al)}


# ---------------------------------------------------------------------------
# 监测配置
# ---------------------------------------------------------------------------
@router.get("/config")
async def get_config(_u=Depends(require_permissions("feed:view"))):
    return get_monitoring().get_state()


@router.put("/config/topics")
async def put_topics(topics: List[TopicPack], _u=Depends(require_permissions("topic:manage"))):
    for t in topics:
        get_monitoring().upsert_topic(t.dict())
    return {"ok": True, "topic_packs": get_monitoring().get_state()["topic_packs"]}


@router.post("/config/topics")
async def post_topic(topic: TopicPack, _u=Depends(require_permissions("topic:manage"))):
    get_monitoring().upsert_topic(topic.dict())
    return {"ok": True, "topic": topic}


@router.delete("/config/topics/{topic_id}")
async def delete_topic(topic_id: str, _u=Depends(require_permissions("topic:manage"))):
    get_monitoring().delete_topic(topic_id)
    return {"ok": True}


@router.put("/config/sources")
async def put_sources(updates: List[SourceChannelUpdate],
                      _u=Depends(require_permissions("source:config"))):
    get_monitoring().update_sources([u.dict() for u in updates])
    return {"ok": True, "source_channels": get_monitoring().get_state()["source_channels"]}


@router.put("/config/thresholds")
async def put_thresholds(rules: ThresholdRules, _u=Depends(require_permissions("threshold:config"))):
    get_monitoring().update_thresholds(rules.dict())
    return {"ok": True, "threshold_rules": get_monitoring().get_state()["threshold_rules"]}


@router.put("/config/notifications")
async def put_notifications(channels: NotificationChannels,
                           _u=Depends(require_permissions("notification:config"))):
    get_monitoring().update_notifications(channels.channels)
    return {"ok": True, "notification_channels": get_monitoring().get_state()["notification_channels"]}


# ---------------------------------------------------------------------------
# 处置协同
# ---------------------------------------------------------------------------
@router.get("/events/{event_id}/disposal")
async def get_disposal(event_id: str, _u=Depends(require_permissions("event:view"))):
    if not get_store().get_event(event_id):
        raise NotFoundError(f"事件不存在: {event_id}")
    return get_monitoring().get_disposal(event_id)


@router.put("/events/{event_id}/disposal")
async def put_disposal(event_id: str, body: DisposalUpdate,
                       _u=Depends(require_permissions("ticket:route"))):
    if not get_store().get_event(event_id):
        raise NotFoundError(f"事件不存在: {event_id}")
    rec = get_monitoring().update_disposal(event_id, body.status, body.note, body.handler)
    return {"ok": True, "disposal": rec}


@router.post("/events/{event_id}/response-draft")
async def response_draft(event_id: str, body: Optional[ResponseDraftRequest] = None,
                         _u=Depends(require_permissions("pr:adopt"))):
    if not get_store().get_event(event_id):
        raise NotFoundError(f"事件不存在: {event_id}")
    report = get_engine().build_report(event_id)
    pr = {
        "category": report["pr_category"],
        "demand": report["pr_demand"],
        "strategy": report["pr_strategy"],
        "draft": report["pr_draft"],
    }
    get_monitoring().set_response_draft(event_id, pr)
    return {"ok": True, "draft": pr}


# ---------------------------------------------------------------------------
# 报告中心
# ---------------------------------------------------------------------------
@router.get("/reports")
async def reports_list(_u=Depends(require_permissions("report:generate"))):
    engine = get_engine()
    mon = get_monitoring()
    items = []
    for e in engine.event_list():
        draft = mon.get_response_draft(e["event_id"])
        items.append({
            "id": e["event_id"],
            "type": "event",
            "title": f"突发事件专项报告 · {e['title']}",
            "event_id": e["event_id"],
            "grade": e["grade"],
            "generated": draft is not None,
            "generated_at": draft.get("generated_at") if draft else None,
        })
    items.append({"id": "periodic_daily", "type": "periodic", "title": "舆情日报（每日 09:00）",
                  "event_id": None, "grade": None, "generated": True,
                  "generated_at": datetime.now().strftime("%Y-%m-%d")})
    items.append({"id": "periodic_weekly", "type": "periodic", "title": "舆情周报（每周一）",
                  "event_id": None, "grade": None, "generated": True, "generated_at": "本周"})
    return {"reports": items}


@router.post("/reports/generate")
async def generate_report(body: dict, _u=Depends(require_permissions("report:generate"))):
    event_id = body.get("event_id")
    if not event_id or not get_store().get_event(event_id):
        raise ValidationError("缺少有效 event_id")
    report = get_engine().build_report(event_id)
    return {"ok": True, "report": report}


@router.get("/reports/periodic/{kind}")
async def periodic_report(kind: str, _u=Depends(require_permissions("report:generate"))):
    """周期简报（日报 / 周报）：自动汇总全网态势、重点事件排行与预警进展。"""
    if kind not in ("daily", "weekly"):
        raise ValidationError("简报类型仅支持 daily / weekly")
    return {"ok": True, "report": get_engine().build_periodic_report(kind)}


@router.get("/reports/periodic/{kind}/export")
async def periodic_export(
    kind: str,
    format: str = Query("markdown", pattern="^(markdown|pdf|html)$"),
    _u=Depends(require_permissions("report:export")),
):
    if kind not in ("daily", "weekly"):
        raise ValidationError("简报类型仅支持 daily / weekly")
    report = get_engine().build_periodic_report(kind)
    label = "舆情日报" if kind == "daily" else "舆情周报"
    # 同事件报告：文件名含中文，按 RFC 6266 用 filename* 传 UTF-8，并留 ASCII 兜底
    disp = (
        f'attachment; filename="{kind}_yuqing.{format}"; '
        f"filename*=UTF-8''{quote(f'{label}.{format}')}"
    )
    if format == "markdown":
        return Response(export_markdown(report).encode("utf-8"),
                        media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": disp})
    if format == "html":
        return Response(export_html(report).encode("utf-8"),
                        media_type="text/html; charset=utf-8",
                        headers={"Content-Disposition": disp})
    content = export_pdf(report)
    media = "application/pdf" if content[:4] == b"%PDF" else "text/html"
    return Response(content, media_type=media, headers={"Content-Disposition": disp})


@router.get("/reports/{event_id}/export")
async def export_report(
    event_id: str,
    format: str = Query("markdown", pattern="^(markdown|pdf|html)$"),
    _u=Depends(require_permissions("report:export")),
):
    if not get_store().get_event(event_id):
        raise NotFoundError(f"事件不存在: {event_id}")
    report = get_engine().build_report(event_id)
    ev = get_store().get_event(event_id)
    safe_title = (ev.get("title") or event_id).replace("/", "_")
    # Content-Disposition 文件名含中文，HTTP 头须为 latin-1；按 RFC 6266 用
    # filename* 传 UTF-8 百分号编码，并保留 ASCII 兜底 filename 兼容旧客户端。
    disp = (
        f'attachment; filename="yuqing_report.{format}"; '
        f"filename*=UTF-8''{quote(f'yuqing_{safe_title}.{format}')}"
    )
    if format == "markdown":
        content = export_markdown(report).encode("utf-8")
        return Response(content, media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": disp})
    if format == "html":
        content = export_html(report).encode("utf-8")
        return Response(content, media_type="text/html; charset=utf-8",
                        headers={"Content-Disposition": disp})
    content = export_pdf(report)
    media = "application/pdf" if content[:4] == b"%PDF" else "text/html"
    return Response(content, media_type=media,
                    headers={"Content-Disposition": disp})


# ---------------------------------------------------------------------------
# 多模态接入演示（图文 OCR / 音视频 ASR 解析管线）
# ---------------------------------------------------------------------------
@router.get("/ingest/demo")
async def ingest_demo(_u=Depends(require_permissions("feed:view"))):
    raw_items = [
        {"content_type": "ocr", "sample_id": "ocr_food_1", "source": "短视频平台"},
        {"content_type": "transcript", "sample_id": "asr_food_1", "source": "新闻门户"},
        {"content_type": "ocr", "sample_id": "ocr_logi_1", "source": "行业论坛"},
        {"content_type": "transcript", "sample_id": "asr_ev_1", "source": "社交媒体"},
    ]
    results = []
    for it in raw_items:
        parsed = parse_multimodal_item(it)
        results.append({
            "raw": it,
            "extracted_text": parsed["extracted_text"],
            "cleaned_text": parsed["cleaned_text"],
            "note": "模拟 OCR/ASR 服务解析；生产可替换为真实多模态模型，保持相同契约。",
        })
    return {"pipeline": ["原始素材(图片/音视频)", "OCR/ASR 解析", "文本清洗", "SimHash 去重", "情感/实体分析"],
            "items": results}
