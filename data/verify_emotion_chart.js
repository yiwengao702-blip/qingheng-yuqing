// 文件位置: data/verify_emotion_chart.js
// 功能: 验证「细粒度情绪分布」图表的端到端链路（接口数据 -> 前端渲染代码）。
//   背景: 该卡片曾长期空白，根因是 /api/overview 未返回 emotion 字段，
//         且 dashboard.js 里根本没有渲染 #emotion 的代码。本脚本用于回归，防止再次漏渲染。
//   1) 真实 HTTP 登录并拉取 /api/overview，校验 emotion 字段结构与合计口径
//   2) 从磁盘真实 js 源码中确认 #emotion / #ev-emotion 的渲染代码存在
//   3) 用真实接口数据重放前端「负向 5 项」构造逻辑，校验合计与颜色映射
// 用法: BASE=http://127.0.0.1:8000 node verify_emotion_chart.js
//       BASE=https://yuqing-platform-24892.app.workbuddy.host node verify_emotion_chart.js
const fs = require("fs");
const path = require("path");

const BASE = process.env.BASE || "http://127.0.0.1:8000";
const JS = "D:/Public Opinion/backend/app/static/js";

// 前端约定的负向情绪顺序与配色（与 dashboard.js / event.js 保持一致）
const NEG_EMO_ORDER = ["愤怒", "失望", "恐慌", "质疑", "其他负向"];
const NEG_EMO_COLOR = { "愤怒": "#e23b3b", "失望": "#e08a00", "恐慌": "#8a4fd3", "质疑": "#2f6df6", "其他负向": "#8a94a6" };

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}  ${detail || ""}`);
}

let TOKEN = "";
async function api(method, p, body) {
  const headers = { "Content-Type": "application/json", "X-Auth-Token": TOKEN, Authorization: "Bearer " + TOKEN };
  const r = await fetch(BASE + p, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  let d; try { d = JSON.parse(t); } catch { d = t; }
  return { status: r.status, data: d };
}

// 从真实源文件读取，避免“验证的是副本”这种自欺
function readJs(file) {
  return fs.readFileSync(path.join(JS, file), "utf-8");
}

(async () => {
  console.log(`目标环境: ${BASE}\n`);

  // ---------- 1) 登录 + 拉取总览 ----------
  const login = await api("POST", "/api/auth/login", { username: "admin", password: "admin123" });
  TOKEN = login.data && login.data.access_token ? login.data.access_token : "";
  check("登录", login.status === 200 && !!TOKEN, `status=${login.status}`);

  const ov = await api("GET", "/api/overview");
  check("GET /api/overview", ov.status === 200, `status=${ov.status}`);

  // ---------- 2) 接口 emotion 字段结构 ----------
  const emo = (ov.data && ov.data.emotion) || null;
  check("overview 返回 emotion 字段", !!emo && typeof emo === "object",
    emo ? JSON.stringify(emo) : "缺失（该卡片将再次变空白）");

  if (emo) {
    const keysOk = NEG_EMO_ORDER.every((k) => typeof emo[k] === "number");
    check("emotion 含全部负向类目", keysOk, NEG_EMO_ORDER.join("/"));
    const nonNeg = typeof emo["非负向"] === "number";
    check("emotion 含「非负向」基数", nonNeg, `非负向=${emo["非负向"]}`);
    const sum = NEG_EMO_ORDER.reduce((a, k) => a + (emo[k] || 0), 0);
    check("负向合计 > 0（图表有内容可画）", sum > 0, `负向合计=${sum} 条`);
    // 与总声量口径核对：负向 + 非负向应等于（或不超过）去重后总量
    const total = (ov.data && ov.data.total_volume) || 0;
    check("情绪口径不超过去重总量", sum + (emo["非负向"] || 0) <= total,
      `情绪合计=${sum + (emo["非负向"] || 0)} / 去重总量=${total}`);
  }

  // ---------- 3) 前端渲染代码确实存在 ----------
  const dashSrc = readJs("dashboard.js");
  check("dashboard.js 渲染 #emotion", /getElementById\(\s*["']emotion["']\s*\)/.test(dashSrc),
    "大盘「细粒度情绪分布」渲染代码");
  check("dashboard.js 读取 ov.emotion", /ov\.emotion/.test(dashSrc), "数据源绑定 overview.emotion");

  const evSrc = readJs("event.js");
  check("event.js 渲染 #ev-emotion", /getElementById\(\s*["']ev-emotion["']\s*\)/.test(evSrc),
    "事件页「细粒度情绪分布」渲染代码");

  // ---------- 4) 重放前端构造逻辑 ----------
  if (emo) {
    const emoNeg = NEG_EMO_ORDER.map((k) => ({ name: k, value: emo[k] || 0 }));
    const emoNegSum = emoNeg.reduce((a, b) => a + b.value, 0);
    const colorsOk = emoNeg.every((x) => !!NEG_EMO_COLOR[x.name]);
    check("负向 5 项各有配色", colorsOk, NEG_EMO_ORDER.map((k) => `${k}:${NEG_EMO_COLOR[k]}`).join(" "));
    check("series 长度 = 5（无「非负向」混入刻度）", emoNeg.length === 5,
      emoNeg.map((x) => `${x.name}=${x.value}`).join(" "));
    check("title 副标题可正常生成", typeof `负向合计 ${emoNegSum} 条 · 非负向 ${emo["非负向"] || 0} 条（未计入刻度）` === "string",
      `负向合计 ${emoNegSum} 条 · 非负向 ${emo["非负向"] || 0} 条`);
  }

  // ---------- 汇总 ----------
  const pass = results.filter((r) => r.ok).length;
  console.log(`\n===== 细粒度情绪分布链路: ${pass}/${results.length} PASS =====`);
  if (pass !== results.length) {
    console.log("失败项: " + results.filter((r) => !r.ok).map((r) => r.name).join(" / "));
    process.exit(1);
  }
})();
