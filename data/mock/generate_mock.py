# 文件位置: data/mock/generate_mock.py
# 功能: 生成模拟多源舆情数据集 dataset.json（文本 / 图片OCR / 音视频ASR），
#       覆盖社交媒体、短视频平台、新闻门户、行业论坛四类信源。
# 用法: 在项目根目录执行  python data/mock/generate_mock.py
#
# 与旧版的区别（真实化改造）：
#   1) 文本不再由十几条模板填空，而是「事件专属细节 × 平台语体骨架」组合，
#      并做情感词校验兜底，保证文本与标注情感一致（分析引擎会重新计算情感）。
#   2) 多模态文本严格取自本事件池，修掉旧版「饮品事件配快递转写」的串料 bug。
#   3) 时间分布按真实舆情规律：爆发核（对数正态，峰值 2~8h）× 昼夜节律（深夜低谷）。
#   4) 互动量为幂律长尾（多数帖子低互动，少量爆款），并区分平台特征
#      （抖音点赞高、知乎评论比高、新闻门户整体偏低）。
#   5) 账号池按平台区分，且账号有地域、有粉丝量级、会在同一事件中反复出现。
from __future__ import annotations

import json
import math
import os
import random
import sys
from datetime import datetime, timedelta
from typing import Dict, List

# 语料层与本文件同目录，直接导入即可
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from corpus_events import EVENTS  # noqa: E402
from corpus_text import (  # noqa: E402
    ACCOUNTS, BIZ_BY_EVENT, CLOSERS, CLOSERS_NEG, CLOSERS_ORAL, CLOSERS_ORAL_NEG,
    COUNTER_BY_EVENT, MENTIONS, PLATFORMS, SKE, TAGS,
)

SEED = 20260923  # 固定随机种子，保证演示数据可复现
random.seed(SEED)

# 输出路径：项目根/backend/app/data/dataset.json
OUT_PATH = os.path.join(_ROOT, "backend", "app", "data", "dataset.json")

REGIONS = ["华北", "华东", "华南", "华中", "西南", "西北", "东北"]

# ---------------------------------------------------------------------------
# 情感词表见下方「同源导入」段落（复用 backend/app/analysis/sentiment.py）。
# 作用有二：① 生成时校验文本是否真的能被判定为目标情感；
#          ② 为中性帖挑选「不含情感词的干净细节」，避免被误判为负向。
# ---------------------------------------------------------------------------
# 强兜底短语：仅在骨架重试若干次仍不达标时使用。
# 要求：① 含 3 个以上目标情绪词，确保不会被正文里的正向词中和；
#      ② 语气尽量自然，避免一眼看出是「补上去的」。
FALLBACK_STRONG = {
    "愤怒": ["说实话，这事太离谱了，越看越气愤。",
             "说真的，这种处理方式太气人了，越想越无语。",
             "讲真，做得这么离谱还一味敷衍，谁看了不气愤。"],
    "失望": ["说实话挺失望的，落差太大，想起来就寒心。",
             "说真的，这次的落差让人挺伤心，也很失望。",
             "讲真，本来是抱着期待的，现在只剩失望和寒心。"],
    "恐慌": ["说实话很担心，越想越害怕，心里总觉得不安。",
             "说真的，想到这些隐患就有些担忧和害怕。",
             "讲真，越琢磨越焦虑，总担心会出乱子。"],
    "质疑": ["说实话我有点怀疑，这里面的真相到底是什么。",
             "说真的，这事透着点套路，我越来越怀疑了。",
             "讲真，凭什么这么说？我确实有些疑惑和怀疑。"],
    "正面": ["整体体验不错，这次处理得挺负责，值得推荐。",
             "说真的，用起来挺顺手，好评，也值得支持。",
             "讲真，这次值得点赞，服务很专业，让人放心。"],
}
# 保留旧名兼容（骨架自带兜底用的短句池）
FALLBACK = FALLBACK_STRONG


