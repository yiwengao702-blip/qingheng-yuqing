# 文件位置: backend/app/config.py
# 功能: 集中式配置管理（dataclass 单例）。所有配置来自环境变量，启动时集中校验、快速失败。
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List


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
# 真实口令不得写入代码库；此处为可一键替换的演示种子。
SEED_USERS: List[dict] = [
    {"username": "admin", "password": os.getenv("ADMIN_PASSWORD", "admin123"),
     "role": "admin", "name": "系统管理员"},
    {"username": "analyst", "password": os.getenv("ANALYST_PASSWORD", "analyst123"),
     "role": "analyst", "name": "舆情分析师"},
    {"username": "pr", "password": os.getenv("PR_PASSWORD", "pr123"),
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
    # 注意：线上以多副本方式部署时，各副本必须使用「同一把」签名密钥，否则
    # A 副本签发的令牌在 B 副本校验会报「令牌签名无效」。因此这里使用固定常量，
    # 不读取 SECRET_KEY 环境变量（部分托管平台会按实例随机注入，导致跨副本令牌失效）。
    secret_key: str = "pcxx-yuqing-platform-fixed-secret-2026-do-not-rotate"
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
        """启动校验：数据集文件必须存在。"""
        if not os.path.isfile(self.dataset_path):
            raise RuntimeError(
                f"数据集文件不存在: {self.dataset_path}，请先运行 data/mock/generate_mock.py 生成。"
            )


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """获取配置单例（进程内唯一）。"""
    return Settings()


settings = load_settings()
