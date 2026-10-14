// 文件位置: data/verify_pages_render.js
// 功能: 端到端验证「生成」类页面的渲染不再崩溃。
//   1) 通过真实 HTTP 链路登录并调用报告生成 / 话术生成接口（本地或线上均可，由 BASE 环境变量指定）
//   2) 从磁盘上的真实 js 文件里提取 esc() 定义并执行（确保验证的是实际发布的代码）
//   3) 用真实响应数据重放 report.js / disposal.js 的模板拼接，观察是否抛异常
// 用法: BASE=http://127.0.0.1:8000 node verify_pages_render.js
//       BASE=https://yuqing-platform-24892.app.workbuddy.host node verify_pages_render.js
const fs = require("fs");
const path = require("path");

const BASE = process.env.BASE || "http://127.0.0.1:8000";
const JS = "D:/Public Opinion/backend/app/static/js";

// 从真实源文件里抽取 esc 定义并求值，避免“验证的是副本”这种自欺
function loadEsc(file) {
  const src = fs.readFileSync(path.join(JS, file), "utf-8");
  const m = src.match(/function esc\(s\)\s*\{[^\n]*\}/);
  if (!m) throw new Error(`在 ${file} 中未找到 esc 定义`);
  return { fn: eval("(" + m[0] + ")"), raw: m[0] };
}

