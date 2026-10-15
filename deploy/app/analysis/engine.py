# 文件位置: backend/app/analysis/engine.py
# 功能: 分析引擎编排 —— 启动时一次性计算全量帖子的情感/情绪/SimHash 去重/风险/实体，
#       并提供态势总览、事件列表、事件详情、监测流筛选与预警列表。结果缓存为单例。
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Optional

from app.config import settings
from app.data.clean import hamming_distance, simhash, tokenize
from app.data.load_dataset import DatasetStore, get_store
from app.analysis import sentiment as sent_mod
from app.analysis.cluster import cluster_viewpoints
from app.analysis.entity_graph import build_entity_graph
from app.analysis.keywords import extract_entities_in_text, hotwords_from_posts
from app.analysis.llm_sim import generate_pr_strategy, narrative_sections
from app.analysis.propagation import interaction, parse_time
from app.analysis.risk import event_intensity, post_risk_grade


def _post_text(post: dict) -> str:
    parts = [post.get("content", "") or ""]
    if post.get("ocr_text"):
        parts.append(post["ocr_text"])
    if post.get("transcript_text"):
        parts.append(post["transcript_text"])
    return " ".join(parts)


class AnalysisEngine:
    """分析引擎：加载数据集并计算所有派生指标。"""

    def __init__(self, store: DatasetStore):
        self.store = store
        self.dedup_stats: Dict = {"total": 0, "unique": 0, "duplicates": 0}
        self._compute()

    # ------------------------------------------------------------------
    # 全量计算（启动时执行一次）
    # ------------------------------------------------------------------
    def _compute(self) -> None:
        posts = self.store.posts
        hi_words = set(self.store.sensitive_words.get("high", []))
        mid_words = set(self.store.sensitive_words.get("medium", []))

        # 1) 逐帖情感、情绪、实体、敏感词、SimHash、风险等级
        for p in posts:
            text = _post_text(p)
            sd = sent_mod.analyze_sentiment(text)
            p["sentiment"] = sd["label"]
            p["sentiment_score"] = sd["score"]
            p["sentiment_detail"] = sd
            p["simhash"] = simhash(text)
            ev = self.store.get_event(p.get("event_id"))
            ents = extract_entities_in_text(text, ev.get("entities", [])) if ev else []
            p["entities"] = ents
            p["sensitive_hit"] = any(w in text for w in hi_words)
            p["sensitive_medium"] = any(w in text for w in mid_words)
            p["risk_grade"] = post_risk_grade(p)
            p["keywords"] = tokenize(text)[:12]

        # 2) SimHash 去重：按时间排序，汉明距离 <=3 视为同质重复，保留最早为权威
        ordered = sorted(posts, key=lambda x: parse_time(x.get("publish_time")) or __import__("datetime").datetime.max)
        for p in posts:
            p["is_duplicate"] = False
            p["duplicate_of"] = None
            p["dup_merged"] = 0
        canon: List[dict] = []
        for p in ordered:
            fp = p["simhash"]
            merged = False
            for c in canon:
                if hamming_distance(fp, c["simhash"]) <= 3:
                    p["is_duplicate"] = True
                    p["duplicate_of"] = c["id"]
                    c["dup_merged"] += 1
                    merged = True
                    break
            if not merged:
                canon.append(p)
        self.dedup_stats = {
            "total": len(posts),
            "unique": len(canon),
            "duplicates": len(posts) - len(canon),
        }

        # 3) 事件级聚合缓存
        self._event_cache: Dict[str, dict] = {}
        for eid, ev in self.store.events.items():
            self._event_cache[eid] = self._compute_event(ev)

        # 4) 预警列表
        self._alerts = self._compute_alerts()

    def _compute_event(self, ev: dict) -> dict:
        posts = [p for p in self.store.posts
                 if p.get("event_id") == ev["id"] and not p.get("is_duplicate")]
        n = len(posts)
        sent_counter = Counter(p.get("sentiment", "neutral") for p in posts)
        emotion_dist = sent_mod.emotion_distribution(posts)
        risk = event_intensity(posts, ev)
        # 时间趋势（小时）
        trend: Dict[str, Dict] = defaultdict(lambda: {"volume": 0, "negative": 0})
        for p in posts:
            t = parse_time(p.get("publish_time"))
            if not t:
                continue
            k = t.strftime("%Y-%m-%d %H:00")
            trend[k]["volume"] += 1
            if p.get("sentiment") == "negative":
                trend[k]["negative"] += 1
        trend_list = [
            {"hour": k, "volume": v["volume"], "negative": v["negative"]}
            for k, v in sorted(trend.items())
        ]
        return {
            "event_id": ev["id"],
            "title": ev.get("title"),
            "category": ev.get("category"),
            "summary": ev.get("summary"),
            "start_time": ev.get("start_time"),
            "volume": n,
            "sentiment": {
                "positive": sent_counter.get("positive", 0),
                "neutral": sent_counter.get("neutral", 0),
                "negative": sent_counter.get("negative", 0),
                "negative_ratio": round(sent_counter.get("negative", 0) / n, 3) if n else 0,
            },
            "emotion": emotion_dist,
            "risk": risk,
            "trend": trend_list,
            "sources": Counter(p.get("source_type") for p in posts),
        }

    def _compute_alerts(self) -> List[dict]:
        alerts: List[dict] = []
        cfg = settings
        # 突发：全量非重复帖子按小时负向声量，环比超 burst_multiplier 触发
        hourly: Dict[str, int] = defaultdict(int)
        for p in self.store.posts:
            if p.get("is_duplicate"):
                continue
            if p.get("sentiment") == "negative":
                t = parse_time(p.get("publish_time"))
                if t:
                    hourly[t.strftime("%Y-%m-%d %H:00")] += 1
        hours_sorted = sorted(hourly.keys())
        for i in range(1, len(hours_sorted)):
            prev_h, cur_h = hours_sorted[i - 1], hours_sorted[i]
            prev_v, cur_v = hourly[prev_h], hourly[cur_h]
            if prev_v > 0 and cur_v >= cfg.burst_multiplier * prev_v and cur_v >= 5:
                level = "S" if cur_v >= 30 else ("A" if cur_v >= 15 else "B")
                alerts.append({
                    "id": f"burst_{cur_h}",
                    "level": level,
                    "type": "突发激增",
                    "event_id": None,
                    "title": f"{cur_h} 负向声量环比激增",
                    "detail": f"负向声量由 {prev_v} 升至 {cur_v}（环比 {round(cur_v / prev_v, 1)}×），触发突发预警。",
                    "time": cur_h,
                })
        # 事件级：高危敏感词命中 + KOL 或高互动，以及风险等级 S/A
        for eid, ev in self.store.events.items():
            posts = [p for p in self.store.posts
                     if p.get("event_id") == eid and not p.get("is_duplicate")]
            sens = [p for p in posts if p.get("sensitive_hit")
                    and (interaction(p) >= 200 or p.get("author_weight", 0) >= 0.8)]
            if sens:
                p0 = max(sens, key=interaction)
                level = "S" if interaction(p0) >= 1000 else "A"
                alerts.append({
                    "id": f"sens_{eid}",
                    "level": level,
                    "type": "敏感词命中",
                    "event_id": eid,
                    "title": f"「{ev.get('title')}」命中高危敏感词",
                    "detail": f"用户「{p0.get('author')}」({p0.get('platform')}) 发布内容命中高危敏感词，"
                              f"互动量 {interaction(p0)}，需重点核实。",
                    "time": p0.get("publish_time"),
                })
            risk = event_intensity(posts, ev)
            if risk["grade"] in ("S", "A"):
                alerts.append({
                    "id": f"risk_{eid}",
                    "level": risk["grade"],
                    "type": "事件风险",
                    "event_id": eid,
                    "title": f"「{ev.get('title')}」风险等级 {risk['grade']}",
                    "detail": f"舆情烈度指数 {risk['intensity']}，主要驱动："
                              f"传播速度 {risk['factors']['spread_speed']} 条/小时、"
                              f"互动 {risk['factors']['interaction']}、"
                              f"KOL 权重 {risk['factors']['kol_max']}。",
                    "time": ev.get("start_time"),
                })
        alerts.sort(key=lambda a: a.get("time") or "", reverse=True)
        return alerts

    # ------------------------------------------------------------------
    # 对外查询
    # ------------------------------------------------------------------
    def overview(self) -> Dict:
        posts = [p for p in self.store.posts if not p.get("is_duplicate")]
        n = len(posts)
        sent = Counter(p.get("sentiment", "neutral") for p in posts)
        src = Counter(p.get("source_type") for p in posts)
        rg = Counter(p.get("risk_grade") for p in posts)
        # 趋势（全量小时）
        trend: Dict[str, Dict] = defaultdict(lambda: {"volume": 0, "negative": 0})
        for p in posts:
            t = parse_time(p.get("publish_time"))
            if t:
                k = t.strftime("%Y-%m-%d %H:00")
                trend[k]["volume"] += 1
                if p.get("sentiment") == "negative":
                    trend[k]["negative"] += 1
        trend_list = [{"hour": k, "volume": v["volume"], "negative": v["negative"]}
                      for k, v in sorted(trend.items())]
        # 全量细粒度情绪分布（愤怒/失望/恐慌/质疑/其他负向/非负向），供大盘「细粒度情绪分布」卡片使用
        emotion_dist = sent_mod.emotion_distribution(posts)
        return {
            "total_volume": n,
            "sentiment": {
                "positive": sent.get("positive", 0),
                "neutral": sent.get("neutral", 0),
                "negative": sent.get("negative", 0),
            },
            "emotion": emotion_dist,
            "source_distribution": dict(src),
            "risk_distribution": dict(rg),
            "trend": trend_list,
            "hotwords": hotwords_from_posts(posts, 40),
            "dedup": self.dedup_stats,
            "event_count": len(self.store.events),
            "alert_count": len(self._alerts),
        }

    def event_list(self) -> List[dict]:
        out = []
        for eid, ev in self.store.events.items():
            c = self._event_cache.get(eid, {})
            out.append({
                "event_id": eid,
                "title": ev.get("title"),
                "category": ev.get("category"),
                "summary": ev.get("summary"),
                "volume": c.get("volume", 0),
                "negative_ratio": c.get("sentiment", {}).get("negative_ratio", 0),
                "grade": c.get("risk", {}).get("grade", "C"),
                "intensity": c.get("risk", {}).get("intensity", 0),
                "start_time": ev.get("start_time"),
            })
        out.sort(key=lambda x: (x["grade"] != "S", x["grade"] != "A", -x["intensity"]))
        return out

    def event_detail(self, event_id: str) -> Dict:
        ev = self.store.get_event(event_id)
        if not ev:
            return {}
        posts = [p for p in self.store.posts
                 if p.get("event_id") == event_id and not p.get("is_duplicate")]
        c = self._event_cache.get(event_id, {})
        viewpoints = cluster_viewpoints(posts)
        prop = self._propagation_for(event_id)
        graph = build_entity_graph(posts, ev)
        # 核心诉求：取规模最大的负面观点簇关键词
        core_demand = ""
        for v in viewpoints:
            if v["sentiment_dist"]["negative"] >= v["sentiment_dist"]["positive"]:
                core_demand = "、".join(v["keywords"][:4])
                break
        analysis = {
            "event_id": event_id,
            "title": ev.get("title"),
            "category": ev.get("category"),
            "summary": ev.get("summary"),
            "volume": len(posts),
            "sentiment": c.get("sentiment", {}),
            "emotion": c.get("emotion", {}),
            "dominant_emotion": max(c.get("emotion", {}).items(), key=lambda x: x[1])[0]
            if c.get("emotion") else None,
            "risk": c.get("risk", {}),
            "propagation": prop,
            "viewpoints": viewpoints,
            "entity_graph": graph,
            "core_demand": core_demand,
            "trend": c.get("trend", []),
            "top_posts": [
                {
                    "id": p["id"], "author": p.get("author"), "platform": p.get("platform"),
                    "source_type": p.get("source_type"), "content_type": p.get("content_type"),
                    "sentiment": p.get("sentiment"), "risk_grade": p.get("risk_grade"),
                    "interaction": interaction(p), "publish_time": p.get("publish_time"),
                    "content": (p.get("content") or "")[:200],
                    "ocr_text": p.get("ocr_text"), "transcript_text": p.get("transcript_text"),
                    "entities": p.get("entities"),
                }
                for p in sorted(posts, key=interaction, reverse=True)[:10]
            ],
        }
        return analysis

    def _propagation_for(self, event_id: str) -> Dict:
        posts = [p for p in self.store.posts
                 if p.get("event_id") == event_id and not p.get("is_duplicate")]
        from app.analysis.propagation import build_propagation
        return build_propagation(posts)

    def feed(self, event_id: Optional[str] = None, source_types: Optional[List[str]] = None,
             sentiments: Optional[List[str]] = None, risk_grades: Optional[List[str]] = None,
             q: Optional[str] = None, time_from: Optional[str] = None, time_to: Optional[str] = None,
             page: int = 1, page_size: int = 20) -> Dict:
        posts = [p for p in self.store.posts if not p.get("is_duplicate")]
        tf = parse_time(time_from)
        tt = parse_time(time_to)
        if event_id:
            posts = [p for p in posts if p.get("event_id") == event_id]
        if source_types:
            posts = [p for p in posts if p.get("source_type") in source_types]
        if sentiments:
            posts = [p for p in posts if p.get("sentiment") in sentiments]
        if risk_grades:
            posts = [p for p in posts if p.get("risk_grade") in risk_grades]
        if q:
            posts = [p for p in posts if q in _post_text(p)]
        if tf:
            posts = [p for p in posts if (parse_time(p.get("publish_time")) or __import__("datetime").datetime.max) >= tf]
        if tt:
            posts = [p for p in posts if (parse_time(p.get("publish_time")) or __import__("datetime").datetime.min) <= tt]
        posts.sort(key=lambda p: p.get("publish_time") or "", reverse=True)
        total = len(posts)
        start = (page - 1) * page_size
        page_items = posts[start:start + page_size]
        items = [
            {
                "id": p["id"], "event_id": p.get("event_id"),
                "author": p.get("author"), "platform": p.get("platform"),
                "source_type": p.get("source_type"), "content_type": p.get("content_type"),
                "sentiment": p.get("sentiment"), "risk_grade": p.get("risk_grade"),
                "author_weight": p.get("author_weight"), "interaction": interaction(p),
                "publish_time": p.get("publish_time"), "region": p.get("region"),
                "entities": p.get("entities"), "sensitive_hit": p.get("sensitive_hit"),
                "content": (p.get("content") or "")[:240],
                "ocr_text": p.get("ocr_text"), "transcript_text": p.get("transcript_text"),
            }
            for p in page_items
        ]
        return {"total": total, "page": page, "page_size": page_size, "items": items}

    def get_alerts(self) -> List[dict]:
        return self._alerts

    def build_report(self, event_id: str) -> Dict:
        analysis = self.event_detail(event_id)
        ev = self.store.get_event(event_id)
        narr = narrative_sections(ev, analysis)
        pr = generate_pr_strategy(ev, analysis)
        from app.analysis.report import assemble_report
        return assemble_report(ev, analysis, narr, pr)

    def build_periodic_report(self, kind: str = "daily") -> Dict:
        """生成周期简报（日报 / 周报）：汇总全网态势、重点事件排行与预警进展。"""
        from app.analysis.report import assemble_periodic
        return assemble_periodic(self.overview(), self.event_list(), self.get_alerts(), kind)


# 模块级单例
_engine: Optional[AnalysisEngine] = None


def get_engine() -> AnalysisEngine:
    global _engine
    if _engine is None:
        _engine = AnalysisEngine(get_store())
    return _engine


if __name__ == "__main__":
    # 本文件是 app 包的内部模块，不允许作为脚本直接运行：
    # 直接运行时 sys.path[0] 是本文件所在目录，backend/ 不在搜索路径里，
    # `from app.config import settings` 必然报 ModuleNotFoundError。
    # 统一从服务入口启动：cd D:/Public Opinion/deploy 后执行 python run.py
    print("【提示】engine.py 是 app 包的内部模块，不能直接运行。")
    print("正确启动方式：cd D:/Public Opinion/deploy 后执行  python run.py")
    print("启动后本地预览：http://127.0.0.1:8001/  （账号 admin；口令由 ADMIN_PASSWORD 环境变量指定，未设置则启动期随机生成并打印于后端日志）")
