# 文件位置: backend/app/services/monitoring.py
# 功能: 监测配置与处置协同状态（内存单例 + JSON 持久化）。
#       涵盖：监测主题词包、信源通道开关与权重、预警阈值规则、通知渠道、事件处置流转与回应草案。
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import DEFAULT_NOTIFICATION_CHANNELS, settings
from app.data.load_dataset import get_store


class MonitoringState:
    """监测配置与处置状态。修改后持久化到 data/config_state.json，重启可恢复。"""

    def __init__(self):
        self.path = os.path.join(os.path.dirname(__file__), "..", "data", "config_state.json")
        self.state: Dict[str, Any] = {}
        self._load_or_seed()

    def _seed(self) -> None:
        store = get_store()
        topics = []
        for eid, ev in store.events.items():
            topics.append({
                "id": f"topic_{eid}",
                "name": ev.get("title", eid),
                "keywords": ev.get("keywords", []),
                "enabled": True,
            })
        self.state = {
            "topic_packs": topics,
            "source_channels": [
                {"source_id": s["id"], "name": s.get("name"), "type": s.get("type"),
                 "enabled": True, "weight": float(s.get("weight", 1.0))}
                for s in store.sources
            ],
            "threshold_rules": {
                "negative_ratio": settings.risk_negative_ratio_threshold,
                "volume": settings.risk_volume_threshold,
                "burst_multiplier": settings.burst_multiplier,
            },
            "notification_channels": list(DEFAULT_NOTIFICATION_CHANNELS),
            "disposal": {},   # event_id -> {status, handler, notes:[], updated_at}
            "response_drafts": {},  # event_id -> {category, demand, draft, strategy, generated_at}
        }

    def _load_or_seed(self) -> None:
        try:
            if os.path.isfile(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
                return
        except Exception:
            pass
        self._seed()
        self._save()

    def _save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ----- 读取 -----
    def get_state(self) -> Dict[str, Any]:
        return self.state

    def get_disposal(self, event_id: str) -> Dict:
        return self.state["disposal"].get(event_id, {
            "event_id": event_id, "status": "tracking",
            "handler": None, "notes": [], "updated_at": None,
        })

    def get_response_draft(self, event_id: str) -> Optional[Dict]:
        return self.state["response_drafts"].get(event_id)

    # ----- 写入 -----
    def update_sources(self, updates: List[Dict]) -> None:
        by_id = {u["source_id"]: u for u in updates}
        for ch in self.state["source_channels"]:
            u = by_id.get(ch["source_id"])
            if u:
                ch["enabled"] = u.get("enabled", ch["enabled"])
                ch["weight"] = float(u.get("weight", ch["weight"]))
        self._save()

    def update_thresholds(self, rules: Dict) -> None:
        self.state["threshold_rules"].update({k: v for k, v in rules.items() if v is not None})
        # 同步到运行配置（仅内存，便于实时生效）
        if "negative_ratio" in rules:
            settings.risk_negative_ratio_threshold = float(rules["negative_ratio"])
        if "volume" in rules:
            settings.risk_volume_threshold = int(rules["volume"])
        if "burst_multiplier" in rules:
            settings.burst_multiplier = float(rules["burst_multiplier"])
        self._save()

    def update_notifications(self, channels: List[str]) -> None:
        self.state["notification_channels"] = channels
        self._save()

    def upsert_topic(self, topic: Dict) -> None:
        exists = False
        for i, t in enumerate(self.state["topic_packs"]):
            if t["id"] == topic["id"]:
                self.state["topic_packs"][i] = topic
                exists = True
                break
        if not exists:
            self.state["topic_packs"].append(topic)
        self._save()

    def delete_topic(self, topic_id: str) -> None:
        self.state["topic_packs"] = [t for t in self.state["topic_packs"] if t["id"] != topic_id]
        self._save()

    def update_disposal(self, event_id: str, status: str, note: Optional[str],
                       handler: Optional[str]) -> Dict:
        rec = self.state["disposal"].get(event_id, {
            "event_id": event_id, "status": "tracking", "handler": None, "notes": [],
        })
        rec["status"] = status
        if handler:
            rec["handler"] = handler
        if note:
            rec["notes"].append({"note": note, "at": datetime.now().strftime("%Y-%m-%d %H:%M")})
        rec["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.state["disposal"][event_id] = rec
        self._save()
        return rec

    def set_response_draft(self, event_id: str, draft: Dict) -> None:
        draft["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.state["response_drafts"][event_id] = draft
        self._save()


_state: Optional[MonitoringState] = None


def get_monitoring() -> MonitoringState:
    global _state
    if _state is None:
        _state = MonitoringState()
    return _state
