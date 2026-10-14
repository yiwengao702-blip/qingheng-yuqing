# 文件位置: backend/app/analysis/keywords.py
# 功能: 热点词提取（基于分词频率）与实体抽取（专名词典 + jieba 词性标注回退）。
from __future__ import annotations

from collections import Counter
from typing import Dict, List

from app.data.clean import tokenize

try:
    import jieba
    import jieba.posseg  # 词性标注子模块需显式导入

    jieba.setLogLevel("ERROR")
    HAS_JIEBA = True
except Exception:  # pragma: no cover
    HAS_JIEBA = False


def _post_text(post: dict) -> str:
    parts = [post.get("content", "") or ""]
    if post.get("ocr_text"):
        parts.append(post["ocr_text"])
    if post.get("transcript_text"):
        parts.append(post["transcript_text"])
    return " ".join(parts)


def hotwords_from_posts(posts: List[dict], top_n: int = 40) -> List[Dict]:
    """聚合帖子文本，返回高频词（热点词）。"""
    counter: Counter = Counter()
    for p in posts:
        for tok in tokenize(_post_text(p)):
            counter[tok] += 1
    return [{"word": w, "weight": c} for w, c in counter.most_common(top_n)]


def extract_entities_in_text(text: str, entity_dict: List[dict]) -> List[str]:
    """从文本中抽取命中的核心实体（机构/人物/产品/事件）。

    entity_dict: [{"name": "...", "type": "机构"|"人物"|"产品"|"事件"}, ...]
    优先用专名词典做子串匹配，再用 jieba 词性标注（nr/nt/nz）回退补充。
    """
    if not text:
        return []
    found: List[str] = []
    for ent in entity_dict:
        name = ent.get("name", "")
        if name and name in text and name not in found:
            found.append(name)
    if HAS_JIEBA:
        for w, flag in jieba.posseg.cut(text):
            if flag in ("nr", "nt", "nz") and len(w) >= 2 and w not in found:
                found.append(w)
    return found


def entity_type_map(entity_dict: List[dict]) -> Dict[str, str]:
    return {e["name"]: e.get("type", "其他") for e in entity_dict}