# ---------------------------------------------------------------------------
# 情感判定：完整复刻 backend/app/analysis/sentiment.py 的打分与情绪归属逻辑。
# 生成时必须按引擎的口径校验，否则「写的时候是愤怒、算出来是中性」会很常见
# —— 典型陷阱是正负词同现，例如「还能不能放心用啊」里「放心」正向、「怕」负向。
# ---------------------------------------------------------------------------
def _score_label(text: str):
    pos = _count(text, POS_WORDS)
    neg = _count(text, NEG_WORDS)
    score = (pos - neg) / (pos + neg + 1)
    label = "positive" if score > 0.12 else ("negative" if score < -0.05 else "neutral")
    return label, score


def _dominant_emotion(text: str):
    cand = [(k, _count(text, w)) for k, w in EMO_WORDS.items()]
    cand = [(k, v) for k, v in cand if v > 0]
    return max(cand, key=lambda x: x[1])[0] if cand else None


def _match(text: str, want: str) -> bool:
    """判断文本经分析引擎处理后，是否真的落在期望的情感/情绪上。"""
    label, _ = _score_label(text)
    if want == "中性":
        return label == "neutral"
    if want == "正面":
        return label == "positive"
    return label == "negative" and _dominant_emotion(text) == want


def _fallback_text(text: str, want: str, style: str) -> str:
    """兜底：追加一条含多个目标情绪词的短句（长文独立成段，短文接在句尾）。

    中性帖不做兜底：追加中性句无法改变打分（分数只由正负词数量决定），
    强行改写反而会更假，因此接受少量中性帖被判为正向的选择性偏差。
    另外若正文里已经出现高度相似的表达（例如骨架自带「挺失望的」），
    就不再追加，否则会出现同一句话连着说两遍的破绽。
    """
    if want not in FALLBACK_STRONG:
        return text
    pool = [p for p in FALLBACK_STRONG[want] if p[:6] not in text]
    if not pool:
        return text
    return _append_fallback(text, random.choice(pool), style)


def _append_fallback(text: str, phrase: str, style: str) -> str:
    """把兜底短语接到正文上：长文独立成段，短文补足句末标点后再接。"""
    if style in ("long", "news"):
        return text.rstrip() + "\n\n" + phrase
    tail = text.rstrip()
    if not tail.endswith(("。", "！", "？", "…", "~", "\n")):
        tail += "。"
    return tail + phrase

# ---------------------------------------------------------------------------
# 真实舆情的时间规律
#   爆发核：对数正态形状，峰值落在事件设定的 peak_hours（真实热点多为 2~8 小时）
#   昼夜节律：深夜低谷、通勤与晚间高峰（社交平台真实活跃曲线）
# ---------------------------------------------------------------------------
DIURNAL = {
    0: 0.18, 1: 0.10, 2: 0.07, 3: 0.05, 4: 0.06, 5: 0.10,
    6: 0.25, 7: 0.55, 8: 0.80, 9: 0.92, 10: 1.00, 11: 0.98,
    12: 0.88, 13: 0.85, 14: 0.90, 15: 0.95, 16: 0.98, 17: 1.00,
    18: 1.02, 19: 1.15, 20: 1.25, 21: 1.20, 22: 0.95, 23: 0.55,
}
BURST_SIGMA = 0.72
_BURST_PEAK_MAX = 1.0  # 爆发核峰值归一化上界（近似值，用于拒绝采样）

# 不同事件类别下的负向情绪细分权重（食品安全偏愤怒+恐慌，服务纠纷偏愤怒+失望，
# 合规类偏质疑，民生类偏恐慌+质疑），比旧版「四种情绪平均随机」真实得多。
EMOTION_MIX = {
    "质量争议": {"愤怒": 0.36, "恐慌": 0.30, "失望": 0.20, "质疑": 0.14},
    "服务纠纷": {"愤怒": 0.42, "失望": 0.34, "质疑": 0.18, "恐慌": 0.06},
    "合规风险": {"质疑": 0.40, "恐慌": 0.22, "愤怒": 0.22, "失望": 0.16},
    "公共事件": {"恐慌": 0.38, "质疑": 0.30, "失望": 0.18, "愤怒": 0.14},
    "其他": {"愤怒": 0.30, "失望": 0.25, "质疑": 0.25, "恐慌": 0.20},
}

