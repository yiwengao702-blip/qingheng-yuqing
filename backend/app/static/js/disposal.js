// 文件位置: backend/app/static/js/disposal.js
// 功能: 处置协同 —— 事件处置状态流转（跟踪/已核实/辟谣处理/忽略/已处理）、风险人工复核、
//       大模型公关回应草案生成与采纳。
const Disposal = (() => {
  const STATUS = [
    { k: "tracking", t: "跟踪中" }, { k: "verified", t: "已核实" },
    { k: "rumor_refuted", t: "辟谣处理" }, { k: "ignored", t: "忽略" }, { k: "handled", t: "已处理" },
  ];

  async function render() {
    const page = document.getElementById("page");
    page.innerHTML = `
      <h2>处置协同</h2>
      <div class="desc">对高危事件进行处置状态流转与风险人工复核，并生成/采纳大模型公关回应草案</div>
      <div class="grid cols-3" id="disp-list"></div>
      <div class="card" id="disp-detail" style="margin-top:16px"><div class="note">请选择事件</div></div>`;

    let list;
    try { list = await API.get("/api/events"); }
    catch (e) { document.getElementById("disp-list").innerHTML = `<div class="loading">${e.message}</div>`; return; }
    // 仅展示有风险（S/A/B）或高声量事件
    const evs = list.events;
    document.getElementById("disp-list").innerHTML = evs.map((e) => `
      <div class="event-item" data-id="${e.event_id}">
        <div class="title">${esc(e.title)} <span class="tag tag-${e.grade}">${e.grade}</span></div>
        <div class="note">${esc(e.category)} · 声量 ${e.volume} · 烈度 ${e.intensity}</div>
      </div>`).join("");
    document.querySelectorAll("#disp-list .event-item").forEach((el) => {
      el.onclick = () => loadDetail(el.dataset.id);
    });
    if (evs.length) loadDetail(evs[0].event_id);
  }

  async function loadDetail(id) {
    const box = document.getElementById("disp-detail");
    box.innerHTML = `<div class="loading">加载中…</div>`;
    let detail, disp;
    try {
      detail = await API.get("/api/events/" + id);
      disp = await API.get("/api/events/" + id + "/disposal");
    } catch (e) { box.innerHTML = `<div class="loading">${e.message}</div>`; return; }

    const statusTag = STATUS.find((s) => s.k === disp.status) || { t: disp.status };
    box.innerHTML = `
      <h3><span class="dot"></span>${esc(detail.title)} · 处置协同</h3>
      <div class="row" style="margin:8px 0">
        <span class="tag tag-${detail.risk.grade}">风险等级 ${detail.risk.grade}（烈度 ${detail.risk.intensity}）</span>
        <span class="tag tag-neg">负面占比 ${Math.round(detail.sentiment.negative_ratio * 100)}%</span>
        <span class="tag tag-src">当前处置：${esc(statusTag.t)}</span>
      </div>
      <div class="section-title">风险等级人工复核</div>
      <div class="row">
        <span class="note">系统评定：</span>
        <select id="risk-override">
          ${["S", "A", "B", "C"].map((g) => `<option value="${g}" ${g === detail.risk.grade ? "selected" : ""}>${g}</option>`).join("")}
        </select>
        <span class="note">（人工复核仅前端标注，持久化可扩展）</span>
      </div>
      <div class="section-title">处置动作标记</div>
      <div class="row" id="status-btns">
        ${STATUS.map((s) => `<button class="btn ${s.k === disp.status ? "" : "ghost"}" data-k="${s.k}">${s.t}</button>`).join("")}
      </div>
      <div class="toolbar" style="margin-top:10px">
        <input id="handler" placeholder="处置人" value="${esc(disp.handler || "")}" style="max-width:160px" />
        <input id="note" class="grow" placeholder="处置备注 / 跟进说明" />
        <button class="btn" id="save-disp">保存处置</button>
      </div>
      <div id="disp-notes" class="note" style="margin-top:8px"></div>
      <div class="section-title">公关应对策略与回应话术草案</div>
      <div class="row">
        <button class="btn" id="gen-draft">生成 / 重新生成草案</button>
      </div>
      <div id="draft-box" style="margin-top:10px"></div>`;

    document.querySelectorAll("#status-btns button").forEach((b) => {
      b.onclick = () => {
        document.querySelectorAll("#status-btns button").forEach((x) => x.classList.add("ghost"));
        b.classList.remove("ghost");
        box.querySelector("#status-btns").dataset.sel = b.dataset.k;
      };
    });
    box.querySelector("#status-btns").dataset.sel = disp.status;

    document.getElementById("save-disp").onclick = async () => {
      const st = box.querySelector("#status-btns").dataset.sel || disp.status;
      const note = document.getElementById("note").value.trim();
      const handler = document.getElementById("handler").value.trim();
      try {
        await API.put("/api/events/" + id + "/disposal", { status: st, note: note || undefined, handler: handler || undefined });
        toast("处置状态已更新");
        loadDetail(id);
      } catch (e) { toast(e.message); }
    };

    document.getElementById("gen-draft").onclick = () => genDraft(id);
    // 若已有草案则直接展示
    try {
      const cfg = await API.get("/api/config");
      const existing = cfg.response_drafts && cfg.response_drafts[id];
      if (existing) showDraft(existing);
    } catch (e) { /* ignore */ }
    renderNotes(disp);
  }

  async function genDraft(id) {
    const box = document.getElementById("draft-box");
    box.innerHTML = `<div class="loading">大模型生成中…</div>`;
    try {
      const r = await API.post("/api/events/" + id + "/response-draft", {});
      showDraft(r.draft);
      toast("回应草案已生成");
    } catch (e) { box.innerHTML = `<div class="loading">${e.message}</div>`; }
  }

  function showDraft(d) {
    document.getElementById("draft-box").innerHTML = `
      <div class="note">事件性质：<b>${esc(d.category)}</b> ｜ 核心诉求：${esc(d.demand)}</div>
      <div class="section-title" style="margin:10px 0 6px">应对策略</div>
      <ul>${ (d.strategy || []).map((s) => `<li style="margin:4px 0">${esc(s)}</li>`).join("") }</ul>
      <div class="section-title" style="margin:10px 0 6px">回应话术草案</div>
      <pre class="draft">${esc(d.draft)}</pre>`;
  }

  function renderNotes(disp) {
    const el = document.getElementById("disp-notes");
    if (!disp.notes || !disp.notes.length) { el.textContent = "暂无处置备注"; return; }
    el.innerHTML = "处置备注：" + disp.notes.map((n) => `<div>· ${esc(n.note)}（${esc(n.at)}）</div>`).join("");
  }

  // 统一转义：兼容数字/布尔等非字符串字段，避免 .replace 抛 TypeError 中断渲染。
  function esc(s) { return String(s === null || s === undefined ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

  return { render };
})();
window.Disposal = Disposal;
