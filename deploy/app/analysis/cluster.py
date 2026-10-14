# 文件位置: backend/app/analysis/cluster.py
# 功能: 核心观点聚类（按关键词相似度贪心聚类）+ 意图提炼。
from __future__ import annotations

from collections import Counter
from typing import Dict, List

from app.data.clean import tokenize
from app.analysis.propagation import interaction


def _post_text(post: dict) -> str:
    parts = [post.get("content", "") or ""]
    if post.get("ocr_text"):
        parts.append(post["ocr_text"])
    if post.get("transcript_text"):
        parts.append(post["transcript_text"])
    return " ".join(parts)


def _infer_intent(posts: List[dict], keywords: List[str]) -> str:
    """依据情感与关键词推断讨论意图。"""
    neg = sum(1 for p in posts if p.get("sentiment") == "negative")
    pos = sum(1 for p in posts if p.get("sentiment") == "positive")
    text = " ".join(_post_text(p) for p in posts)
    if neg >= pos and any(w in text for w in ["维权", "投诉", "退款", "赔偿", "起诉", "曝光", "举报"]):
        return "投诉维权"
    if neg >= pos and any(w in text for w in ["为什么", "凭什么", "质疑", "真相", "内幕", "怎么回事"]):
        return "质疑求证"
    if neg > pos:
        return "情绪宣泄"
    if pos > neg:
        return "支持肯定"
    if any(w in text for w in ["怎么", "如何", "建议", "办法", "求"]):
        return "求助建议"
    return "理性讨论"


def cluster_viewpoints(posts: List[dict], top_n: int = 6) -> List[Dict]:
    """将事件内帖子按关键词集合 Jaccard 相似度聚类为若干核心观点簇。"""
    if not posts:
        return []

    sigs: List[tuple] = []
    for p in posts:
        toks = tokenize(_post_text(p))
        kw = Counter(toks)
        sigs.append((p, set(kw.keys()), kw))

    clusters: List[Dict] = []  # {"posts":[...], "kw":Counter}
    for p, kwset, kw in sigs:
        best = None
        best_j = 0.0
        for c in clusters:
            inter = len(kwset & c["kwset"])
            union = len(kwset | c["kwset"]) or 1
            j = inter / union
            if j > best_j:
                best_j, best = j, c
        if best and best_j >= 0.18:
            best["posts"].append(p)
            best["kw"].update(kw)
        else:
            clusters.append({"posts": [p], "kwset": kwset, "kw": Counter(kw)})

    # 簇过多则合并最小的，控制在 top_n
    while len(clusters) > top_n:
        clusters.sort(key=lambda c: len(c["posts"]))
        a = clusters.pop(0)
        b = clusters.pop(0)
        merged_kw = a["kw"] + b["kw"]
        clusters.append({
            "posts": a["posts"] + b["posts"],
            "kwset": set(merged_kw.keys()),
            "kw": merged_kw,
        })

    out: List[Dict] = []
    for i, c in enumerate(clusters):
        size = len(c["posts"])
        rep = max(c["posts"], key=interaction)
        top_kw = [w for w, _ in c["kw"].most_common(6)]
        sentiments = [p.get("sentiment", "neutral") for p in c["posts"]]
        sentiment_dist = {
            "positive": sentiments.count("positive"),
            "neutral": sentiments.count("neutral"),
            "negative": sentiments.count("negative"),
        }
        out.append({
            "cluster_id": f"vc_{i + 1}",
            "label": top_kw[0] if top_kw else f"观点簇{i + 1}",
            "keywords": top_kw,
            "size": size,
            "sentiment_dist": sentiment_dist,
            "intent": _infer_intent(c["posts"], top_kw),
            "representative": {
                "id": rep["id"], "author": rep.get("author"),
                "platform": rep.get("platform"), "content": (rep.get("content") or "")[:140],
                "interaction": interaction(rep),
            },
            "sample_post_ids": [p["id"] for p in c["posts"][:5]],
        })
    # 按规模降序
    out.sort(key=lambda x: x["size"], reverse=True)
    return out
