# 文件位置: backend/data/mock/generate_mock.py
# 功能: 生成模拟多源舆情数据集 dataset.json（文本 / 图片OCR文本 / 音视频转录文本），
#       覆盖社交媒体/新闻门户/短视频平台/行业论坛，并预置典型事件与传播父子链。
# 用法: 在 backend 目录下执行  python data/mock/generate_mock.py
from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta

random.seed(20260923)  # 固定随机种子，保证演示数据稳定

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PATH = os.path.join(BASE_DIR, "app", "data", "dataset.json")

# ---------------------------------------------------------------------------
# 信源通道（含权重，用于舆情烈度 KOL 维度）
# ---------------------------------------------------------------------------
SOURCES = [
    {"id": "weibo", "name": "微博", "type": "社交媒体", "weight": 1.2},
    {"id": "wechat", "name": "微信公众号", "type": "社交媒体", "weight": 1.0},
    {"id": "douyin", "name": "抖音", "type": "短视频平台", "weight": 1.3},
    {"id": "toutiao", "name": "今日头条", "type": "新闻门户", "weight": 1.1},
    {"id": "xinhua", "name": "主流新闻网", "type": "新闻门户", "weight": 1.0},
    {"id": "zhihu", "name": "知乎", "type": "行业论坛", "weight": 0.9},
    {"id": "forum", "name": "行业论坛", "type": "行业论坛", "weight": 0.8},
]
SOURCE_BY_TYPE: dict = {}
for s in SOURCES:
    SOURCE_BY_TYPE.setdefault(s["type"], []).append(s)

KOL_ACCOUNTS = ["财经观察员", "民生直通车", "消费曝光台", "城市晚报", "行业研究员", "头部测评博主"]
NORMAL_ACCOUNTS = ["小A", "路人甲", "吃瓜群众", "用户_8821", "本地网友", "匿名用户",
                   "热心市民", "数码控", "宝妈日记", "上班族小李"]

SENSITIVE_WORDS = {
    "high": ["造假", "欺诈", "虚假", "欺骗", "致癌", "危害健康", "维权", "投诉", "曝光", "黑幕", "塌房", "翻车"],
    "medium": ["差评", "失望", "质疑", "担忧", "退款", "缩水", "虚标", "隐患", "事故"],
}
REGIONS = ["华北", "华东", "华南", "华中", "西南", "西北", "东北"]