# 平台情感倾向修正：短视频最外放，知乎/公众号更理性，新闻门户客观克制
PLATFORM_NEG_BIAS = {
    "douyin": 0.07, "weibo": 0.03, "zhihu": 0.0, "forum": 0.01,
    "toutiao": -0.06, "news": -0.14, "wechat": -0.08,
}

# 平台在各事件上的曝光偏好（新闻类事件上新闻门户更多，消费纠纷上社交平台更多）
PLATFORM_BIAS = {
    "ev_g1": {"weibo": 1.3, "wechat": 1.2, "forum": 1.1},
    "ev_g2": {"weibo": 1.3, "wechat": 1.2, "toutiao": 1.1, "forum": 1.1},
    "ev_g3": {"weibo": 1.35, "wechat": 1.25, "zhihu": 1.3, "forum": 1.1, "douyin": 1.1},
    "ev_g4": {"weibo": 1.3, "wechat": 1.2, "toutiao": 1.15, "forum": 1.2, "douyin": 1.1},
    "ev_g5": {"weibo": 1.3, "wechat": 1.2, "zhihu": 1.2, "forum": 1.1, "douyin": 1.1},
    "ev_g6": {"douyin": 1.4, "weibo": 1.3, "wechat": 1.2, "news": 1.1},
    # ev_g7 在线服务平台宕机：服务纠纷类，社媒与论坛讨论最热烈，短视频次之
    "ev_g7": {"weibo": 1.3, "wechat": 1.2, "zhihu": 1.25, "forum": 1.15, "douyin": 1.1},
    # ev_g8 理财平台收益争议：合规风险类，社媒/公众号/知乎/头条并重，新闻门户跟进报道
    "ev_g8": {"weibo": 1.3, "wechat": 1.25, "zhihu": 1.3, "toutiao": 1.15, "forum": 1.1, "news": 1.05},
    # ev_g9 食品质量争议：质量类，社媒/公众号/头条/论坛并重，短视频扩散快
    "ev_g9": {"weibo": 1.3, "wechat": 1.2, "toutiao": 1.15, "forum": 1.2, "douyin": 1.1},
    # ev_g10 城市公共服务：公共事件类，社媒/公众号/知乎/头条/新闻并重，论坛讨论政策
    "ev_g10": {"weibo": 1.3, "wechat": 1.2, "zhihu": 1.2, "toutiao": 1.15, "forum": 1.1, "news": 1.1},
}

# 平台互动特征（点赞 / 评论 / 转发 的相对系数）
PLATFORM_INTERACTION = {
    "weibo": {"like": 1.00, "comment": 0.60, "repost": 0.55},
    "douyin": {"like": 3.00, "comment": 0.35, "repost": 0.22},
    "wechat": {"like": 2.20, "comment": 0.16, "repost": 0.12},
    "toutiao": {"like": 0.35, "comment": 0.22, "repost": 0.10},
    "news": {"like": 0.15, "comment": 0.09, "repost": 0.07},
    "zhihu": {"like": 0.70, "comment": 0.32, "repost": 0.05},
    "forum": {"like": 0.10, "comment": 0.48, "repost": 0.02},
}

EMOTION_KEYS = ["愤怒", "失望", "恐慌", "质疑"]

# 生成过程统计：兜底率过高说明骨架质量不足，需要回头打磨语料
_STATS = {"total": 0, "fallback": 0}

# ---------------------------------------------------------------------------
# 情感词表：直接复用分析引擎的词表。
# 这里曾经手抄了一份副本，结果引擎侧补词（把「气愤 / 心寒 / 担心」并进负向词表）后
# 副本没跟上，出现「生成器认为达标、引擎算出来却是中性」的静默偏差。
# 因此改为同源导入，仅在脱离仓库单独运行时退回内嵌副本。
# ---------------------------------------------------------------------------
try:
    _BACKEND = os.path.join(_ROOT, "backend")
    if _BACKEND not in sys.path:
        sys.path.insert(0, _BACKEND)
    from app.analysis.sentiment import EMOTION_LEXICON as _EMO_ENGINE
    from app.analysis.sentiment import NEGATIVE as _NEG_ENGINE
    from app.analysis.sentiment import POSITIVE as _POS_ENGINE

    POS_WORDS: List[str] = list(_POS_ENGINE)
    NEG_WORDS: List[str] = list(_NEG_ENGINE)
    EMO_WORDS: Dict[str, List[str]] = {k: list(v) for k, v in _EMO_ENGINE.items()}
    WORD_SOURCE = "分析引擎同源词表"
