# 文件位置: backend/app/analysis/risk.py
# 功能: 舆情烈度指数与风险等级（S/A/B/C）。
#       烈度 = f(传播扩散速度, 互动量, KOL 账号权重, 敏感词命中)，归一化到 0~100。
from __future__ import annotations

import math
from typing import Dict, List

from app.analysis.propagation import interaction, parse_time

# 风险等级阈值（烈度指数）
GRADE_THRESHOLDS = [(80, "S"), (60, "A"), (40, "B"), (0, "C")]


def _grade_of(intensity: float) -> str:
    for th, g in GRADE_THRESHOLDS:
        if intensity >= th:
            return g
    return "C"


def post_risk_grade(post: dict) -> str:
    """单帖风险等级：结合情感、敏感词命中、KOL 权重、互动量。"""
    sent = post.get("sentiment", "neutral")
    hi_sensitive = post.get("sensitive_hit", False)
    kol = post.get("author_weight", 0) >= 0.8
    inter = interaction(post)
    if hi_sensitive and (inter >= 500 or kol):
        return "S"
    if hi_sensitive or (sent == "negative" and kol):
        return "A"
    if sent == "negative":
        return "B"
    return "C"


def event_intensity(event_posts: List[dict], event: dict) -> Dict:
    """事件级舆情烈度指数与风险等级。"""
    n = len(event_posts)
    if n == 0:
        return {"intensity": 0.0, "grade": "C",
                "factors": {"spread_speed": 0, "interaction": 0, "kol": 0, "sensitive": 0}}

    times = [parse_time(p.get("publish_time")) for p in event_posts]
    times = [t for t in times if t]
    if times:
        span_h = max((max(times) - min(times)).total_seconds() / 3600.0, 1.0)
    else:
        span_h = 1.0
    speed = n / span_h  # 每小时声量

    total_inter = sum(interaction(p) for p in event_posts)
    inter_score = math.log1p(total_inter)
    kol_max = max((p.get("author_weight", 0) for p in event_posts), default=0.0)
    hi_sensitive = sum(1 for p in event_posts if p.get("sensitive_hit"))

    # 归一化到 0~1
    speed_norm = min(1.0, speed / 50.0)          # 50 帖/小时视为满速
    inter_norm = min(1.0, inter_score / 12.0)     # log1p(约 1.6e5) 视为满量
    kol_norm = min(1.0, kol_max)
    sens_norm = min(1.0, hi_sensitive / 10.0)    # 10 条高危命中视为满

    intensity = 100.0 * (
        0.30 * speed_norm + 0.30 * inter_norm + 0.20 * kol_norm + 0.20 * sens_norm
    )
    return {
        "intensity": round(intensity, 1),
        "grade": _grade_of(intensity),
        "factors": {
            "spread_speed": round(speed, 2),
            "interaction": total_inter,
            "kol_max": round(kol_max, 2),
            "sensitive_hits": hi_sensitive,
            "volume": n,
        },
    }
