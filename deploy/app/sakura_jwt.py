# backend/app/sakura_jwt.py
#
# 本地 vendoring：sakura_base.auth.jwt 中「HS256 JWT 签发/校验」部分的副本，
# 使清衡舆情发布版无需依赖仓库外的私有共享底座即可独立运行（clone-and-run）。
# 算法 / 令牌格式 / 签名与 sakura_base 完全一致（纯标准库，零三方依赖）。
# 如需与 sakura_base 主线保持同步，直接替换本文件为最新版本即可。
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def encode_jwt(payload: Dict[str, Any], secret: str, *, expires_in: int = 3600) -> str:
    """签发 HS256 JWT；自动注入 iat / exp。"""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    body = dict(payload)
    body["iat"] = now
    body["exp"] = now + expires_in
    seg1 = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    seg2 = _b64url(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{seg1}.{seg2}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{seg1}.{seg2}.{_b64url(sig)}"


def decode_jwt(token: str, secret: str, *, verify_exp: bool = True) -> Optional[Dict[str, Any]]:
    """校验签名并（可选）校验过期；成功返回 payload，失败返回 None。"""
    try:
        seg1, seg2, sig_b64 = token.split(".")
    except ValueError:
        return None
    signing_input = f"{seg1}.{seg2}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url(expected), sig_b64):
        return None
    try:
        payload = json.loads(_b64url_decode(seg2))
    except Exception:
        return None
    if verify_exp and isinstance(payload.get("exp"), int) and payload["exp"] < int(time.time()):
        return None
    return payload