except Exception:  # pragma: no cover - 仅在缺少 backend 包时触发
    POS_WORDS = [
        "好评", "点赞", "推荐", "满意", "喜欢", "信赖", "安心", "靠谱", "良心", "给力",
        "不错", "优秀", "温暖", "负责", "透明", "解决", "正能量", "支持", "赞", "好",
        "棒", "惊喜", "放心", "专业", "贴心", "点赞了", "值得", "稳了", "可以", "没问题",
    ]
    NEG_WORDS = [
        "差评", "投诉", "维权", "曝光", "黑幕", "欺骗", "欺诈", "虚假", "造假", "虚标",
        "缩水", "翻车", "塌房", "垃圾", "无语", "离谱", "愤怒", "失望", "寒心", "坑爹",
        "坑人", "恶心", "担忧", "恐慌", "害怕", "危机", "危害", "致癌", "质疑", "怀疑",
        "套路", "忽悠", "敷衍", "推诿", "冷漠", "傲慢", "失责", "违规", "违法", "退款",
        "赔偿", "道歉", "抵制", "拉黑", "问题", "故障", "事故", "隐患", "威胁", "恶劣",
        "气愤", "黑心", "混蛋", "忍不了", "太气", "遗憾", "心寒", "落差", "落空",
        "辜负", "伤心", "担心", "焦虑", "危险", "不安", "疑惑", "凭什么", "水分",
        "内幕", "真相",
    ]
    EMO_WORDS = {
        "愤怒": ["愤怒", "气愤", "离谱", "无语", "垃圾", "坑爹", "坑人", "恶心", "黑心",
                 "混蛋", "欺", "骗", "忽悠", "敷衍", "傲慢", "冷漠", "失责", "忍不了", "太气"],
        "失望": ["失望", "遗憾", "寒心", "心寒", "落差", "落空", "辜负", "不再", "再也不", "伤心"],
        "恐慌": ["恐慌", "害怕", "担忧", "担心", "焦虑", "危机", "危害", "致癌", "危险", "健康",
                 "隐患", "怕", "慌", "不安"],
        "质疑": ["质疑", "怀疑", "疑惑", "凭什么", "套路", "虚标", "虚假", "造假", "水分",
                 "内幕", "真相", "怎么可能", "真的吗", "为何", "为什么", "怎么回事"],
    }
    WORD_SOURCE = "内嵌兜底词表（未找到 backend 包）"


# ---------------------------------------------------------------------------
# 情感工具
# ---------------------------------------------------------------------------
def _count(text: str, words) -> int:
    return sum(text.count(w) for w in words)


def _clean_details(event: dict) -> list:
    """中性帖专用的「干净细节」：不含任何正负情感词，避免被误判为负向。"""
    out = []
    for d in event["details"]:
        if _count(d, POS_WORDS) == 0 and _count(d, NEG_WORDS) == 0:
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# 时间采样
# ---------------------------------------------------------------------------
def _burst_weight(hours: float, peak: float) -> float:
    """爆发核：对数正态形状，hours 为距事件首发的小时数。"""
    x = hours + 0.6
    mu = math.log(peak + 0.6)
    return math.exp(-((math.log(x) - mu) ** 2) / (2 * BURST_SIGMA ** 2))


def _sample_time(base: datetime, span: float, peak: float) -> datetime:
    """拒绝采样：爆发核 × 昼夜节律。拒绝若干次后退化为均匀采样，保证必定返回。"""
    limit = _BURST_PEAK_MAX * max(DIURNAL.values())
    for _ in range(140):
        h = random.uniform(0.0, span)
        dt = base + timedelta(hours=h)
        w = _burst_weight(h, peak) * DIURNAL[dt.hour]
        if random.random() < w / limit:
            return _jitter_minute(dt)
    return _jitter_minute(base + timedelta(hours=random.uniform(0.0, span)))


