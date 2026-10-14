// 文件位置: backend/app/static/js/feed.js
// 功能: 舆情监测流 —— 多维筛选（主题/信源/时间/情感/风险）+ 多源卡片 + 多模态原文详情。
const Feed = (() => {
  let state = { source_types: [], sentiments: [], risk_grades: [], q: "", page: 1, page_size: 15, event_id: "" };

  async function render() {
    const page = document.getElementById("page");
    page.innerHTML = `
      <h2>舆情监测流</h2>
      <div class="desc">全网多源内容实时滚动 · 支持按主题/信源/时间/情感/风险等级多维筛选</div>
      <div class="toolbar">
        <select id="f-event"><option value="">全部事件</option></select>
        <select id="f-source"><option value="">全部信源</option></select>
        <select id="f-sent">
          <option value="">全部情感</option><option value="positive">正面</option>
          <option value="neutral">中性</option><option value="negative">负面</option>
        </select>
        <select id="f-risk">
          <option value="">全部风险</option><option value="S">S 特别重大</option>
          <option value="A">A 重大</option><option value="B">B 较大</option><option value="C">C 一般</option>
        </select>
        <input id="f-q" class="grow" placeholder="搜索关键词（内容/实体）" />
        <button class="btn" id="f-search">筛选</button>
        <button class="btn ghost" id="f-reset">重置</button>
      </div>
      <div id="feed-list" class="feed-list"><div class="loading">加载中…</div></div>
      <div class="pager" id="pager"></div>`;

    // 事件下拉
    try {
      const evs = await API.get("/api/events");
      const sel = document.getElementById("f-event");
      evs.events.forEach((e) => {
        const o = document.createElement("option");
        o.value = e.event_id; o.textContent = `${e.title}（${e.grade}）`;
        sel.appendChild(o);
      });
    } catch (e) { toast(e.message); }

    document.getElementById("f-search").onclick = () => {
      state.event_id = document.getElementById("f-event").value;
      state.source_types = [document.getElementById("f-source").value].filter(Boolean);
      state.sentiments = [document.getElementById("f-sent").value].filter(Boolean);
      state.risk_grades = [document.getElementById("f-risk").value].filter(Boolean);
      state.q = document.getElementById("f-q").value.trim();
      state.page = 1;
      load();
    };
    document.getElementById("f-reset").onclick = () => {
      state = { source_types: [], sentiments: [], risk_grades: [], q: "", page: 1, page_size: 15, event_id: "" };
      document.getElementById("f-event").value = "";
      document.getElementById("f-source").value = "";
      document.getElementById("f-sent").value = "";
      document.getElementById("f-risk").value = "";
      document.getElementById("f-q").value = "";
      load();
    };
    await load();
  }

  async function load() {
    const box = document.getElementById("feed-list");
    box.innerHTML = `<div class="loading">加载中…</div>`;
    const qs = new URLSearchParams();
    if (state.event_id) qs.set("event_id", state.event_id);
    state.source_types.forEach((s) => qs.append("source_types", s));
    state.sentiments.forEach((s) => qs.append("sentiments", s));
    state.risk_grades.forEach((s) => qs.append("risk_grades", s));
    if (state.q) qs.set("q", state.q);
    qs.set("page", state.page);
    qs.set("page_size", state.page_size);
    let data;
    try { data = await API.get("/api/feed?" + qs.toString()); }
    catch (e) { box.innerHTML = `<div class="loading">加载失败：${e.message}</div>`; return; }

    if (!data.items.length) { box.innerHTML = `<div class="loading">无符合条件的舆情</div>`; }
    else {
      box.innerHTML = data.items.map(cardHtml).join("");
      attachCardClickHandlers();
    }
    // 分页
    const pager = document.getElementById("pager");
    const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
    pager.innerHTML = `
      <button id="prev" ${state.page <= 1 ? "disabled" : ""}>上一页</button>
      <span class="note">第 ${state.page}/${totalPages} 页 · 共 ${data.total} 条</span>
      <button id="next" ${state.page >= totalPages ? "disabled" : ""}>下一页</button>`;
    if (document.getElementById("prev")) document.getElementById("prev").onclick = () => { state.page--; load(); };
    if (document.getElementById("next")) document.getElementById("next").onclick = () => { state.page++; load(); };
  }

  function cardHtml(p) {
    const ct = p.content_type === "ocr" ? "图文" : p.content_type === "transcript" ? "音视频" : "文本";
    const multi = p.content_type === "ocr" && p.ocr_text
      ? `<div class="multi"><b>图片OCR：</b>${esc(p.ocr_text)}</div>`
      : p.content_type === "transcript" && p.transcript_text
      ? `<div class="multi"><b>音视频转写：</b>${esc(p.transcript_text)}</div>`
      : "";
    const ents = (p.entities || []).map((e) => `<span class="pill">${esc(e)}</span>`).join("");
    const sens = p.sensitive_hit ? `<span class="tag tag-neg">敏感词命中</span>` : "";
    return `<div class="feed-card" data-event-id="${esc(p.event_id || "")}" style="cursor:pointer">
      <div class="meta">
        <span class="tag tag-src">${esc(p.platform)}·${esc(p.source_type)}</span>
        <span class="tag tag-${p.sentiment}">${sentLabel(p.sentiment)}</span>
        <span class="tag tag-${p.risk_grade}">风险 ${p.risk_grade}</span>
        <span class="tag tag-src">${ct}</span>
        ${sens}
        <span>${esc(p.author)}</span><span>互动 ${p.interaction}</span><span>${esc(p.publish_time || "")}</span><span>${esc(p.region || "")}</span>
      </div>
      <div class="content">${esc(p.content)}</div>
      ${multi}
      ${ents ? `<div style="margin-top:6px">${ents}</div>` : ""}
    </div>`;
  }

  function sentLabel(s) { return s === "positive" ? "正面" : s === "negative" ? "负面" : "中性"; }
  // 统一转义：兼容数字/布尔等非字符串字段，避免 .replace 抛 TypeError 中断渲染。
  function esc(s) { return String(s === null || s === undefined ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

  // 卡片点击：跳转到对应事件的研判工作台详情页
  function attachCardClickHandlers() {
    document.querySelectorAll(".feed-card[data-event-id]").forEach((card) => {
      card.onclick = () => {
        const eventId = card.dataset.eventId;
        if (!eventId) return;
        // 通过 window.App.go 切换页面，然后用全局回调通知 EventPage 选中该事件
        if (window.App && window.App.go) {
          window.App.go("event");
          // EventPage 加载完成后会自动选中第一项；
          // 我们通过 window._feedPendingEventId 传递目标事件 ID，
          // EventPage.render 会检查该标志并跳过自动选中
          window._feedPendingEventId = eventId;
          // 额外等待确保 DOM 渲染完成
          setTimeout(() => {
            const item = document.querySelector(`.event-item[data-id="${eventId}"]`);
            if (item) item.click();
          }, 500);
        }
      };
    });
  }

  return { render };
})();
window.Feed = Feed;
