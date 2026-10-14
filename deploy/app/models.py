# 文件位置: backend/app/models.py
# 功能: API 数据模型（Pydantic）。请求体强校验；响应体以强类型为主，复杂分析结构用 dict 透传。
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    """注册请求。字段长度/规则由服务层校验，以便返回统一的中文错误信息。"""
    username: str
    password: str
    name: Optional[str] = None
    role: str = "analyst"


class UserOut(BaseModel):
    username: str
    name: str
    role: str
    permissions: List[str]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------
class SentimentLabel(str, Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class RiskGrade(str, Enum):
    S = "S"  # 特别重大
    A = "A"  # 重大
    B = "B"  # 较大
    C = "C"  # 一般


# ---------------------------------------------------------------------------
# 监测配置（请求体）
# ---------------------------------------------------------------------------
class TopicPack(BaseModel):
    id: str
    name: str
    keywords: List[str]
    enabled: bool = True


class SourceChannelUpdate(BaseModel):
    source_id: str
    enabled: bool = True
    weight: float = Field(1.0, ge=0.0, le=5.0)


class ThresholdRules(BaseModel):
    negative_ratio: float = Field(0.45, ge=0.0, le=1.0)
    volume: int = Field(200, ge=0)
    burst_multiplier: float = Field(2.5, ge=1.0)


class NotificationChannels(BaseModel):
    channels: List[str]


# ---------------------------------------------------------------------------
# 处置协同
# ---------------------------------------------------------------------------
class DisposalUpdate(BaseModel):
    status: str  # tracking / verified / rumor_refuted / ignored / handled
    note: Optional[str] = None
    handler: Optional[str] = None


class ResponseDraftRequest(BaseModel):
    # 事件 ID 以路径参数 /events/{event_id}/response-draft 为准，
    # body 中可不传，故设为可选（否则前端发 {} 会触发 422 校验失败）。
    event_id: Optional[str] = None
    category: Optional[str] = None
    demand: Optional[str] = None
    regenerate: bool = False