def _jitter_minute(dt: datetime) -> datetime:
    """分钟抖动：真实发帖时间在整点/半点附近有聚集，不是均匀分布。"""
    r = random.random()
    if r < 0.33:
        minute = random.randint(0, 5) if random.random() < 0.62 else random.randint(55, 59)
    elif r < 0.55:
        minute = random.choice([28, 29, 30, 31, 32])
    else:
        minute = random.randint(0, 59)
    return dt.replace(minute=minute, second=random.randint(0, 59), microsecond=0)


# ---------------------------------------------------------------------------
# 平台与账号
# ---------------------------------------------------------------------------
def _pick_platform(event_id: str) -> dict:
    bias = PLATFORM_BIAS.get(event_id, {})
    weights = [p["weight"] * bias.get(p["id"], 1.0) for p in PLATFORMS]
    return random.choices(PLATFORMS, weights=weights, k=1)[0]


def _build_author_pool(platform_id: str) -> dict:
    """给每个账号固定地域与「活跃度」，让同一账号在同一事件里多次出现时保持一致。"""
    pool = []
    for a in ACCOUNTS[platform_id]:
        item = dict(a)
        item["region"] = random.choice(REGIONS)
        # 活跃账号：真实平台里总有一部分用户发帖频率远高于其他人
        item["active"] = random.random() < 0.45
        pool.append(item)
    return {"all": pool, "active": [a for a in pool if a["active"]] or pool}


AUTHOR_POOLS = {p["id"]: _build_author_pool(p["id"]) for p in PLATFORMS}


def _pick_author(platform_id: str) -> dict:
    pool = AUTHOR_POOLS[platform_id]
    # 72% 从活跃子集挑 —— 制造「同一账号反复发言」的真实感，而不是全员只出现一次
    src = pool["active"] if random.random() < 0.72 else pool["all"]
    # KOL/媒体占比控制：真实平台里认证账号的发声量占比不高但影响力大
    r = random.random()
    if r < 0.16:
        cand = [a for a in pool["all"] if a["kind"] in ("media", "kol")] or src
        return random.choice(cand)
    if r < 0.24:
        cand = [a for a in pool["all"] if a["kind"] == "anon"] or src
        return random.choice(cand)
    cand = [a for a in src if a["kind"] == "normal"] or src
    return random.choice(cand)


# ---------------------------------------------------------------------------
# 文本构造
# ---------------------------------------------------------------------------
def _pick_emotion(event: dict, platform_id: str) -> str:
    mix = EMOTION_MIX.get(event["category"], EMOTION_MIX["其他"])
    keys = list(mix.keys())
    return random.choices(keys, weights=[mix[k] for k in keys], k=1)[0]


def _fill(skeleton: str, event: dict, want: str, clean: bool = False) -> str:
    """把骨架里的占位符替换为事件专属内容（含行业语境槽位）。"""
    details = _clean_details(event) if clean else event["details"]
    if not details:
        details = event["details"]
    counter = COUNTER_BY_EVENT.get(event["id"], ["情况还在核实中"])
    biz = BIZ_BY_EVENT.get(event["id"], {})
    values = {
        "subject": event["subject"],
        "detail": random.choice(details),
        "role": random.choice(event["roles"]),
        "counter": random.choice(counter),
        "demand": random.choice(event["demands"]),
        "official": random.choice(event["official"]),
        "kw": random.choice(event["keywords"]),
    }
    # 行业语境槽位：让长文里的「考核体系 / 加盟结构 / 责任划分」在所有行业下都讲得通
    for key in ("field", "org", "unit", "mid", "metric", "chain", "spot",
                "daily", "blame_line", "profit_src"):
        values[key] = biz.get(key, "相关方")
    try:
        return skeleton.format(**values)
    except (KeyError, IndexError):
        return skeleton


