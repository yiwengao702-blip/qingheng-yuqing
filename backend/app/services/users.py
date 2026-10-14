# 文件位置: backend/app/services/users.py
# 功能: 用户库服务（单例）。统一管理「演示种子账号」与「页面注册账号」；
#       口令一律经 pbkdf2 哈希后保存，进程内与磁盘均不出现明文。
#       注册账号持久化到 app/data/users.json，重启可恢复；种子账号不落盘（仅内存哈希）。
from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import defaultdict
from typing import Dict, Optional

from app.config import ROLE_PERMISSIONS, SEED_USERS
from app.security import hash_password, verify_password
from app.errors import AuthError

# 用户名规则：3-20 位字母 / 数字 / 下划线
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
_MIN_PASSWORD_LEN = 6
_ROLE_NAMES = {"admin": "系统管理员", "analyst": "舆情分析师", "pr": "公关运营人员"}

# 连续失败锁定策略：达到阈值后锁定 30 分钟，超时自动重置。
_FAILED_LOGIN_THRESHOLD = 150
_LOCKOUT_SECONDS = 30 * 60


class UserStore:
    """用户库单例。线程安全（注册写盘加锁）。"""

    def __init__(self) -> None:
        # 与 monitoring.py 保持一致的 data 目录约定
        self.path = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")
        self._lock = threading.Lock()
        # username -> {username, name, role, password_hash, seed}
        self._users: Dict[str, dict] = {}
        self._load()
        # 连续失败计数 + 最后一次失败时间（用于 150 次触发 30 分钟锁）
        # 不持久化 —— 进程重启视为一次“重新注入”，与大多数系统的行为一致。
        self._failed: Dict[str, int] = defaultdict(int)
        self._last_fail_at: Dict[str, float] = {}

    def _load(self) -> None:
        # 1) 演示种子账号（内存内哈希，不落盘）
        for u in SEED_USERS:
            self._users[u["username"]] = {
                "username": u["username"], "name": u["name"], "role": u["role"],
                "password_hash": hash_password(u["password"]), "seed": True,
            }
        # 2) 页面注册账号（落盘，重启恢复）
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    for u in json.load(f):
                        self._users[u["username"]] = {
                            "username": u["username"],
                            "name": u.get("name") or u["username"],
                            "role": u["role"],
                            "password_hash": u["password_hash"],
                            "seed": False,
                        }
            except Exception:
                # 文件损坏时忽略，保证服务可启动
                pass

    def _persist(self) -> None:
        """仅持久化非种子账号（种子账号口令来自环境变量，无需落盘）。"""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        data = [
            {"username": u["username"], "name": u["name"], "role": u["role"],
             "password_hash": u["password_hash"]}
            for u in self._users.values() if not u.get("seed")
        ]
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _is_locked(self, username: str) -> bool:
        """账号是否处于连续失败锁定期（150 次失败 → 锁定 30 分钟）。"""
        count = self._failed.get(username, 0)
        if count < _FAILED_LOGIN_THRESHOLD:
            return False
        last = self._last_fail_at.get(username, 0.0)
        if time.time() - last >= _LOCKOUT_SECONDS:
            # 锁定期已过，自动清零让账号恢复可用（避免永久锁死）。
            self._failed[username] = 0
            self._last_fail_at[username] = 0.0
            return False
        return True

    def _record_success(self, username: str) -> None:
        """登录/注册成功：重置失败计数（新账号从 0 开始）。"""
        self._failed[username] = 0
        self._last_fail_at[username] = 0.0

    # ----- 查询 -----
    def exists(self, username: str) -> bool:
        return username in self._users

    def _public(self, u: dict) -> dict:
        """对外返回结构（与登录接口 user 字段一致，含权限）。"""
        return {
            "username": u["username"], "name": u["name"], "role": u["role"],
            "permissions": ROLE_PERMISSIONS.get(u["role"], []),
        }

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        u = self._users.get(username)
        if not u or not verify_password(password, u["password_hash"]):
            # 失败：累计次数 + 时间戳；超过阈值后在 lockout 窗口内拒绝登录。
            now = time.time()
            self._failed[username] += 1
            self._last_fail_at[username] = now
            if self._is_locked(username):
                raise AuthError("登录失败次数过多，账号已锁定 30 分钟")
            raise AuthError("用户名或密码错误")
        # 成功：清掉累计次数（防止被恶意刷成锁定状态）。
        self._record_success(username)
        return self._public(u)

    # ----- 注册 -----
    def create(self, username: str, password: str, role: str,
               name: Optional[str] = None) -> dict:
        """创建账号；校验失败抛 ValueError（由路由层转为 400）。"""
        username = (username or "").strip()
        role = (role or "").strip()
        name = (name or "").strip() or username
        if not _USERNAME_RE.match(username):
            raise ValueError("用户名需为 3-20 位字母、数字或下划线")
        if len(password or "") < _MIN_PASSWORD_LEN:
            raise ValueError(f"密码长度至少 {_MIN_PASSWORD_LEN} 位")
        if role not in ROLE_PERMISSIONS:
            raise ValueError("角色不合法，可选：analyst / pr / admin")
        with self._lock:
            if username in self._users:
                raise ValueError("该用户名已被注册")
            u = {
                "username": username, "name": name, "role": role,
                "password_hash": hash_password(password), "seed": False,
            }
            self._users[username] = u
            self._persist()
        return self._public(u)

    def role_name(self, role: str) -> str:
        return _ROLE_NAMES.get(role, role)

    def delete(self, username: str) -> bool:
        """删除账号（含种子账号）。返回是否成功删除。"""
        with self._lock:
            if username not in self._users:
                return False
            del self._users[username]
            self._persist()
            return True


_store: Optional[UserStore] = None


def get_users() -> UserStore:
    """获取用户库单例（进程内唯一，惰性初始化）。"""
    global _store
    if _store is None:
        _store = UserStore()
    return _store
