# 文件位置: data/verify_corpus_realism.py
# 功能: 模拟数据集「真实度」自查。
#       数据集是演示的门面，一眼假的数据会让整套分析能力都失去说服力。
#       本脚本用真实分析引擎与语料定义做交叉校验，覆盖：
#         1) 文本可读性（换行是否正确落盘、有无字面转义残留）
#         2) 跨事件串料（细节 / OCR / ASR 是否严格属于本事件）
#         3) 情感一致性（引擎实际判定的负向占比与情绪分布是否合理）
#         4) 互动量合理性（长尾分布、爆款、点赞/评论/转发关系）
#         5) 时间分布（爆发峰值位置、昼夜节律、分钟聚集）
#         6) 体量与多样性（唯一正文率、账号数、平台分布、多模态占比）
# 用法: 在项目根目录执行  python data/verify_corpus_realism.py
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_HERE, "mock"))
sys.path.insert(0, os.path.join(_ROOT, "backend"))

from corpus_events import EVENTS  # noqa: E402

from app.analysis import sentiment as sent_mod  # noqa: E402

DATASET = os.path.join(_ROOT, "backend", "app", "data", "dataset.json")

results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


with open(DATASET, encoding="utf-8") as f:
    data = json.load(f)
posts = data["posts"]
EV = {e["id"]: e for e in EVENTS}

print("=" * 72)
print("一、文本可读性")
# 字面 "\n" 残留说明转义写错了，前端会显示成一行乱码
literal_esc = [p for p in posts if "\\n" in p["content"]]
check("正文无字面 \\n 残留（换行已正确落盘）", not literal_esc,
      f"命中 {len(literal_esc)} 条" if literal_esc else "ok")
multi_line = sum(1 for p in posts if "\n" in p["content"])
check("存在多段文本（长文换行生效）", multi_line > 20, f"多段正文 {multi_line} 条")

print("\n二、跨事件串料")
# 事件专属内容不得出现在其他事件的帖子里（旧版 bug：饮品事件配快递转写）
leak = defaultdict(list)
for p in posts:
    ev = EV.get(p["event_id"])
    if not ev:
        continue
    others = [e for eid, e in EV.items() if eid != p["event_id"]]
    body = " ".join([p["content"] or "", p.get("ocr_text") or "", p.get("transcript_text") or ""])
    for o in others:
        for pool_name in ("details", "ocr", "asr"):
            for item in o.get(pool_name) and o[pool_name] or []:
                if item and item in body:
                    leak[p["event_id"]].append(f"{o['id']}/{pool_name}")
check("无线索从其他事件串入", not leak,
      f"串料事件 {dict((k, len(v)) for k, v in leak.items())}" if leak else "ok")

# 每条 OCR/ASR 必须能在本事件池里找到出处
bad_src = 0
for p in posts:
    ev = EV.get(p["event_id"])
    if not ev:
        continue
    if p.get("ocr_text") and p["ocr_text"] not in ev["ocr"]:
        bad_src += 1
    if p.get("transcript_text") and p["transcript_text"] not in ev["asr"]:
        bad_src += 1
check("多模态文本均可溯源到本事件池", bad_src == 0, f"异常 {bad_src} 条")

print("\n三、情感一致性（用真实引擎计算）")
neg_by_event = {}
emotion_total = Counter()
for p in posts:
    text = " ".join([p["content"] or "", p.get("ocr_text") or "", p.get("transcript_text") or ""])
    sd = sent_mod.analyze_sentiment(text)
    neg_by_event.setdefault(p["event_id"], [0, 0])
    neg_by_event[p["event_id"]][0] += (1 if sd["label"] == "negative" else 0)
    neg_by_event[p["event_id"]][1] += 1
    if sd["label"] == "negative" and sd.get("dominant_emotion"):
        emotion_total[sd["dominant_emotion"]] += 1

drift = []
for ev_id, (neg, total) in neg_by_event.items():
    actual = neg / max(total, 1)
    expect = EV[ev_id]["neg_ratio_base"]
    if abs(actual - expect) > 0.22:
        drift.append(f"{ev_id} 实际{actual:.2f}/预期{expect:.2f}")
check("各事件负向占比贴近设定", not drift, "；".join(drift) if drift else "偏差均在 0.22 内")

check("四种负向情绪均有实际样本", len(emotion_total) == 4,
      "  ".join(f"{k}={v}" for k, v in emotion_total.most_common()))

# 正文与证据文本（OCR 截图文字 / ASR 录音转写）不能情感对撞：
# 「正文在骂、配的录音却在夸」是一眼假的典型破绽。
clash = []
for p in posts:
    media = p.get("ocr_text") or p.get("transcript_text")
    if not media:
        continue
    body_lab = sent_mod.analyze_sentiment(p["content"])["label"]
    media_lab = sent_mod.analyze_sentiment(media)["label"]
    if {body_lab, media_lab} == {"positive", "negative"}:
        clash.append(p["id"])
check("正文与证据文本基调不矛盾", len(clash) == 0,
      f"对撞 {len(clash)} 条: {clash[:5]}" if clash else "ok")

# 正面事件不该被负面淹没，负面事件不该一片骂声
launch = neg_by_event.get("ev_g6", [0, 1])
check("正面事件（公益透明）负向占比 < 0.3", launch[0] / launch[1] < 0.3,
      f"负向 {launch[0] / launch[1]:.2f}")
