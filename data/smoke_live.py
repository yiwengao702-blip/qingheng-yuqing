# 文件位置: data/smoke_live.py
# 功能: 针对「已发布的线上地址」的端到端冒烟。与 smoke_test.py 的区别：
#       令牌同时通过 Authorization 与 X-Auth-Token 下发（托管平台代理会覆盖前者）。
#       用法: BASE=https://xxx OUT=./live_out python smoke_live.py
import json
import os
import urllib.request
import urllib.error
import urllib.parse
import time

BASE = os.getenv("BASE", "http://127.0.0.1:8000")
OUT = os.getenv("OUT", "./live_out")
os.makedirs(OUT, exist_ok=True)
results = []


def req(method, path, token=None, body=None, params=None, raw=False, timeout=15):
    url = BASE + "/api" + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
        headers["X-Auth-Token"] = token  # 关键：平台代理会覆盖 Authorization，用自定义头兜底
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            b = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        b = e.read()
        status = e.code
    if raw:
        return status, b
    try:
        parsed = json.loads(b.decode("utf-8")) if b else {}
    except Exception:
        parsed = {"_raw": b.decode("utf-8", "replace")[:200]}
    return status, parsed


def check(tag, cond, detail=""):
    results.append((tag, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {tag}  {detail}")


print(f"BASE = {BASE}\n")

tokens = {}
for user, pw in [("admin", "admin123"), ("analyst", "analyst123"), ("pr", "pr123")]:
    st, body = req("POST", "/auth/login", body={"username": user, "password": pw})
    ok = st == 200 and "access_token" in body
    check(f"login:{user}", ok, f"status={st}")
    if ok:
        tokens[user] = body["access_token"]

ADMIN = tokens.get("admin")
ANALYST = tokens.get("analyst")
PR = tokens.get("pr")

st, body = req("GET", "/auth/me", token=ADMIN)
check("auth:me", st == 200 and body.get("username") == "admin", f"status={st} keys={list(body.keys()) if isinstance(body, dict) else body}")

st, body = req("GET", "/overview", token=ADMIN)
check("overview", st == 200 and "total_volume" in body,
      f"status={st} total_volume={body.get('total_volume')} events={body.get('event_count')} alerts={body.get('alert_count')}")

st, body = req("GET", "/events", token=ADMIN)
check("events:list", st == 200 and "events" in body, f"status={st} count={len(body.get('events', [])) if st == 200 else 0}")

st, body = req("GET", "/events/ev_g1", token=ADMIN)
check("event:detail", st == 200 and "event_id" in body,
      f"status={st} viewpoints={len(body.get('viewpoints', [])) if st == 200 else 0}")

st, body = req("GET", "/feed", token=ADMIN, params={"page": 1, "page_size": 5})
check("feed:list", st == 200 and "items" in body, f"status={st} items={len(body.get('items', [])) if st == 200 else 0}")

st, body = req("GET", "/alerts", token=ADMIN)
check("alerts:list", st == 200 and "alerts" in body, f"status={st} count={len(body.get('alerts', [])) if st == 200 else 0}")

st, body = req("GET", "/config", token=ADMIN)
check("config:get", st == 200, f"status={st} keys={list(body.keys()) if isinstance(body, dict) else body}")

st, body = req("PUT", "/events/ev_g1/disposal", token=ADMIN,
               body={"status": "处理中", "note": "线上冒烟-已联系门店核查", "handler": "公关运营"})
check("disposal:put", st == 200, f"status={st}")

st, body = req("POST", "/events/ev_g1/response-draft", token=PR)
check("response-draft:pr", st == 200 and "draft" in body,
      f"status={st} strategy_len={len(body.get('draft', {}).get('strategy', '')) if st == 200 else 0}")

st, body = req("POST", "/reports/generate", token=ADMIN, body={"event_id": "ev_g1"})
check("report:generate", st == 200 and "report" in body, f"status={st}")

for fmt in ["markdown", "html", "pdf"]:
    st, b = req("GET", "/reports/ev_g1/export", token=ADMIN, params={"format": fmt}, raw=True, timeout=25)
    if fmt == "pdf":
        ok = st == 200 and b[:4] == b"%PDF"
        detail = f"status={st} is_pdf={b[:4] == b'%PDF'} bytes={len(b)}"
    else:
        ok = st == 200 and len(b) > 50
        detail = f"status={st} bytes={len(b)}"
    check(f"report:export:{fmt}", ok, detail)
    if ok:
        with open(os.path.join(OUT, f"ev_g1.{fmt}"), "wb") as f:
            f.write(b)

st, _ = req("GET", "/reports/ev_g1/export", token=PR, params={"format": "markdown"}, raw=True)
check("rbac:pr_no_export", st == 403, f"status={st}")


def sse_probe(token, secs=8):
    url = BASE + "/api/stream/alerts"
    r = urllib.request.Request(url, headers={"Accept": "text/event-stream", "X-Auth-Token": token})
    try:
        with urllib.request.urlopen(r, timeout=secs) as resp:
            end = time.time() + secs
            lines = []
            while time.time() < end:
                line = resp.readline()
                if not line:
                    break
                lines.append(line.decode("utf-8", "replace").rstrip("\n"))
                if len(lines) >= 6:
                    break
            return lines
    except Exception as e:
        return ["ERR:" + str(e)]


lines = sse_probe(ADMIN)
got = any(l.startswith("data:") or l.startswith("event:") for l in lines)
check("sse:alerts:stream", got, f"lines={lines[:4]}")

passed = sum(1 for _, ok, _ in results if ok)
print(f"\n==== SUMMARY ====\nPASS {passed}/{len(results)}")
fails = [t for t, ok, _ in results if not ok]
print("FAILED:", fails if fails else "NONE (ALL GREEN)")