let TOKEN = "";
async function api(method, p, body) {
  const headers = { "Content-Type": "application/json", "X-Auth-Token": TOKEN, Authorization: "Bearer " + TOKEN };
  const r = await fetch(BASE + p, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  let d; try { d = JSON.parse(t); } catch { d = t; }
  return { status: r.status, data: d };
}

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}  ${detail || ""}`);
}

(async () => {
  console.log(`目标环境: ${BASE}\n`);

  // ---------- 登录 ----------
  const login = await api("POST", "/api/auth/login", { username: "admin", password: "admin123" });
  check("登录", login.status === 200 && !!login.data.access_token, `status=${login.status}`);
  TOKEN = login.data.access_token || "";

  // ================= 报告中心（report.js） =================
  const escRep = loadEsc("report.js");
  console.log(`\n[report.js] esc 实现: ${escRep.raw.slice(0, 78)}…`);

  const list = await api("GET", "/api/reports");
  check("GET /api/reports", list.status === 200 && Array.isArray(list.data.reports),
    `status=${list.status} reports=${(list.data.reports || []).length}`);

  // 取非周期性的第一个事件报告
  const target = (list.data.reports || []).find((r) => r.type !== "periodic");
  check("存在可生成的事件报告项", !!target, target ? `id=${target.id} title=${target.title}` : "未找到");

  if (target) {
    const gen = await api("POST", "/api/reports/generate", { event_id: target.id });
    check("POST /api/reports/generate", gen.status === 200 && !!gen.data.report, `status=${gen.status}`);

    if (gen.data.report) {
      const r = gen.data.report;
      // 非字符串字段提示（正是这次 bug 的触发源）
      const nonStr = Object.entries(r.meta).filter(([, v]) => typeof v !== "string");
      console.log(`   meta 中非字符串字段: ${nonStr.map(([k, v]) => `${k}(${typeof v})=${v}`).join(", ") || "无"}`);

      // 精确复刻 report.js onSelect 的渲染模板
      try {
        const html = `
          <h3>${escRep.fn(r.title)}</h3>
          <table>${Object.entries(r.meta).map(([k, v]) =>
            `<tr><th>${escRep.fn(k)}</th><td>${escRep.fn(v)}</td></tr>`).join("")}</table>
          ${r.sections.map((s) => `<div class="section-title">${escRep.fn(s.title)}</div><div>${escRep.fn(s.body)}</div>`).join("")}
          <div class="section-title">六、公关应对策略与回应话术草案</div>
          <div class="note">事件性质：<b>${escRep.fn(r.pr_category)}</b> ｜ 核心诉求：${escRep.fn(r.pr_demand)}</div>
          <ul>${r.pr_strategy.map((s) => `<li>${escRep.fn(s)}</li>`).join("")}</ul>
          <pre class="draft">${escRep.fn(r.pr_draft)}</pre>`;
        const vol = (html.match(/<td>(\d+)<\/td>/) || [])[1];
        check("report.js 渲染预览(不再抛 TypeError)", true, `HTML=${html.length}字节 声量单元格=${vol}`);
        check("报告六段结构完整", r.sections.length === 5 && !!r.pr_draft && r.pr_strategy.length > 0,
          `sections=${r.sections.length} 策略=${r.pr_strategy.length}条 话术=${r.pr_draft.length}字`);
      } catch (e) {
        check("report.js 渲染预览(不再抛 TypeError)", false, `${e.constructor.name}: ${e.message}`);
      }
    }
  }

  // ================= 处置协同：生成草案（disposal.js） =================
  const escDis = loadEsc("disposal.js");
  const events = await api("GET", "/api/events");
  check("GET /api/events", events.status === 200 && Array.isArray(events.data.events),
    `status=${events.status} events=${(events.data.events || []).length}`);

  const ev0 = (events.data.events || [])[0];
  if (ev0) {
    const draft = await api("POST", `/api/events/${ev0.event_id}/response-draft`, {});
    check("POST /api/events/{id}/response-draft", draft.status === 200 && !!draft.data.draft, `status=${draft.status}`);

    if (draft.data.draft) {
      const d = draft.data.draft;
      try {
        const html = `
          <div class="note">事件性质：<b>${escDis.fn(d.category)}</b> ｜ 核心诉求：${escDis.fn(d.demand)}</div>
          <ul>${(d.strategy || []).map((s) => `<li>${escDis.fn(s)}</li>`).join("")}</ul>
          <pre class="draft">${escDis.fn(d.draft)}</pre>`;
        check("disposal.js 渲染草案", true, `HTML=${html.length}字节 策略=${(d.strategy || []).length}条`);
      } catch (e) {
        check("disposal.js 渲染草案", false, `${e.constructor.name}: ${e.message}`);
      }
    }
  }

  // ================= 报告导出（Markdown / HTML / PDF） =================
  if (target) {
    for (const fmt of ["markdown", "html", "pdf"]) {
      const r = await fetch(`${BASE}/api/reports/${target.id}/export?format=${fmt}`, {
        headers: { "X-Auth-Token": TOKEN, Authorization: "Bearer " + TOKEN },
      });
      const buf = Buffer.from(await r.arrayBuffer());
      const okPdf = fmt !== "pdf" || buf.slice(0, 4).toString() === "%PDF";
      check(`导出 ${fmt}`, r.status === 200 && buf.length > 500 && okPdf,
        `status=${r.status} ${buf.length}字节${fmt === "pdf" ? " magic=" + buf.slice(0, 4).toString() : ""}`);
    }
  }

  // ================= 周期简报（日报 / 周报） =================
  for (const kind of ["daily", "weekly"]) {
    const pr = await api("GET", `/api/reports/periodic/${kind}`);
    check(`GET /api/reports/periodic/${kind}`, pr.status === 200 && !!pr.data.report, `status=${pr.status}`);
    if (pr.data.report) {
      const r = pr.data.report;
      try {
        const html = `
          <h3>${escRep.fn(r.title)}</h3>
          <table>${Object.entries(r.meta).map(([k, v]) =>
            `<tr><th>${escRep.fn(k)}</th><td>${escRep.fn(v)}</td></tr>`).join("")}</table>
          ${r.sections.map((s) => `<div class="section-title">${escRep.fn(s.title)}</div><div class="sec-body">${escRep.fn(s.body)}</div>`).join("")}`;
        check(`${kind} 简报渲染`, r.sections.length === 4 && html.length > 400,
          `标题=${r.title} sections=${r.sections.length} HTML=${html.length}字节`);
      } catch (e) {
        check(`${kind} 简报渲染`, false, `${e.constructor.name}: ${e.message}`);
      }
      for (const fmt of ["markdown", "pdf"]) {
        const resp = await fetch(`${BASE}/api/reports/periodic/${kind}/export?format=${fmt}`, {
          headers: { "X-Auth-Token": TOKEN, Authorization: "Bearer " + TOKEN },
        });
        const buf = Buffer.from(await resp.arrayBuffer());
        const okPdf = fmt !== "pdf" || buf.slice(0, 4).toString() === "%PDF";
        check(`${kind} 导出 ${fmt}`, resp.status === 200 && buf.length > 400 && okPdf,
          `status=${resp.status} ${buf.length}字节${fmt === "pdf" ? " magic=" + buf.slice(0, 4).toString() : ""}`);
      }
    }
  }

  // ---------- 汇总 ----------
  const pass = results.filter((r) => r.ok).length;
  console.log(`\n===== 结果: ${pass}/${results.length} PASS (${BASE}) =====`);
  process.exit(pass === results.length ? 0 : 1);
})().catch((e) => { console.error("脚本异常:", e); process.exit(2); });