# ---------------------------------------------------------------------------
# 事件模板
# ---------------------------------------------------------------------------
EVENTS = [
    {
        "id": "ev_food", "title": "清甜饮品瓶身异物质量争议", "category": "质量争议",
        "summary": "消费者在社交平台晒出瓶身封口异物照片，质疑饮品卫生安全，引发广泛转发与媒体跟进。",
        "keywords": ["清甜饮品", "异物", "卫生", "食品安全", "瓶身", "封口"],
        "start_time": "2026-09-20 09:00", "volume": 150, "neg_ratio_base": 0.62, "span_hours": 36,
        "entities": [
            {"name": "清甜饮品", "type": "产品"}, {"name": "清甜集团", "type": "机构"},
            {"name": "市场监管局", "type": "机构"}, {"name": "涉事工厂", "type": "机构"},
            {"name": "异物", "type": "事件"}, {"name": "消费者", "type": "人物"},
        ],
        "demand": "要求查明异物来源、公开检测报告、下架问题批次并赔偿",
    },
    {
        "id": "ev_logi", "title": "云速快递爆仓丢件服务纠纷", "category": "服务纠纷",
        "summary": "大促期间云速快递多仓爆仓，大量用户反映签收异常、急件丢失，客服处理缓慢引发集中投诉。",
        "keywords": ["云速快递", "丢件", "爆仓", "签收异常", "客服", "物流"],
        "start_time": "2026-09-18 14:00", "volume": 120, "neg_ratio_base": 0.55, "span_hours": 48,
        "entities": [
            {"name": "云速快递", "type": "机构"}, {"name": "客服", "type": "人物"},
            {"name": "丢件", "type": "事件"}, {"name": "爆仓", "type": "事件"},
            {"name": "消费者", "type": "人物"},
        ],
        "demand": "要求找回急件、透明赔付标准、提升客服响应",
    },
    {
        "id": "ev_ev", "title": "远途新能源续航虚标合规风险", "category": "合规风险",
        "summary": "多位车主实测续航与宣传不符，质疑参数虚标，监管部门约谈引发合规讨论。",
        "keywords": ["远途新能源", "续航", "虚标", "实测", "约谈", "续航里程"],
        "start_time": "2026-09-15 10:00", "volume": 95, "neg_ratio_base": 0.5, "span_hours": 60,
        "entities": [
            {"name": "远途新能源", "type": "机构"}, {"name": "续航虚标", "type": "事件"},
            {"name": "监管", "type": "机构"}, {"name": "车主", "type": "人物"},
        ],
        "demand": "要求公布真实测试标准、整改宣传口径、接受监管核查",
    },
    {
        "id": "ev_pub", "title": "多地菜价上涨民生关注", "category": "公共事件",
        "summary": "受天气与运输影响，多地蔬菜价格短期上涨，居民关注度高，舆情以担忧与求证为主。",
        "keywords": ["菜价", "上涨", "民生", "蔬菜", "物价", "保供"],
        "start_time": "2026-09-12 08:00", "volume": 130, "neg_ratio_base": 0.35, "span_hours": 72,
        "entities": [
            {"name": "菜价", "type": "事件"}, {"name": "保供", "type": "事件"},
            {"name": "发改委", "type": "机构"}, {"name": "居民", "type": "人物"},
        ],
        "demand": "希望稳定供应、透明价格、加强保供",
    },
    {
        "id": "ev_launch", "title": "星河手机新品发布好评", "category": "其他",
        "summary": "星河手机新品发布，舆论以正面体验与测评为主，整体声量正向。",
        "keywords": ["星河手机", "新品", "测评", "体验", "发布"],
        "start_time": "2026-09-21 19:00", "volume": 70, "neg_ratio_base": 0.12, "span_hours": 24,
        "entities": [
            {"name": "星河手机", "type": "产品"}, {"name": "星河科技", "type": "机构"},
        ],
        "demand": "持续收集用户反馈优化体验",
    },
]

POS_TPL = [
    "刚试了{noun}，体验确实不错，点赞支持。",
    "这次{noun}处理很负责，透明解决，值得信赖。",
    "身边的朋友都在用{noun}，整体满意，推荐。",
    "{noun}官方回应挺专业，放心了，好评。",
]
NEU_TPL = [
    "关于{noun}，想了解下具体情况，有知道的吗？",
    "看到{noun}的新闻，先观望一下后续。",
    "{noun}这件事，等官方通报再判断。",
    "求科普：{noun}到底怎么回事？",
]
NEG_TPL = {
    "愤怒": [
        "无语，{noun}这操作太离谱了，欺骗消费者，必须曝光！",
        "{noun}真是坑人，垃圾体验，忍不了，要求退款！",
        "黑心{noun}，敷衍推诿，大家别再上当了。",
    ],
    "失望": [
        "{noun}这次真的让人寒心，落差太大，不再买了。",
        "对{noun}很失望，辜负了信任，遗憾。",
        "{noun}承诺没兑现，心寒，再也不推荐。",
    ],
    "恐慌": [
        "担心{noun}会不会有健康隐患，危害不小，害怕。",
        "看到{noun}的报道有点恐慌，安全隐患要重视。",
        "{noun}这事会不会致癌？担忧，求关注。",
    ],
    "质疑": [
        "质疑{noun}的数据真实性，凭什么这么虚标？求真相。",
        "{noun}到底有没有造假？希望给个说法，别忽悠。",
        "对{noun}的宣传存疑，套路太多，怎么可能这么夸张。",
    ],
}
OCR_TEXTS = [
    "实拍：瓶身封口处有不明黑色异物，已拍照留存。",
    "门店后厨监控截图流出：食材落地后直接装盘。",
    "快递面单合集：连续三单显示已签收但本人未收到。",
]
ASR_TEXTS = [
    "我昨天买的这个饮料，打开以后发现里面飘着一块黑乎乎的东西，喝下去肚子到现在还疼。",
    "客服让我等，等了五天还是没消息，我的急件就这么没了，谁负责？",
    "销售当时跟我说能跑五百公里，结果高速上一半就报警了，这不是骗人是什么。",
]


