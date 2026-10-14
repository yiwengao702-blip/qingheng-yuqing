# 文件位置: backend/app/data/clean.py
# 功能: 文本清洗、中文分词（jieba 优先，缺失则回退 n-gram）、SimHash 指纹与去重。
#       用于「文本清洗与 SimHash 去重」与「热点词提取」的输入预处理。
from __future__ import annotations

import hashlib
import re
from typing import List, Set

# jieba 可选：安装则用语义分词，未安装则回退到连续中文 n-gram
try:
    import jieba

    jieba.setLogLevel("ERROR")
    HAS_JIEBA = True
except Exception:  # pragma: no cover
    HAS_JIEBA = False

# 常见中文停用词（精简版，覆盖高频虚词与标点）
STOPWORDS: Set[str] = {
    "的", "了", "和", "是", "在", "我", "有", "就", "不", "也", "都", "而", "及", "与",
    "你", "他", "她", "它", "们", "这", "那", "个", "之", "吗", "呢", "吧", "啊", "嘛",
    "把", "被", "让", "给", "对", "从", "向", "到", "为", "以", "于", "但", "却", "还",
    "又", "很", "太", "更", "最", "上", "下", "中", "后", "前", "内", "外", "没", "没",
    "已经", "正在", "将要", "可以", "应该", "可能", "这么", "那么", "什么", "怎么", "为什么",
    "因为", "所以", "如果", "虽然", "但是", "然而", "于是", "并且", "或者", "以及", "这个",
    "那个", "这些", "那些", "一些", "一样", "这样", "那样", "如何", "多少", "感觉", "觉得",
    "现在", "今天", "的时候", "一个", "一种", "一位", "一款", "一名", "我们", "你们", "他们",
}

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\W_0-9]+")


def normalize_text(text: str) -> str:
    """清洗文本：去 HTML、去 URL、压缩空白。"""
    if not text:
        return ""
    text = _HTML_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def tokenize(text: str) -> List[str]:
    """中文分词：jieba 优先；回退为 2~3 字连续中文 n-gram。"""
    text = normalize_text(text)
    if not text:
        return []
    if HAS_JIEBA:
        return [
            t for t in jieba.lcut(text)
            if len(t) > 1 and t not in STOPWORDS and not _PUNCT_RE.fullmatch(t)
        ]
    # 回退：连续中文片段切 2~3 字 n-gram
    out: List[str] = []
    for seg in re.findall(r"[\u4e00-\u9fff]+", text):
        for n in (3, 2):
            for i in range(len(seg) - n + 1):
                gram = seg[i:i + n]
                if gram not in STOPWORDS:
                    out.append(gram)
    return out


def _token_hash(token: str) -> int:
    return int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)


def simhash(text: str, bits: int = 64) -> int:
    """计算文本 SimHash 指纹（64 位）。用于近似重复检测。"""
    tokens = tokenize(text)
    if not tokens:
        return 0
    vec = [0] * bits
    for tok in tokens:
        h = _token_hash(tok)
        for i in range(bits):
            if (h >> i) & 1:
                vec[i] += 1
            else:
                vec[i] -= 1
    fp = 0
    for i in range(bits):
        if vec[i] > 0:
            fp |= 1 << i
    return fp


def hamming_distance(a: int, b: int) -> int:
    """两指纹的汉明距离。"""
    x = a ^ b
    return x.bit_count() if hasattr(int, "bit_count") else bin(x).count("1")
