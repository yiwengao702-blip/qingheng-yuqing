# 文件位置: backend/app/data/load_dataset.py
# 功能: 数据集仓储（内存单例）。加载 dataset.json，提供事件/帖子访问与多维筛选。
from __future__ import annotations

import json
from typing import Dict, List, Optional

from app.config import settings


class DatasetStore:
    """加载模拟多源舆情数据集，提供只读访问与多维筛选。"""

    def __init__(self, path: str | None = None):
        self.path = path or settings.dataset_path
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.events: Dict[str, dict] = {e["id"]: e for e in data.get("events", [])}
        self.posts: List[dict] = data.get("posts", [])
        self.sources: List[dict] = data.get("sources", [])
        self.sensitive_words: Dict[str, List[str]] = data.get("sensitive_words", {})
        self.generated_at: str = data.get("generated_at", "")
        self.source_map: Dict[str, dict] = {s["id"]: s for s in self.sources}

    def get_event(self, event_id: str) -> Optional[dict]:
        return self.events.get(event_id)

    def get_post(self, post_id: str) -> Optional[dict]:
        for p in self.posts:
            if p["id"] == post_id:
                return p
        return None

    def posts_of_event(self, event_id: str) -> List[dict]:
        return [p for p in self.posts if p.get("event_id") == event_id]


# 模块级单例（进程内唯一）
_store: Optional[DatasetStore] = None


def get_store() -> DatasetStore:
    global _store
    if _store is None:
        _store = DatasetStore()
    return _store
