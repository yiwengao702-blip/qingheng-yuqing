# 文件位置: backend/app/config.py
# 功能: 集中式配置管理（dataclass 单例）。所有配置来自环境变量，启动时集中校验、快速失败。
from __future__ import annotations

import os
import secrets
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List

_logger = logging.getLogger(__name__)


def _generate_ephemeral_secret() -> str:
    """SECRET_KEY 未设置时生成临时随机密钥（仅单实例演示，重启失效）。"""
    key = secrets.token_hex(32)
    _logger.warning(
        "SECRET_KEY 未设置，已生成临时随机密钥（仅适用于单实例演示，进程重启后旧令牌失效）。"
        "多副本生产部署请通过环境变量 SECRET_KEY 注入同一把强密钥。"
    )
    return key


# ---------------------------------------------------------------------------
# 角色与权限矩阵（RBAC）
# ---------------------------------------------------------------------------
# 三类角色职责（来自需求）：
#   系统管理员 admin   —— 配置信源通道、预警分级阈值、通知渠道、系统运行配置
#   舆情分析师 analyst —— 创建/调整监测主题、查阅舆情动态、事件研判与观点下钻、生成导出报告
#   公关运营人员 pr    —— 接收高危预警、查看传播脉络与核心观点、采纳公关建议、流转处置工单
ROLE_PERMISSIONS: dict[str, List[str]] = {
    "admin": [
        "source:config", "threshold:config", "notification:config", "system:config",
        "topic:manage", "feed:view", "event:analyze", "event:view",
        "report:generate", "report:export", "alert:receive", "pr:adopt", "ticket:route",
    ],
    "analyst": [
        "topic:manage", "feed:view", "event:analyze", "event:view",
        "report:generate", "report:export",
    ],
    "pr": [
        "alert:receive", "event:view", "pr:adopt", "ticket:route", "feed:view",
    ],
}

# 演示态默认账号（仅用于本地演示，生产请通过环境变量覆盖并接入真实用户库）。
# 安全：不再硬编码弱默认口令(admin123 等)。优先读环境变量 ADMIN_PASSWORD / ANALYST_PASSWORD /
# PR_PASSWORD；若未设置，则启动期为该账号生成一次性随机强口令并打印到启动日志（见 main.py 生命周期），
# 避免「克隆即弱口令」。自动生成的口令仅本次启动有效（种子账号不落盘），重启且未设环境变量会重新生成。
AUTO_SEED_PASSWORDS: dict[str, str] = {}  # 仅记录本次启动自动生成的口令，供启动日志提示（进程内存，不落盘）


def _resolve_seed_password(username: str, env_var: str) -> str:
    """种子账号口令解析：环境变量优先；未设置则生成随机强口令（记录到 AUTO_SEED_PASSWORDS）。"""
    env_val = os.getenv(env_var)
    if env_val:
        return env_val
    pw = secrets.token_urlsafe(16)
    AUTO_SEED_PASSWORDS[username] = pw
    return pw


SEED_USERS: List[dict] = [
    {"username": "admin", "password": _resolve_seed_password("admin", "ADMIN_PASSWORD"),
     "role": "admin", "name": "系统管理员"},
    {"username": "analyst", "password": _resolve_seed_password("analyst", "ANALYST_PASSWORD"),
     "role": "analyst", "name": "舆情分析师"},
    {"username": "pr", "password": _resolve_seed_password("pr", "PR_PASSWORD"),
     "role": "pr", "name": "公关运营"},
]

# 默认通知渠道（管理员可配置）
DEFAULT_NOTIFICATION_CHANNELS: List[str] = ["站内消息", "邮件", "短信", "企业微信"]


@dataclass
class Settings:
    """全局配置单例。通过 load_settings() 获取唯一实例。"""

    # ----- 服务基础配置 -----
    app_name: str = "清衡舆情分析平台"
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    # ----- 安全与鉴权 -----
    # 安全修复（P0 硬编码密钥）：原密钥写死在源码里，拿到源码即可伪造任意令牌。
    # 现改为「优先读环境变量 SECRET_KEY；未设置时生成临时随机密钥（仅单实例演示，重启失效），
    # 并在日志高亮告警」。多副本生产部署请通过环境变量 SECRET_KEY 注入同一把强密钥。
    secret_key: str = field(
        default_factory=lambda: os.getenv("SECRET_KEY") or _generate_ephemeral_secret()
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "525600"))
    )

    # ----- 数据集路径 -----
    dataset_path: str = field(
        default_factory=lambda: os.getenv(
            "DATASET_PATH",
            os.path.join(os.path.dirname(__file__), "data", "dataset.json"),
        )
    )

    # ----- 跨域（演示态允许本地前端，生产请改为显式来源） -----
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv(
                "CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
            ).split(",")
            if o.strip()
        ]
    )

    # ----- 模拟 LLM 开关（演示态默认开启，可一键替换为真实大模型接口） -----
    use_mock_llm: bool = field(
        default_factory=lambda: os.getenv("USE_MOCK_LLM", "true").lower() == "true"
    )
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))

    # ----- 风险预警阈值（管理员可配置，这里为默认值） -----
    risk_negative_ratio_threshold: float = field(
        default_factory=lambda: float(os.getenv("RISK_NEGATIVE_RATIO", "0.45"))
    )
    risk_volume_threshold: int = field(
        default_factory=lambda: int(os.getenv("RISK_VOLUME", "200"))
    )
    # 突发舆情判定：单小时负向声量环比超过该倍数即触发突发预警
    burst_multiplier: float = field(
        default_factory=lambda: float(os.getenv("BURST_MULTIPLIER", "2.5"))
    )

    def validate(self) -> None:
        """启动校验：数据集文件必须存在，且 SECRET_KEY 不得过短或为已知弱密钥。"""
        if not os.path.isfile(self.dataset_path):
            raise RuntimeError(
                f"数据集文件不存在: {self.dataset_path}，请先运行 data/mock/generate_mock.py 生成。"
            )
        # 安全：拒绝过短或为已知弱密钥的 SECRET_KEY
        if self.secret_key in (
            "", "pcxx-yuqing-platform-fixed-secret-2026-do-not-rotate",
            "changeme", "secret",
        ) or len(self.secret_key) < 16:
            raise RuntimeError(
                "SECRET_KEY 过短或为已知弱密钥（至少 16 位）；"
                "多副本生产部署请通过环境变量 SECRET_KEY 注入同一把强密钥。"
            )


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """获取配置单例（进程内唯一）。"""
    return Settings()


settings = load_settings()
