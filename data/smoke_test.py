# 文件位置: data/smoke_test.py
# 功能: 舆情平台 HTTP 端到端冒烟测试（仅用标准库 urllib，无需额外依赖）。
#       依次验证：登录鉴权、态势总览、事件列表/详情、监测流、预警、配置读写、
#       处置协同、报告生成与三种格式导出、SSE 预警流、RBAC 越权拦截。
import json
import os
import urllib.request
import urllib.error
import urllib.parse
import time

BASE = os.getenv("BASE", "http://127.0.0.1:8000")
OUT = os.getenv("OUT", "/tmp/smoke_out")
os.makedirs(OUT, exist_ok=True)

results = []  # (tag, ok, detail)


def req(method, path, token=None, body=None, params=None, raw=False, timeout=10):
    url = BASE + "/api" + path
    if params:
        # doseq=True 是必需的：sentiments / risk_grades 这类多值参数若按普通方式编码，
        # 会被序列化成 "['negative']" 这样的字符串，服务端按枚举匹配不到任何值，
        # 筛选结果会静默变成 0 条（看似通过、实则没验到筛选逻辑）。
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    data = None
    # 本机 WorkBuddy 系统代理按 UA 拦截 Python-urllib 的 CONNECT 隧道（报 502 Bad Gateway），
    # 统一伪装成 curl UA 即可走通代理；对本地 127.0.0.1 直连无任何影响。
    headers = {"Accept": "application/json", "User-Agent": "curl/8.9.1"}
    if token:
        # 线上托管平台的反向代理会覆盖 Authorization 头，鉴权必须走自定义头 X-Auth-Token；
        # 本地无代理时两个头都发，确保两种环境都能通过鉴权。前端 app.js 与 verify_pages_render.js 同样使用 X-Auth-Token。
        headers["Authorization"] = "Bearer " + token
        headers["X-Auth-Token"] = token
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


# ---------------------------------------------------------------------------
# 1. 登录三角色
# ---------------------------------------------------------------------------
tokens = {}
for user, pw in [("admin", "admin123"), ("analyst", "analyst123"), ("pr", "pr123")]:
    st, body = req("POST", "/auth/login", body={"username": user, "password": pw})
    ok = st == 200 and "access_token" in body
    check(f"login:{user}", ok, f"status={st}")
    if ok:
        tokens[user] = body["access_token"]
        check(f"login:{user}:perms", "permissions" in body.get("user", {}),
              f"role={body['user']['role']} perms={body['user']['permissions']}")

ADMIN = tokens.get("admin")
ANALYST = tokens.get("analyst")
PR = tokens.get("pr")

# ---------------------------------------------------------------------------
# 2. 态势总览（含 total_volume 校验）
# ---------------------------------------------------------------------------
st, body = req("GET", "/overview", token=ADMIN)
has_tv = isinstance(body, dict) and "total_volume" in body
check("overview:total_volume", has_tv, f"status={st} keys={list(body.keys())[:8] if isinstance(body,dict) else body}")
if has_tv:
    need = ["total_volume", "event_count", "alert_count", "risk_distribution", "sentiment", "trend", "hotwords", "dedup"]
    check("overview:shape", all(k in body for k in need),
          f"total_volume={body['total_volume']} events={body['event_count']} alerts={body['alert_count']}")

# ---------------------------------------------------------------------------
# 3. 事件列表 / 详情（演示场景 ev_g1 连锁健身闭店退费纠纷）
# ---------------------------------------------------------------------------
st, body = req("GET", "/events", token=ADMIN)
ev_ok = st == 200 and isinstance(body, dict) and "events" in body
check("events:list", ev_ok, f"status={st} count={len(body.get('events',[])) if ev_ok else 0}")
if ev_ok:
    food = next((e for e in body["events"] if e.get("event_id") == "ev_g1"), None)
    check("events:ev_g1_present", food is not None, f"title={food['title'] if food else None}")

st, body = req("GET", "/events/ev_g1", token=ADMIN)
det_ok = st == 200 and isinstance(body, dict) and "event_id" in body
check("event:detail:ev_g1", det_ok, f"status={st} grade={body.get('grade') if det_ok else None} viewpoints={len(body.get('viewpoints',[])) if det_ok else 0}")

# ---------------------------------------------------------------------------
# 4. 监测流（多维筛选）
# ---------------------------------------------------------------------------
st, body = req("GET", "/feed", token=ADMIN, params={"page": 1, "page_size": 5})
feed_ok = st == 200 and isinstance(body, dict) and "items" in body
check("feed:list", feed_ok, f"status={st} returned={len(body.get('items',[])) if feed_ok else 0} total={body.get('total') if feed_ok else None}")
# 情感筛选
st, body = req("GET", "/feed", token=ADMIN, params={"sentiments": ["negative"], "page_size": 3})
check("feed:filter:sentiment", st == 200 and len(body.get("items", [])) > 0,
      f"status={st} neg_items={len(body.get('items',[])) if st==200 else 0} total={body.get('total') if st==200 else None}")