def _add_suffix(text: str, platform: dict, event: dict, want: str) -> str:
    """按平台习惯追加话题标签 / @ / 收尾语，进一步拉开帖子之间的差异。

    含情感词的收尾语只挂在负面帖上 —— 否则中性帖被追加「已经投诉了」之后，
    分析引擎会把它算成负向，情感分布就失真了。
    """
    if random.random() > platform["suffix_rate"]:
        return text
    style = platform["style"]
    if style == "news":  # 新闻门户是报道体，不会出现「求扩散」这类社交收尾语
        return text
    neg = want in EMOTION_KEYS
    kw = random.choice(event["keywords"])
    parts = []
    if style == "short":
        if random.random() < 0.5:
            parts.append(random.choice(TAGS).format(kw=kw))
        if neg and random.random() < 0.35:
            parts.append(random.choice(MENTIONS))
        pool = CLOSERS + (CLOSERS_NEG if neg else []) + CLOSERS_ORAL + (CLOSERS_ORAL_NEG if neg else [])
        if random.random() < 0.6:
            parts.append(random.choice(pool))
    else:
        pool = CLOSERS + (CLOSERS_NEG if neg else [])
        if random.random() < 0.5:
            parts.append(random.choice(pool))
    if not parts:
        return text
    joiner = " " if style == "short" else "\n\n"
    return text + joiner + " ".join(parts)


def _build_content(event: dict, platform: dict, want: str) -> str:
    """按平台语体选骨架 -> 填充事件细节与行业槽位 -> 校验情感 -> 追加平台化后缀。

    校验采用「重试 + 强兜底」：先换骨架/细节重试若干次，让达标的文本自然产生；
    实在不达标才追加一条强情绪句。这样既保证情感标注与正文一致，又不会
    让大量帖子末尾挂着同一句「补上去的话」。
    """
    bank = SKE.get(platform["id"], SKE["weibo"])
    # 若该平台该情感没有骨架（如新闻门户的「正面」通常也走中性语体），退回中性语体
    skeletons = bank.get(want) or bank.get("中性") or SKE["weibo"]["中性"]
    style = platform["style"]
    clean = (want == "中性")  # 中性帖只取不含情感词的细节，避免被误判成正/负
    cand = ""
    body = None
    for _ in range(5):
        cand = _fill(random.choice(skeletons), event, want, clean=clean)
        if _match(cand, want):
            body = cand
            break
    _STATS["total"] += 1
    if body is None:
        # 重试若干次仍不达标：记录比例，用于评估骨架质量（过高说明骨架还需打磨）
        _STATS["fallback"] += 1
        body = _fallback_text(cand, want, style)
    return _add_suffix(body, platform, event, want)


# ---------------------------------------------------------------------------
# 互动量：幂律长尾
# ---------------------------------------------------------------------------
def _interactions(author: dict, platform_id: str, want: str) -> dict:
    coef = PLATFORM_INTERACTION.get(platform_id, PLATFORM_INTERACTION["weibo"])
    fans = author.get("fans", 0)
    # 基础量级由粉丝量决定（开方压缩，避免千万级粉丝算出天文数字）
    scale = (fans ** 0.52) if fans > 0 else 7.0
    noise = math.exp(random.gauss(0, 0.9))
    # 情绪越激烈的内容越容易获得互动
    intensity = 1.0 + (0.45 if want in EMOTION_KEYS else 0.0) + (0.45 if want == "愤怒" else 0.0)
    core = scale * noise * intensity
    if random.random() < 0.03:  # 爆款长尾
        core *= random.uniform(8, 42)
    like = max(0, int(core * coef["like"]))
    # 评论与转发以点赞为基数，并做上限约束：真实平台上绝大多数内容满足
    # 点赞 ≥ 评论 ≥ 转发，但保留约 6%~8% 的自然反转（知乎/论坛里评论多于点赞很常见）。
    comment = int(like * coef["comment"] * math.exp(random.gauss(0, 0.42)))
    if random.random() > 0.06:
        comment = min(comment, like)
    repost = int(like * coef["repost"] * math.exp(random.gauss(0, 0.45)))
    if random.random() > 0.08:
        repost = min(repost, comment)
    return {"like": like, "comment": max(0, comment), "repost": max(0, repost)}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _strip_suffix(text: str) -> str:
    """剥离话题标签与 @ 提及，保留段落结构。

    跨平台搬运或刷量复制的都是「正文主体」，不会把原平台的 #话题# / @账号
    一并搬过去 —— 否则会出现新闻网上挂着微博话题标签这种一眼假的破绽。
    """
    out = []
    for line in text.split("\n"):
        segs = [s for s in line.split(" ") if s and not s.startswith("#") and not s.startswith("@")]
        out.append(" ".join(segs))
    cleaned = "\n".join(out).strip()
    return cleaned or text