def _pick_source():
    return random.choice(SOURCES)


def _make_post(pid, ev, t, label, emotion=None, is_ocr=False, is_asr=False,
               is_spam=False, kol=False, parent_id=None):
    src = _pick_source()
    noun = ev["keywords"][0]
    if label == "positive":
        content = random.choice(POS_TPL).format(noun=noun)
    elif label == "neutral":
        content = random.choice(NEU_TPL).format(noun=noun)
    else:
        emotion = emotion or random.choice(["愤怒", "失望", "恐慌", "质疑"])
        content = random.choice(NEG_TPL[emotion]).format(noun=noun)
    if label == "negative" and random.random() < 0.5:
        content += random.choice(SENSITIVE_WORDS["high"] + SENSITIVE_WORDS["medium"])

    ctype = "text"
    ocr_text = None
    transcript_text = None
    if is_ocr:
        ctype = "ocr"
        ocr_text = random.choice(OCR_TEXTS)
    elif is_asr:
        ctype = "transcript"
        transcript_text = random.choice(ASR_TEXTS)

    author = random.choice(KOL_ACCOUNTS) if kol else random.choice(NORMAL_ACCOUNTS)
    weight = round(random.uniform(0.85, 0.98), 2) if kol else round(random.uniform(0.2, 0.6), 2)
    base = 1500 if kol else random.randint(5, 300)
    return {
        "id": pid,
        "event_id": ev["id"],
        "source_id": src["id"],
        "source_type": src["type"],
        "platform": src["name"],
        "author": author,
        "author_weight": weight,
        "content": content,
        "content_type": ctype,
        "ocr_text": ocr_text,
        "transcript_text": transcript_text,
        "publish_time": t.strftime("%Y-%m-%d %H:%M:%S"),
        "repost": random.randint(0, base),
        "comment": random.randint(0, base),
        "like": random.randint(0, base * 2),
        "region": random.choice(REGIONS),
        "parent_id": parent_id,
        "is_spam": is_spam,
    }


def generate():
    posts = []
    pid = 0
    events_out = []
    for ev in EVENTS:
        base = datetime.strptime(ev["start_time"], "%Y-%m-%d %H:%M")
        span = ev["span_hours"]
        neg_base = ev["neg_ratio_base"]
        n = ev["volume"]
        origin = _make_post(f"p{pid:05d}", ev, base + timedelta(minutes=random.randint(0, 30)),
                            "negative", emotion="愤怒", kol=random.random() < 0.4)
        pid += 1
        posts.append(origin)
        for i in range(1, n):
            frac = i / max(n - 1, 1)
            t = base + timedelta(hours=span * (frac ** 1.6))
            r = random.random()
            neg_p = min(0.9, neg_base + frac * 0.2)
            if r < neg_p:
                label = "negative"
            elif r < neg_p + (1 - neg_p) * 0.4:
                label = "neutral"
            else:
                label = "positive"
            kol = random.random() < 0.12
            is_ocr = random.random() < 0.12
            is_asr = (not is_ocr and random.random() < 0.12)
            parent_id = None
            if i > 2 and random.random() < 0.55 and posts:
                parent_id = random.choice(posts[-8:])["id"]
            is_spam = random.random() < 0.07
            p = _make_post(f"p{pid:05d}", ev, t, label, is_ocr=is_ocr, is_asr=is_asr,
                           is_spam=is_spam, kol=kol, parent_id=parent_id)
            if is_spam and posts:
                ref = random.choice(posts)
                p["content"] = ref["content"]
                p["ocr_text"] = ref.get("ocr_text")
                p["transcript_text"] = ref.get("transcript_text")
            pid += 1
            posts.append(p)
        events_out.append({
            "id": ev["id"], "title": ev["title"], "category": ev["category"],
            "summary": ev["summary"], "keywords": ev["keywords"],
            "start_time": ev["start_time"], "entities": ev["entities"], "demand": ev["demand"],
        })

    data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sources": SOURCES,
        "sensitive_words": SENSITIVE_WORDS,
        "events": events_out,
        "posts": posts,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已生成数据集: {OUT_PATH}")
    print(f"事件数: {len(events_out)}，帖子总数: {len(posts)}")


if __name__ == "__main__":
    generate()