food = neg_by_event.get("ev_g1", [0, 1])
check("主事件（健身闭店退费纠纷）负向占比 > 0.5", food[0] / food[1] > 0.5,
      f"负向 {food[0] / food[1]:.2f}")

print("\n四、互动量合理性")
likes = sorted(p["like"] for p in posts)
n = len(likes)
median = likes[n // 2]
p95 = likes[int(n * 0.95)]
zeros = sum(1 for x in likes if x == 0)
hot = sum(1 for x in likes if x > 10000)
check("点赞呈长尾分布（中位数远小于 P95）", median < p95 / 5,
      f"中位数 {median} / P95 {p95} / 过万 {hot} 条")
check("存在零互动与低互动样本（真实长尾）", zeros > 0 or median < 60,
      f"零互动 {zeros} 条，中位数 {median}")
geo = sum(1 for p in posts if p["like"] >= p["comment"] >= p["repost"])
check("多数帖子满足 点赞≥评论≥转发", geo / n > 0.75, f"{geo}/{n} = {geo / n:.1%}")
by_plat = defaultdict(list)
for p in posts:
    by_plat[p["platform"]].append(p["like"])
check("抖音平均点赞高于新闻门户", 
      (sum(by_plat.get("抖音", [0])) / max(len(by_plat.get("抖音", [1])), 1))
      > (sum(by_plat.get("主流新闻网", [0])) / max(len(by_plat.get("主流新闻网", [1])), 1)),
      f"抖音 {sum(by_plat.get('抖音', [0])) / max(len(by_plat.get('抖音', [1])), 1):.0f} vs "
      f"新闻网 {sum(by_plat.get('主流新闻网', [0])) / max(len(by_plat.get('主流新闻网', [1])), 1):.0f}")

print("\n五、时间分布")
from datetime import datetime  # noqa: E402
hour_hist = Counter()
for p in posts:
    dt = datetime.strptime(p["publish_time"], "%Y-%m-%d %H:%M:%S")
    hour_hist[dt.hour] += 1
night = sum(hour_hist[h] for h in range(1, 6))
day = sum(hour_hist[h] for h in range(9, 18))
check("深夜声量显著低于白天（昼夜节律）", night < day * 0.5,
      f"1-5 时 {night} 条 vs 9-17 时 {day} 条")
minute_hit = sum(1 for p in posts
                 if datetime.strptime(p["publish_time"], "%Y-%m-%d %H:%M:%S").minute in
                 (0, 1, 2, 3, 4, 5, 28, 29, 30, 31, 32, 55, 56, 57, 58, 59))
check("整点/半点存在聚集（非均匀分布）", minute_hit / n > 0.40,
      f"{minute_hit}/{n} = {minute_hit / n:.1%}")

for ev_id in ("ev_g1", "ev_g3"):
    ev0 = EV[ev_id]
    base = datetime.strptime(ev0["start_time"], "%Y-%m-%d %H:%M")
    hs = [datetime.strptime(p["publish_time"], "%Y-%m-%d %H:%M:%S") for p in posts
          if p["event_id"] == ev_id]
    diff = [(h - base).total_seconds() / 3600 for h in hs]
    peak_bucket = Counter(int(d // 2) * 2 for d in diff if 0 <= d <= 40)
    peak_at = peak_bucket.most_common(1)[0][0] if peak_bucket else -1
    check(f"{ev_id} 声量峰值落在设定区间附近", 0 <= peak_at <= ev0["span_hours"],
          f"实际峰值区间 {peak_at}-{peak_at + 2}h，设定 peak={ev0['peak_hours']}h")
    check(f"{ev_id} 存在跨天长尾（非集中一天）",
          len({h.date() for h in hs}) >= 2, f"覆盖 {len({h.date() for h in hs})} 天")

print("\n六、体量与多样性")
uniq = len(set(p["content"] for p in posts))
authors = len(set(p["author"] for p in posts))
avg_len = sum(len(p["content"]) for p in posts) / n
multimodal = sum(1 for p in posts if p["content_type"] != "text")
check("唯一正文率 > 80%", uniq / n > 0.80, f"{uniq}/{n} = {uniq / n:.1%}")
check("账号数 > 40", authors > 40, f"{authors} 个")
check("平均正文长度 > 40 字", avg_len > 40, f"{avg_len:.1f} 字")
check("多模态占比 15%~30%", 0.15 < multimodal / n < 0.30, f"{multimodal}/{n} = {multimodal / n:.1%}")
check("事件数 10", len(data["events"]) == 10, f"{len(data['events'])} 个")
plat = Counter(p["platform"] for p in posts)
check("平台分布覆盖 7 个信源", len(plat) == 7,
      "  ".join(f"{k}:{v}" for k, v in plat.most_common()))
# 同一账号应在本事件中多次出现（真实用户会连续发帖），而不是全员只出现一次
repeat = sum(1 for a, c in Counter(p["author"] for p in posts).items() if c >= 3)
check("多数账号会重复出现（非一人一号一次性）", repeat / authors > 0.5,
      f"{repeat}/{authors} 个账号发帖 ≥3 条")

print("\n七、样本抽查（人工可读性）")
sample_bad = [p for p in posts if len(p["content"]) < 8]
check("无过短异常正文", not sample_bad, f"{len(sample_bad)} 条")

print("\n" + "=" * 72)
passed = sum(1 for _, ok, _ in results if ok)
print(f"===== 数据真实度自查: {passed}/{len(results)} PASS =====")
if passed != len(results):
    print("失败项: " + " / ".join(name for name, ok, _ in results if not ok))
    sys.exit(1)