def _make_post(pid: str, event: dict, when: datetime, want: str, platform: dict,
               author: dict, parent_id=None, is_spam=False,
               is_ocr=False, is_asr=False, media_text=None) -> dict:
    content = _build_content(event, platform, want)
    ctype, ocr_text, transcript_text = "text", None, None
    if is_ocr:
        ctype = "ocr"
        # 关键：OCR 文本只从本事件池取，杜绝旧版跨事件串料
        ocr_text = media_text or random.choice(event["ocr"])
    elif is_asr:
        ctype = "transcript"
        transcript_text = media_text or random.choice(event["asr"])
    inter = _interactions(author, platform["id"], want)
    return {
        "id": pid,
        "event_id": event["id"],
        "source_id": platform["id"],
        "source_type": platform["type"],
        "platform": platform["name"],
        "author": author["name"],
        "author_weight": author["weight"],
        # 以下三个是新增的真实感字段（不影响既有分析链路，引擎按需读取）
        "author_kind": author["kind"],
        "author_verified": author["verified"],
        "author_fans": author["fans"],
        "content": content,
        "content_type": ctype,
        "ocr_text": ocr_text,
        "transcript_text": transcript_text,
        "publish_time": when.strftime("%Y-%m-%d %H:%M:%S"),
        "repost": inter["repost"],
        "comment": inter["comment"],
        "like": inter["like"],
        "region": author["region"],
        "parent_id": parent_id,
        "is_spam": is_spam,
    }


