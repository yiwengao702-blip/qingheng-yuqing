# 文件位置: backend/app/security.py
# 功能: 鉴权与 RBAC。HS256 JWT（基于 hmac，无第三方依赖，实现见 app/sakura_jwt.py 内联副本）
#       + pbkdf2 口令哈希。令牌默认有效期 1 年（config.access_token_expire_minutes=525600）。
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import List, Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.errors import AuthError, PermissionDeniedError
from app.online_registry import ensure_registered

# [本地化] HS256 签发/校验收敛到 app/sakura_jwt.py（sakura_base.auth.jwt 的内联副本，
# 纯标准库零三方依赖）。这样发布版 clone-and-run，不再依赖仓库外的私有共享底座。
from app.sakura_jwt import encode_jwt, decode_jwt

_bearer = HTTPBearer(auto_error=False)

# 吊销的令牌集合（被管理员「删除/踢出」的账号令牌会加入，下次请求即 401）
REVOKED_TOKENS: set = set()


# ---------------------------------------------------------------------------
# 口令哈希（pbkdf2_hmac，salt 随机）
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return salt.hex() + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# 用户库（种子账号 + 注册账号）已迁移至 services/users.py；
# 本模块只保留口令哈希、JWT 与鉴权依赖，避免循环依赖。


# ---------------------------------------------------------------------------
# 令牌签发/校验：本地内联 HS256（app/sakura_jwt.py）
# ---------------------------------------------------------------------------
def create_access_token(username: str, role: str, name: str, permissions: List[str],
                        expires_minutes: Optional[int] = None) -> str:
    exp = int(time.time()) + (expires_minutes or settings.access_token_expire_minutes) * 60
    # 注意：JWT 载荷中的权限键必须为 "permissions"，
    # 与 require_permissions() 读取的键保持一致（曾误用 "perms" 导致所有鉴权 403）。
    payload = {"sub": username, "role": role, "name": name,
               "permissions": permissions, "exp": exp}
    # 走内联的 HS256 实现；签名密钥为 settings.secret_key（格式与 sakura_base 完全兼容，旧令牌可验）
    return encode_jwt(payload, settings.secret_key, expires_in=exp - int(time.time()))


def decode_token(token: str) -> dict:
    # 走内联实现；校验失败（格式/签名/过期）返回 None 时按原语义抛 AuthError
    payload = decode_jwt(token, settings.secret_key, verify_exp=True)
    if payload is None:
        raise AuthError("令牌无效或已过期")
    return payload


# ---------------------------------------------------------------------------
# 鉴权依赖
# ---------------------------------------------------------------------------
def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    token: Optional[str] = None,
) -> dict:
    # 取用顺序很关键：部分托管平台的反向代理会用其自身的 Authorization 头覆盖我们下发的令牌，
    # 导致应用永远收不到自己的 JWT。因此优先读取自定义头 X-Auth-Token（代理不改写），
    # 其次是 ?token=（供 EventSource 等无法自定义头的场景），最后才回退到标准 Authorization 头（本地直连）。
    raw = request.headers.get("x-auth-token") or token
    if not raw and creds is not None:
        raw = creds.credentials
    if not raw:
        raise AuthError("缺少访问令牌")
    if raw in REVOKED_TOKENS:
        raise AuthError("令牌已被吊销")
    payload = decode_token(raw)
    # 惰性补登记：服务重启会清空内存在线表，但长期令牌仍有效；
    # 这里按令牌载荷把「有令牌却不在表里」的账号补回去，保证管理员能看到全部在线账号。
    ensure_registered(payload.get("sub"), payload.get("role"),
                      payload.get("name"), raw, exp_ts=payload.get("exp"))
    return payload


def require_permissions(*required: str):
    """生成依赖：校验当前用户是否拥有全部所需权限，否则 403。"""

    def _dep(user: dict = Depends(get_current_user)) -> dict:
        owned = set(user.get("permissions", []))
        if not set(required).issubset(owned):
            raise PermissionDeniedError("权限不足，无法执行该操作")
        return user

    return _dep
