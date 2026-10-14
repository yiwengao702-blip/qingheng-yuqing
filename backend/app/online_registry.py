# 文件位置: backend/app/online_registry.py
# 功能: 在线账号登记表（进程内存）+ 永久账号白名单（落盘）。
#       登录/注册时登记；令牌校验时对「令牌仍有效但登记表被服务重启清空」的账号惰性补登记，
#       保证管理员始终能看到当前在线账号。永久账号名单跨重启保留。
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Set

# 数据目录：与 users.py 一致
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_PERMANENT_PATH = os.path.join(_DATA_DIR, "permanent_users.json")

# 永久账号集合：跨重启持久化。注册新账号自动加入，手动删除时移除。
PERMANENT_USERS: Set[str] = set()


def _load_permanent() -> None:
    """加载磁盘上的永久账号名单（幂等，失败不抛异常）。"""
    global PERMANENT_USERS
    try:
        if os.path.isfile(_PERMANENT_PATH):
            with open(_PERMANENT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            PERMANENT_USERS = set(str(u) for u in data if isinstance(u, str))
    except Exception:
        PERMANENT_USERS = set()


def _save_permanent() -> None:
    """将永久账号名单写入磁盘（用于注册新账号、手动删除时同步）。"""
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_PERMANENT_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(PERMANENT_USERS), f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 写失败不影响主流程


def is_permanent(username: str) -> bool:
    """判断某账号是否为永久有效（注册账号 / 演示种子账号）。"""
    return username in PERMANENT_USERS


def mark_permanent(username: str) -> None:
    """将账号加入永久名单并落盘（注册成功时调用）。"""
    PERMANENT_USERS.add(username)
    _save_permanent()


def unmark_permanent(username: str) -> None:
    """将账号移出永久名单并落盘（管理员删除账号时调用）。"""
    PERMANENT_USERS.discard(username)
    _save_permanent()


# 模块级初始化：加载磁盘名单
_load_permanent()

# 在线账号表：username -> {username, role, name, login_at, expire_at, token, permanent}
#   permanent=True：账号本身永久有效，expire_at 存 "—"；
#   permanent=False：有明确到期时间的会话账号（暂未使用，保留扩展能力）。
ONLINE_ACCOUNTS: dict = {}


def register(username: str, role: str, name: str, token: str,
             login_at: datetime | None = None, expire_at: datetime | None = None,
             permanent: bool = True) -> None:
    """登记/刷新一个在线账号（登录、注册成功时调用）。"""
    now = datetime.now()
    ONLINE_ACCOUNTS[username] = {
        "username": username,
        "role": role,
        "name": name,
        "login_at": (login_at or now).isoformat(timespec="seconds"),
        # 永久账号显示为 "—"；非永久才存具体时间
        "expire_at": "—" if permanent else (expire_at or now + timedelta(days=365)).isoformat(timespec="seconds"),
        "token": token,
        "permanent": permanent,
    }


def ensure_registered(username: str, role: str, name: str, token: str,
                      exp_ts: int | None = None) -> None:
    """惰性补登记：令牌有效但登记表缺失（服务重启、内存表清空）时自动补录。

    - 已在表中则什么都不做（每次鉴权都会经过这里，务必保持轻量）；
    - 永久账号（注册账号 / 演示种子）直接标 permanent=True，expire_at 显示 "—"；
    - 非永久账号按令牌 exp 推算。
    """
    if not username or username in ONLINE_ACCOUNTS:
        return
    # 优先查永久名单（跨重启也准确），其次查内存旧记录
    permanent = is_permanent(username) or ONLINE_ACCOUNTS.get(username, {}).get("permanent", True)
    now = datetime.now()
    if exp_ts and not permanent:
        try:
            exp_dt = datetime.fromtimestamp(int(exp_ts))
            login_at = min(exp_dt - timedelta(days=365), now)
            register(username, role, name, token, login_at=login_at, expire_at=exp_dt, permanent=False)
            return
        except (OSError, ValueError, OverflowError):
            pass  # exp 异常时走下面的兜底
    register(username, role, name, token, permanent=permanent)


# 模块加载时自动完成持久化读取
load_permanent = _load_permanent  # 兼容旧代码中的导入名
save_permanent = _save_permanent
