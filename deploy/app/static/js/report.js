// 文件位置: backend/app/static/js/report.js
// 功能: 报告中心 —— 事件专项报告与周期简报（日报/周报）的列表、在线预览与 PDF/Markdown/HTML 导出。
const ReportPage = (() => {
  async function render() {
    const page = document.getElementById("page");
    page.innerHTML = `
      <h2>报告中心</h2>
      <div class="desc">自动化生成结构化舆情研判报告与周期简报 · 支持在线预览与 PDF / Markdown / HTML 导出</div>
      <div class="grid cols-2">
        <div class="card"><h3><span class="dot"></span>报告列表</h3><div id="rep-list" class="loading">加载中…</div></div>
        <div class="card"><h3><span class="dot"></span>报告预览</h3><div id="rep-preview"><div class="note">请选择左侧报告项</div></div></div>
      </div>`;

    let list;
    try { list = await API.get("/api/reports"); }
    catch (e) { document.getElementById("rep-list").innerHTML = `<div class="loading">${e.message}</div>`; return; }
    document.getElementById("rep-list").innerHTML = list.reports.map((r) => {
      const tag = r.type === "periodic"
        ? `<span class="tag tag-src">周期简报</span>`
        : `<span class="tag tag-${r.grade}">${r.grade}</span>`;
      const gen = r.generated ? `<span class="tag tag-pos">已生成</span>` : `<span class="tag tag-neu">待生成</span>`;
      return `<div class="event-item" data-id="${r.id}" data-type="${r.type}">
        <div class="title">${esc(r.title)} ${tag} ${gen}</div>
        <div class="note">${r.generated_at ? "生成于 " + esc(r.generated_at) : "点击生成专项报告"}</div>
      </div>`;
    }).join("");
    document.querySelectorAll("#rep-list .event-item").forEach((el) => {
      el.onclick = () => {
        document.querySelectorAll("#rep-list .event-item").forEach((x) => x.classList.remove("active"));
        el.classList.add("active");
        onSelect(el.dataset.id, el.dataset.type);
      };
    });
    // 默认自动展开第一项，避免右侧预览区空白
    const first = document.querySelector("#rep-list .event-item");
    if (first) { first.classList.add("active"); onSelect(first.dataset.id, first.dataset.type); }
  }

  async function onSelect(id, type) {
    const box = document.getElementById("rep-preview");
    if (type === "periodic") {
      // 周期简报（日报/周报）：由后端汇总全网态势、事件排行与预警进展生成
      const kind = id === "periodic_weekly" ? "weekly" : "daily";
      box.innerHTML = `<div class="loading">生成简报中…</div>`;
      let data;
      try { data = await API.get("/api/reports/periodic/" + kind); }
      catch (e) { box.innerHTML = `<div class="loading">${e.message}</div>`; return; }
      renderReport(box, data.report, { periodicKind: kind });
      return;
    }
    box.innerHTML = `<div class="loading">生成报告中…</div>`;
    let data;
    try { data = await API.post("/api/reports/generate", { event_id: id }); }
    catch (e) { box.innerHTML = `<div class="loading">${e.message}</div>`; return; }
    renderReport(box, data.report, { eventId: id });
  }

  // 统一渲染报告预览：事件专项报告与周期简报共用（周期简报无第六节公关话术）
  function renderReport(box, r, target) {
    let tail = "";
    if (!target.periodicKind) {
      tail = `
        <div class="section-title">六、公关应对策略与回应话术草案</div>
        <div class="note">事件性质：<b>${esc(r.pr_category)}</b> ｜ 核心诉求：${esc(r.pr_demand)}</div>
        <ul>${(r.pr_strategy || []).map((s) => `<li style="margin:4px 0">${esc(s)}</li>`).join("")}</ul>
        <pre class="draft">${esc(r.pr_draft)}</pre>`;
    }
    box.innerHTML = `
      <h3 style="margin-bottom:8px">${esc(r.title)}</h3>
      <table style="width:100%;border-collapse:collapse;margin-bottom:10px">
        ${Object.entries(r.meta).map(([k, v]) => `<tr><th style="text-align:left;background:#f7f7f7;padding:6px 10px;border:1px solid #eee;width:120px">${esc(k)}</th><td style="padding:6px 10px;border:1px solid #eee">${esc(v)}</td></tr>`).join("")}
      </table>
      ${r.sections.map((s) => `<div class="section-title">${esc(s.title)}</div><div class="sec-body">${esc(s.body)}</div>`).join("")}
      ${tail}
      <div class="actions">
        <button class="btn" id="exp-md">导出 Markdown</button>
        <button class="btn ghost" id="exp-pdf">导出 PDF</button>
        <button class="btn ghost" id="exp-html">导出 HTML</button>
      </div>`;
    document.getElementById("exp-md").onclick = () => exportFile(target, "markdown");
    document.getElementById("exp-pdf").onclick = () => exportFile(target, "pdf");
    document.getElementById("exp-html").onclick = () => exportFile(target, "html");
  }

  function exportUrl(target, fmt) {
    return target.periodicKind
      ? `/api/reports/periodic/${target.periodicKind}/export?format=${fmt}`
      : `/api/reports/${target.eventId}/export?format=${fmt}`;
  }

  async function exportFile(target, fmt) {
    const name = target.periodicKind
      ? (target.periodicKind === "weekly" ? "舆情周报" : "舆情日报")
      : `舆情研判报告_${target.eventId}`;
    try {
      const resp = await API.raw(exportUrl(target, fmt));
      if (!resp.ok) { const d = await resp.json().catch(() => ({})); throw new Error((d.error && d.error.message) || "导出失败"); }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${name}.${fmt === "markdown" ? "md" : fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast("已开始下载");
    } catch (e) { toast(e.message); }
  }

  // 统一转义：必须兼容数字/布尔等非字符串字段（如 meta.声量 是 int），
  // 否则 (s || "").replace 会抛 TypeError，导致整段渲染中断、页面卡在“生成中”。
  function esc(s) { return String(s === null || s === undefined ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

  return { render };
})();
window.ReportPage = ReportPage;
