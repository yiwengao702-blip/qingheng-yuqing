# 文件位置: backend/app/analysis/sentiment.py
# 功能: 情感倾向识别（正/中/负）+ 细粒度负向情绪（愤怒/失望/恐慌/质疑）。
#       基于中文情感词典做子串计数，离线可跑；可替换为真实情感模型。
from __future__ import annotations

from typing import Dict, List

# 正向情感词
POSITIVE: List[str] = [
    "好评", "点赞", "推荐", "满意", "喜欢", "信赖", "安心", "靠谱", "良心", "给力",
    "不错", "优秀", "温暖", "负责", "透明", "解决", "正能量", "支持", "赞", "好",
    "棒", "惊喜", "放心", "专业", "贴心", "点赞了", "值得", "稳了", "可以", "没问题",
]

# 负向情感词
NEGATIVE: List[str] = [
    "差评", "投诉", "维权", "曝光", "黑幕", "欺骗", "欺诈", "虚假", "造假", "虚标",
    "缩水", "翻车", "塌房", "垃圾", "无语", "离谱", "愤怒", "失望", "寒心", "坑爹",
    "坑人", "恶心", "担忧", "恐慌", "害怕", "危机", "危害", "致癌", "质疑", "怀疑",
    "套路", "忽悠", "敷衍", "推诿", "冷漠", "傲慢", "失责", "违规", "违法", "退款",
    "赔偿", "道歉", "抵制", "拉黑", "问题", "故障", "事故", "隐患", "威胁", "恶劣",
]

# 细粒度负向情绪词典
EMOTION_LEXICON: Dict[str, List[str]] = {
    "愤怒": ["愤怒", "气愤", "离谱", "无语", "垃圾", "坑爹", "坑人", "恶心", "黑心",
            "混蛋", "欺", "骗", "忽悠", "敷衍", "傲慢", "冷漠", "失责", "忍不了", "太气"],
    "失望": ["失望", "遗憾", "寒心", "心寒", "落差", "落空", "辜负", "不再", "再也不", "伤心"],
    "恐慌": ["恐慌", "害怕", "担忧", "担心", "焦虑", "危机", "危害", "致癌", "危险", "健康",
            "隐患", "怕", "慌", "不安"],
    "质疑": ["质疑", "怀疑", "疑惑", "凭什么", "套路", "虚标", "虚假", "造假", "水分",
            "内幕", "真相", "怎么可能", "真的吗", "为何", "为什么", "怎么回事"],
}

# 情绪词补入负向词表
# 背景：只把词放进 EMOTION_LEXICON 是不够的 —— 「太气愤了」「很担心」「心寒」这类
# 明显负面的表达会因此拿不到负向分，被误判为中性，出现「情绪识别为愤怒、
# 整体倾向却算中性」的自相矛盾结果。
# 这里只补入本身即负面表达的词；疑问类的「为什么 / 怎么回事 / 真的吗」以及
# 中性的「健康」不并入，否则大量中性提问帖会被误判为负向。
EMOTION_NEGATIVE_EXTRA: List[str] = [
    "气愤", "黑心", "混蛋", "忍不了", "太气",          # 愤怒
    "遗憾", "心寒", "落差", "落空", "辜负", "伤心",     # 失望
    "担心", "焦虑", "危险", "不安",                    # 恐慌
    "疑惑", "凭什么", "水分", "内幕", "真相",          # 质疑
]
NEGATIVE: List[str] = list(dict.fromkeys(NEGATIVE + EMOTION_NEGATIVE_EXTRA))

_LABEL_BY_SCORE = lambda s: "positive" if s > 0.12 else ("negative" if s < -0.05 else "neutral")


def _count_hits(text: str, words: List[str]) -> int:
    return sum(text.count(w) for w in words)


def analyze_sentiment(text: str) -> Dict:
    """返回情感分析结果：label / score(-1~1) / 各细粒度情绪命中数 / 主导负向情绪。"""
    if not text:
        return {"label": "neutral", "score": 0.0,
                "emotions": {k: 0 for k in EMOTION_LEXICON}, "dominant_emotion": None}
    pos = _count_hits(text, POSITIVE)
    neg = _count_hits(text, NEGATIVE)
    score = (pos - neg) / (pos + neg + 1)
    emotions = {k: _count_hits(text, wl) for k, wl in EMOTION_LEXICON.items()}
    dominant = None
    if neg > 0:
        # 取命中数最多的细粒度情绪（并列取顺序优先）
        cand = [(k, v) for k, v in emotions.items() if v > 0]
        if cand:
            dominant = max(cand, key=lambda x: x[1])[0]
    return {
        "label": _LABEL_BY_SCORE(score),
        "score": round(score, 4),
        "emotions": emotions,
        "dominant_emotion": dominant,
    }


def emotion_distribution(posts: List[dict]) -> Dict[str, int]:
    """聚合一批帖子的细粒度情绪分布（仅统计负向主导情绪）。"""
    dist = {"愤怒": 0, "失望": 0, "恐慌": 0, "质疑": 0, "其他负向": 0, "非负向": 0}
    for p in posts:
        sent = p.get("sentiment_detail") or analyze_sentiment(p.get("content", ""))
        if sent["label"] != "negative":
            dist["非负向"] += 1
            continue
        de = sent.get("dominant_emotion")
        if de:
            dist[de] += 1
        else:
            dist["其他负向"] += 1
    return dist
