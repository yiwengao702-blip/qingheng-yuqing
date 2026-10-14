# 文件位置: backend/app/analysis/entity_graph.py
# 功能: 热点实体抽取与关联图谱（同一帖子内实体共现构建边）。
from __future__ import annotations

from collections import Counter
from typing import Dict, List

from app.analysis.keywords import extract_entities_in_text, entity_type_map


def _post_text(post: dict) -> str:
    parts = [post.get("content", "") or ""]
    if post.get("ocr_text"):
        parts.append(post["ocr_text"])
    if post.get("transcript_text"):
        parts.append(post["transcript_text"])
    return " ".join(parts)


def build_entity_graph(posts: List[dict], event: dict) -> Dict:
    """构建事件内实体共现图谱。"""
    entity_dict = event.get("entities", [])
    type_map = entity_type_map(entity_dict)

    node_count: Counter = Counter()
    edge_w: Counter = Counter()
    for p in posts:
        ents = extract_entities_in_text(_post_text(p), entity_dict)
        for e in ents:
            node_count[e] += 1
        for i in range(len(ents)):
            for j in range(i + 1, len(ents)):
                a, b = ents[i], ents[j]
                key = (a, b) if a < b else (b, a)
                edge_w[key] += 1

    nodes = [
        {"id": name, "name": name, "type": type_map.get(name, "其他"), "value": cnt}
        for name, cnt in node_count.most_common(15)
    ]
    edges = [
        {"source": a, "target": b, "value": w}
        for (a, b), w in edge_w.items() if w >= 1 and a in node_count and b in node_count
    ]
    # 仅保留出现在 nodes 中的实体边（防止孤立边）
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]
    return {"nodes": nodes, "edges": edges}