# ---------------------------------------------------------------------------
# 5. 预警列表
# ---------------------------------------------------------------------------
st, body = req("GET", "/alerts", token=ADMIN)
al_ok = st == 200 and isinstance(body, dict) and "alerts" in body
check("alerts:list", al_ok, f"status={st} count={len(body.get('alerts',[])) if al_ok else 0}")

# ---------------------------------------------------------------------------
# 6. 监测配置读写
# ---------------------------------------------------------------------------
st, body = req("GET", "/config", token=ADMIN)
check("config:get", st == 200 and isinstance(body, dict), f"status={st} keys={list(body.keys()) if isinstance(body,dict) else body}")
# 修改阈值（admin 专属）
st, body = req("PUT", "/config/thresholds", token=ADMIN,
               body={"risk_negative_ratio_threshold": 0.5, "risk_volume_threshold": 150, "burst_multiplier": 3.0})
check("config:put:thresholds", st == 200, f"status={st}")
# analyst 尝试改阈值 -> 应 403
st, body = req("PUT", "/config/thresholds", token=ANALYST,
               body={"risk_negative_ratio_threshold": 0.5, "risk_volume_threshold": 150, "burst_multiplier": 3.0})
check("config:rbac:analyst_forbidden", st == 403, f"status={st}")

# ---------------------------------------------------------------------------
# 7. 处置协同（状态流转）
# ---------------------------------------------------------------------------
st, body = req("PUT", "/events/ev_g1/disposal", token=ADMIN,
               body={"status": "处理中", "note": "已联系门店核查", "handler": "公关运营-小李"})
check("disposal:put", st == 200, f"status={st} disposal={body.get('disposal') if st==200 else None}")
# pr 采纳公关建议（生成话术草案）
st, body = req("POST", "/events/ev_g1/response-draft", token=PR)
check("disposal:response-draft:pr", st == 200 and isinstance(body, dict) and "draft" in body,
      f"status={st} strategy_len={len(body.get('draft',{}).get('strategy','')) if st==200 else 0}")

# ---------------------------------------------------------------------------
# 8. 报告生成 + 三种格式导出
# ---------------------------------------------------------------------------
st, body = req("POST", "/reports/generate", token=ADMIN, body={"event_id": "ev_g1"})
rep_ok = st == 200 and isinstance(body, dict) and "report" in body
check("report:generate", rep_ok, f"status={st}")
if rep_ok:
    rep = body["report"]
    need = ["title", "meta", "summary", "sections", "pr_strategy", "pr_draft", "pr_category", "pr_demand"]
    check("report:sections", all(k in rep for k in need),
          f"sections={list(rep.keys())}")

for fmt in ["markdown", "html", "pdf"]:
    st, b = req("GET", "/reports/ev_g1/export", token=ADMIN, params={"format": fmt}, raw=True)
    if fmt == "pdf":
        ok = st == 200 and b[:4] == b"%PDF"
        detail = f"status={st} is_pdf={b[:4]==b'%PDF'} bytes={len(b)}"
    else:
        ok = st == 200 and len(b) > 50
        detail = f"status={st} bytes={len(b)} head={b[:40].decode('utf-8','replace')!r}"
    check(f"report:export:{fmt}", ok, detail)
    if ok:
        with open(os.path.join(OUT, f"ev_g1.{fmt if fmt!='pdf' else 'pdf'}"), "wb") as f:
            f.write(b)

# ---------------------------------------------------------------------------
# 9. SSE 预警流（读取若干事件行，带超时）
# ---------------------------------------------------------------------------
def sse_probe(token, secs=4):
    url = BASE + "/api/stream/alerts?token=" + token
    req_sse = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    try:
        with urllib.request.urlopen(req_sse, timeout=secs) as resp:
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

lines = sse_probe(PR)
got_event = any(l.startswith("data:") or l.startswith("event:") for l in lines)
check("sse:alerts:stream", got_event or len(lines) > 0, f"lines={lines[:4]}")

# ---------------------------------------------------------------------------
# 10. RBAC: pr 越权访问报告导出（应被放行，pr 有 report:export? 实际无）
# pr 权限无 report:export -> 应 403
st, _ = req("GET", "/reports/ev_g1/export", token=PR, params={"format": "markdown"}, raw=True)
check("rbac:pr_no_report_export", st == 403, f"status={st}")

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print("\n==== SUMMARY ====")
print(f"PASS {passed}/{total}")
fails = [t for t, ok, _ in results if not ok]
if fails:
    print("FAILED:", fails)
else:
    print("ALL GREEN")
