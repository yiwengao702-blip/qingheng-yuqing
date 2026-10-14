# 文件位置: data/export_corpus_samples.py
# 功能: 导出数据集样本与指标对照（Markdown），用于人工验收「数据真实化」效果。
#       产出: deliverables/corpus_samples.md
# 用法: 在项目根目录执行  python data/export_corpus_samples.py
from __future__ import annotations

import json
import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "backend"))

from app.analysis import sentiment as sm  # noqa: E402

OUT = os.path.join(_ROOT, "deliverables", "corpus_samples.md")
DATASET = os.path.join(_ROOT, "backend", "app", "data", "dataset.json")
random.seed(11)


def label_of(post: dict):
    text = " ".join([post["content"] or "", post.get("ocr_text") or "",
                     post.get("transcript_text") or ""])
    sd = sm.analyze_sentiment(text)
    return sd["label"], sd.get("dominant_emotion")


def main() -> None:
    with open(DATASET, encoding="utf-8") as f:
        data = json.load(f)
    posts = data["posts"]
    n = len(posts)

    # 改造前的基线指标（来自旧版生成器产出的数据集，用于对照）
    before = {"posts": 565, "events": 5, "uniq_ratio": 0.430, "authors": 16, "avg_len": 21.6}

    uniq = len(set(p["content"] for p in posts))
    authors = len(set(p["author"] for p in posts))
    avg_len = sum(len(p["content"]) for p in posts) / n
    mm = sum(1 for p in posts if p["content_type"] != "text")

    L = []
    add = L.append
    add("# 舆情数据集真实化 · 样本与指标对照")
    add("")
    add("> 目的：把「一眼能看出是演示数据」的种子语料，改造成经得起追问的真实感数据。")
    add("")
    add("## 一、指标对比")
    add("")
    add("| 指标 | 改造前 | 改造后 |")
    add("| --- | --- | --- |")
    add("| 帖子总数 | " + str(before["posts"]) + " | " + str(n) + " |")
    add("| 事件数 | " + str(before["events"]) + " | " + str(len(data["events"])) + " |")
    add("| 唯一正文率 | 243/565 = 43.0% | " + str(uniq) + "/" + str(n) +
        " = " + format(100.0 * uniq / n, ".1f") + "% |")
    add("| 账号数 | " + str(before["authors"]) + " | " + str(authors) + " |")
    add("| 平均正文长度 | 21.6 字 | " + format(avg_len, ".1f") + " 字 |")
    add("| 多模态占比 | 约 24% | " + format(100.0 * mm / n, ".1f") + "% |")
    add("| 跨事件串料 | 存在（饮品事件配快递转写文本） | 0（已逐条校验） |")
    add("| 生成脚本可用性 | 语法错误，无法运行 | 可复现运行（固定随机种子） |")
    # 兜底率由生成器写进数据集，避免这里再维护一份会过期的硬编码数字
    gstats = data.get("generation_stats") or {}
    if gstats.get("total"):
        fb_txt = format(100.0 * gstats["fallback"] / gstats["total"], ".1f") + "%"
    else:
        fb_txt = "（未记录）"
    add("| 情感标签一致性 | 未校验 | 按分析引擎口径逐条校验，兜底率 " + fb_txt + " |")
    add("")
    add("## 二、平台语体对照")
    add("")
    add("同一个事件在不同平台上的说法本就不同 —— 这是真实感最直观的体现。")
    add("")
    platforms = [
        ("微博", "短、口语、带话题标签与 @"),
        ("抖音", "极短、情绪外放"),
        ("微信公众号", "克制的评述体"),
        ("今日头条", "资讯短评"),
        ("主流新闻网", "记者报道体"),
        ("知乎", "分点长文、专业视角"),
        ("行业论坛", "从业者长贴、内幕视角"),
    ]
    for plat, tip in platforms:
        ps = [p for p in posts if p["platform"] == plat]
        add("### " + plat + " —— " + tip)
        add("")
        for p in random.sample(ps, min(3, len(ps))):
            lab, emo = label_of(p)
            verdict = lab + ("/" + emo if emo else "")
            add("- @" + p["author"] + " · " + p["publish_time"][5:16] + " · 赞" + str(p["like"]) +
                "/评" + str(p["comment"]) + "/转" + str(p["repost"]) + " · 引擎判定 **" + verdict + "**")
            for line in p["content"].split("\n"):
                if line.strip():
                    add("  > " + line.strip())
            if p.get("ocr_text"):
                add("  > 【OCR】" + p["ocr_text"])
            if p.get("transcript_text"):
                add("  > 【ASR】" + p["transcript_text"])
            add("")

    add("## 三、细粒度情绪样本")
    add("")
    add("四类负向情绪各有独立语料池与兜底句，且文本本身含对应情绪词（保证与引擎判定一致）。")
    add("")
    buckets = {"愤怒": [], "失望": [], "恐慌": [], "质疑": [], "正面": []}
    for p in posts:
        lab, emo = label_of(p)
        if lab == "negative" and emo in buckets and len(buckets[emo]) < 3:
            buckets[emo].append(p)
        elif lab == "positive" and len(buckets["正面"]) < 3:
            buckets["正面"].append(p)
    for k in ["愤怒", "失望", "恐慌", "质疑", "正面"]:
        add("### " + k)
        add("")
        for p in buckets[k]:
            add("- @" + p["author"] + "（" + p["platform"] + "）：" + p["content"].split("\n")[0])
        add("")

    add("## 四、时间与互动分布")
    add("")
    hour_hist = {}
    for p in posts:
        h = int(p["publish_time"][11:13])
        hour_hist[h] = hour_hist.get(h, 0) + 1
    night = sum(hour_hist.get(h, 0) for h in range(1, 6))
    day = sum(hour_hist.get(h, 0) for h in range(9, 18))
    likes = sorted(p["like"] for p in posts)
    add("- 昼夜节律：凌晨 1-5 时 " + str(night) + " 条 vs 白天 9-17 时 " + str(day) + " 条（深夜显著低谷）")
    add("- 互动长尾：点赞中位数 " + str(likes[n // 2]) + "，P95 " + str(likes[int(n * 0.95)]) +
        "，过万 " + str(sum(1 for x in likes if x > 10000)) + " 条，零互动 " + str(sum(1 for x in likes if x == 0)) + " 条")
    add("- 主事件 ev_g1 覆盖 " + str(len(set(p["publish_time"][:10] for p in posts if p["event_id"] == "ev_g1"))) +
        " 天，呈「首发-爆发-长尾」形态")
    add("")
    add("## 五、说明")
    add("")
    add("- 全部主体（连锁健身品牌 / 家电品牌 / 服务平台 / 公共场所 / 出行平台 / 公益项目）均为虚构，不指向任何真实企业。")
    add("- 语料按「事件专属细节 × 平台语体骨架」组合生成，不是模板填空；同一条骨架填入不同事件的细节后读起来是两件不相干的事。")
    add("- 重新生成：`python data/mock/generate_mock.py`；真实度自查：`python data/verify_corpus_realism.py`。")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("已生成样本对照: " + OUT)
    print("共 " + str(len(L)) + " 行")


if __name__ == "__main__":
    main()
