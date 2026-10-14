# 文件位置: backend/app/analysis/propagation.py
# 功能: 传播脉络溯源 —— 父子扩散树、首发节点、关键引爆节点、按小时传播时间线。
#       同时提供被风险/聚类模块复用的公用工具：parse_time、interaction。
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional


def parse_time(s: Optional[str]) -> Optional[datetime]:
    """解析 ISO 时间字符串为无时区的 datetime（用于统一聚合）。"""
    if not s:
        return None
    s2 = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s2)
    except ValueError:
        return None
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def interaction(p: dict) -> int:
    """互动量 = 转发 + 评论 + 点赞。"""
    return int(p.get("repost", 0) + p.get("comment", 0) + p.get("like", 0))


def build_propagation(posts: List[dict]) -> Dict:
    """构建事件传播结构。"""
    if not posts:
        return {"origin": None, "key_nodes": [], "timeline": [], "total": 0, "max_depth": 0}

    by_id = {p["id"]: p for p in posts}
    children = defaultdict(list)
    roots = []
    for p in posts:
        pid = p.get("parent_id")
        if pid and pid in by_id:
            children[pid].append(p)
        else:
            roots.append(p)

    # 首发节点：无父节点中发布时间最早者
    origin = None
    candidates = sorted(roots, key=lambda p: parse_time(p.get("publish_time")) or datetime.max)
    if candidates:
        origin = candidates[0]
    else:
        origin = min(posts, key=lambda p: parse_time(p.get("publish_time")) or datetime.max)

    # 关键引爆节点：互动量最高 + KOL 账号
    key_nodes = []
    for p in sorted(posts, key=interaction, reverse=True)[:6]:
        is_kol = p.get("author_weight", 0) >= 0.8
        key_nodes.append({
            "id": p["id"], "author": p.get("author"), "platform": p.get("platform"),
            "publish_time": p.get("publish_time"),
            "interaction": interaction(p),
            "role": "KOL引爆" if is_kol else "高互动扩散",
        })

    # 按小时聚合传播时间线（含累计声量与负向占比）
    hours: Dict[str, Dict] = defaultdict(lambda: {"volume": 0, "neg": 0})
    min_t = None
    max_t = None
    for p in posts:
        t = parse_time(p.get("publish_time"))
        if t is None:
            continue
        min_t = t if min_t is None or t < min_t else min_t
        max_t = t if max_t is None or t > max_t else max_t
        key = t.strftime("%Y-%m-%d %H:00")
        hours[key]["volume"] += 1
        if p.get("sentiment") == "negative":
            hours[key]["neg"] += 1

    timeline = []
    cum = 0
    for k in sorted(hours.keys()):
        cum += hours[k]["volume"]
        neg_ratio = round(hours[k]["neg"] / hours[k]["volume"], 3) if hours[k]["volume"] else 0
        timeline.append({
            "hour": k, "volume": hours[k]["volume"],
            "negative": hours[k]["neg"], "negative_ratio": neg_ratio, "cumulative": cum,
        })

    # 最大传播深度（从首发沿父子链向下）
    max_depth = 0

    def depth(pid, d):
        nonlocal max_depth
        max_depth = max(max_depth, d)
        for c in children.get(pid, []):
            depth(c["id"], d + 1)

    depth(origin["id"], 1)

    return {
        "origin": {
            "id": origin["id"], "author": origin.get("author"),
            "platform": origin.get("platform"), "publish_time": origin.get("publish_time"),
            "content": (origin.get("content") or "")[:120],
        },
        "key_nodes": key_nodes,
        "timeline": timeline,
        "total": len(posts),
        "max_depth": max_depth,
    }