def generate() -> dict:
    posts = []
    events_out = []
    pid = 0

    for ev in EVENTS:
        base = datetime.strptime(ev["start_time"], "%Y-%m-%d %H:%M")
        span = float(ev["span_hours"])
        peak = float(ev["peak_hours"])
        neg_base = float(ev["neg_ratio_base"])
        n = int(ev["volume"])
        ev_posts = []

        for i in range(n):
            frac = i / max(n - 1, 1)
            platform = _pick_platform(ev["id"])
            author = _pick_author(platform["id"])

            # 时间：爆发核 × 昼夜节律
            when = _sample_time(base, span, peak)

            # 情感：负向比例随事件推进抬升（真实舆情是「越滚越负面」），再叠加平台倾向
            if i == 0:
                want = "愤怒" if random.random() < 0.6 else _pick_emotion(ev, platform["id"])
            else:
                neg_p = min(0.92, neg_base + frac * 0.18 + PLATFORM_NEG_BIAS.get(platform["id"], 0.0))
                neg_p = max(0.02, neg_p)
                r = random.random()
                if r < neg_p:
                    want = _pick_emotion(ev, platform["id"])
                elif r < neg_p + (1 - neg_p) * 0.34:
                    want = "中性"
                else:
                    want = "正面"

            is_ocr = random.random() < 0.11
            is_asr = (not is_ocr) and random.random() < 0.11
            media_text = None
            if is_ocr or is_asr:
                # 证据文本（截图文字 / 录音转写）自带情感基调，正文不能与之对撞，
                # 否则会出现「正文在骂、配的录音却在夸」这种一眼假的破绽。
                # 注意：中性证据（如一张检测报告）只是事实陈述，不必限制正文情绪 ——
                # 「晒报告 + 愤怒吐槽」本身就是最真实的表达方式。
                pool = ev["ocr"] if is_ocr else ev["asr"]
                media_text = random.choice(pool)
                ev_label = _score_label(media_text)[0]
                if ev_label == "positive" and want in EMOTION_KEYS:
                    want = "中性"
                elif ev_label == "negative" and want == "正面":
                    want = "中性"

            # 传播链：转发挂到已有帖子（优先挂高影响力账号，符合真实传播规律）
            parent_id = None
            if i > 3 and random.random() < 0.32:
                influ = [p for p in ev_posts[-40:] if p["author_verified"]]
                parent_id = random.choice(influ or ev_posts)["id"]

            # 水军刷量：近似重复内容，供 SimHash 去重演示。
            # 真实热点事件里，搬运号复制转发的内容通常能占到一成左右。
            is_spam = random.random() < 0.10

            post = _make_post(f"p{pid:05d}", ev, when, want, platform, author,
                              parent_id=parent_id, is_spam=is_spam,
                              is_ocr=is_ocr, is_asr=is_asr, media_text=media_text)
            pid += 1

            if is_spam and ev_posts:
                # 刷量优先复制「同平台同事件」的正文，跨平台搬运则剥离原平台标签
                same = [p for p in ev_posts
                        if p["source_id"] == platform["id"] and p["content_type"] == "text"]
                ref = random.choice(same or [p for p in ev_posts if p["content_type"] == "text"] or ev_posts)
                post["content"] = _strip_suffix(ref["content"])
                post["ocr_text"] = ref.get("ocr_text")
                post["transcript_text"] = ref.get("transcript_text")

            ev_posts.append(post)
            posts.append(post)

        events_out.append({
            "id": ev["id"], "title": ev["title"], "category": ev["category"],
            "summary": ev["summary"], "keywords": ev["keywords"],
            "start_time": ev["start_time"], "entities": ev["entities"],
            "demand": ev["demands"][0],
        })

    # 全局按时间排序，更接近真实抓取流水的顺序
    posts.sort(key=lambda p: p["publish_time"])

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # 生成期统计：供导出脚本/自查脚本读取，避免各处硬编码会过期的数字
        "generation_stats": {
            "fallback": _STATS["fallback"],
            "total": _STATS["total"],
            "fallback_rate": round(_STATS["fallback"] / max(_STATS["total"], 1), 4),
            "word_source": WORD_SOURCE,
        },
        "sources": [{"id": p["id"], "name": p["name"], "type": p["type"], "weight": p["weight"]}
                    for p in PLATFORMS],
        "sensitive_words": {
            "high": ["造假", "欺诈", "虚假", "欺骗", "致癌", "危害健康", "维权", "投诉",
                     "曝光", "黑幕", "塌房", "翻车"],
            "medium": ["差评", "失望", "质疑", "担忧", "退款", "缩水", "虚标", "隐患", "事故"],
        },
        "events": events_out,
        "posts": posts,
    }


def main() -> None:
    data = generate()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    posts = data["posts"]
    uniq = len(set(p["content"] for p in posts))
    authors = len(set(p["author"] for p in posts))
    avg_len = sum(len(p["content"]) for p in posts) / max(len(posts), 1)
    print(f"已生成数据集: {OUT_PATH}")
    print(f"事件数: {len(data['events'])}，帖子总数: {len(posts)}")
    print(f"唯一正文: {uniq}（{uniq / max(len(posts), 1):.1%}），账号数: {authors}，"
          f"平均正文长度: {avg_len:.1f} 字")
    print(f"多模态: OCR {sum(1 for p in posts if p['content_type'] == 'ocr')} 条，"
          f"ASR {sum(1 for p in posts if p['content_type'] == 'transcript')} 条，"
          f"水军同质 {sum(1 for p in posts if p['is_spam'])} 条")
    fb_rate = _STATS["fallback"] / max(_STATS["total"], 1)
    print(f"情感兜底率: {_STATS['fallback']}/{_STATS['total']} = {fb_rate:.1%}"
          f"（越低越好，说明骨架本身就能自洽）")
    print(f"情感词表来源: {WORD_SOURCE}")


if __name__ == "__main__":
    main()
