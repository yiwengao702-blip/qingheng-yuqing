// 文件位置: backend/app/static/js/event.js
// 功能: 事件研判工作台 —— 事件列表 + 传播溯源时间线 + 核心观点聚类 + 实体关系图谱 + 多模态原文。
const EventPage = (() => {
  async function render() {
    const page = document.getElementById("page");
    page.innerHTML = `
      <h2>研判工作台</h2>
      <div class="desc">选择事件进行深度研判：传播溯源、核心争议观点聚类、实体关系图谱与多模态原文</div>
      <div class="event-grid">
        <div class="card"><h3><span class="dot"></span>在监测事件</h3><div id="ev-list" class="loading">加载中…</div></div>
        <div class="card"><h3><span class="dot"></span>事件概览</h3><div id="ev-detail"><div class="note">请选择左侧事件</div></div></div>
      </div>
      <div id="ev-detail-full"></div>`;

    let list;
    try { list = await API.get("/api/events"); }
    catch (e) { document.getElementById("ev-list").innerHTML = `<div class="loading">${e.message}</div>`; return; }
    document.getElementById("ev-list").innerHTML = list.events
      .map((e) => `<div class="event-item" data-id="${e.event_id}">
        <div class="title">${esc(e.title)} <span class="tag tag-${e.grade}">${e.grade}</span></div>
        <div class="note">${esc(e.category)} · 声量 ${e.volume} · 负面占比 ${Math.round(e.negative_ratio * 100)}% · 烈度 ${e.intensity}</div>
      </div>`).join("");
    document.querySelectorAll("#ev-list .event-item").forEach((el) => {
      el.onclick = () => loadDetail(el.dataset.id);
    });
    // 如果 Feed 页面请求跳转到特定事件（通过 window._feedPendingEventId 传递）
    const pendingId = window._feedPendingEventId;
    if (pendingId) {
      delete window._feedPendingEventId;
      const item = document.querySelector(`.event-item[data-id="${pendingId}"]`);
      if (item) {
        item.click();
        // 滚动到事件列表可见区域
        item.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
    }
    if (list.events.length) loadDetail(list.events[0].event_id);
  }

  async function loadDetail(id) {
    const box = document.getElementById("ev-detail");
    const full = document.getElementById("ev-detail-full");
    box.innerHTML = `<div class="loading">加载中…</div>`;
    full.innerHTML = "";
    let d;
    try { d = await API.get("/api/events/" + id); }
    catch (e) { box.innerHTML = `<div class="loading">${e.message}</div>`; return; }

    box.innerHTML = `
      <div style="font-weight:700;font-size:15px">${esc(d.title)} <span class="tag tag-${d.risk.grade}">风险 ${d.risk.grade}</span></div>
      <div class="note" style="margin:6px 0">${esc(d.category)} · 烈度指数 ${d.risk.intensity}</div>
      <div class="row" style="margin-top:6px">
        <span class="tag tag-pos">正面 ${d.sentiment.positive}</span>
        <span class="tag tag-neu">中性 ${d.sentiment.neutral}</span>
        <span class="tag tag-neg">负面 ${d.sentiment.negative}</span>
      </div>
      <div class="note" style="margin-top:8px;line-height:1.6">${esc(d.summary || "")}</div>`;

    const emo = d.emotion || {};
    const prop = d.propagation || {};
    const tl = (prop.timeline || []).slice(-12);
    full.innerHTML = `
      <div class="grid cols-2" style="margin-top:14px">
        <div class="card"><h3><span class="dot"></span>舆情声量时间线（近 12 小时）</h3><div id="ev-trend" class="chart sm"></div></div>
        <div class="card"><h3><span class="dot"></span>细粒度情绪分布</h3><div id="ev-emotion" class="chart sm"></div></div>
      </div>
      <div class="grid cols-2" style="margin-top:16px">
        <div class="card"><h3><span class="dot"></span>传播脉络溯源时间线</h3>
          <div class="timeline">${timelineHtml(prop)}</div>
        </div>
        <div class="card"><h3><span class="dot"></span>实体关系图谱</h3><div id="ev-graph" class="chart" style="height:340px"></div></div>
      </div>
      <div class="section-title">核心争议观点聚类（${ (d.viewpoints||[]).length } 簇）</div>
      <div id="ev-clusters"></div>
      <div class="section-title">多模态原文 · 高互动样本</div>
      <div id="ev-posts" class="feed-list"></div>`;

    // 趋势
    echarts.init(document.getElementById("ev-trend")).setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 40, right: 16, top: 20, bottom: 40 },
      xAxis: { type: "category", data: tl.map((t) => t.hour.slice(5)), axisLabel: { rotate: 40, fontSize: 10 } },
      yAxis: { type: "value" },
      series: [{ type: "line", smooth: true, data: tl.map((t) => t.volume), areaStyle: { opacity: .15 } }],
    });
    // 情绪
    // 与大屏一致：只画负向主导情绪细分，「非负向」数量以 title 副标题给出，避免压扁刻度。
    const NEG_EMO_ORDER = ["愤怒", "失望", "恐慌", "质疑", "其他负向"];
    const NEG_EMO_COLOR = { "愤怒": "#e23b3b", "失望": "#e08a00", "恐慌": "#8a4fd3", "质疑": "#2f6df6", "其他负向": "#8a94a6" };
    const emoNeg = NEG_EMO_ORDER.map((k) => ({ name: k, value: emo[k] || 0 }));
    const emoNegSum = emoNeg.reduce((a, b) => a + b.value, 0);
    const emoNonNeg = emo["非负向"] || 0;
    echarts.init(document.getElementById("ev-emotion")).setOption({
      title: {
        text: `负向合计 ${emoNegSum} 条 · 非负向 ${emoNonNeg} 条（未计入刻度）`,
        left: 4, top: 0,
        textStyle: { fontSize: 11, fontWeight: "normal", color: "#8a94a6" },
      },
      tooltip: {
        trigger: "axis",
        formatter: (ps) => {
          const p = ps[0];
          const pct = emoNegSum ? ((p.value / emoNegSum) * 100).toFixed(1) : "0.0";
          return `负向情绪「${p.name}」<br/>样本：${p.value} 条（占负向 ${pct}%）`;
        },
      },
      grid: { left: 64, right: 40, top: 30, bottom: 18 },
      xAxis: { type: "value", splitLine: { lineStyle: { color: "#eef1f6" } } },
      yAxis: { type: "category", data: emoNeg.map((x) => x.name).reverse(), axisLabel: { fontSize: 12 }, axisTick: { show: false } },
      series: [{
        type: "bar", barWidth: 16,
        data: emoNeg.slice().reverse().map((x) => ({ value: x.value, itemStyle: { color: NEG_EMO_COLOR[x.name], borderRadius: [0, 6, 6, 0] } })),
        label: { show: true, position: "right", fontSize: 11, formatter: "{c}" },
      }],
    });
    // 实体图谱
    const g = d.entity_graph || { nodes: [], edges: [] };
    echarts.init(document.getElementById("ev-graph")).setOption({
      tooltip: {},
      legend: { data: [...new Set(g.nodes.map((n) => n.type))], top: 0 },
      series: [{
        type: "graph", layout: "force", roam: true,
        label: { show: true, fontSize: 11 },
        categories: [...new Set(g.nodes.map((n) => n.type))].map((t) => ({ name: t })),
        data: g.nodes.map((n) => ({ name: n.name, value: n.value, category: n.type,
          symbolSize: 14 + Math.min(30, n.value * 3) })),
        edges: g.edges.map((e) => ({ source: e.source, target: e.target, value: e.value,
          lineStyle: { width: Math.min(6, e.value) } })),
        force: { repulsion: 120, edgeLength: 90 },
      }],
    });
    // 观点聚类
    document.getElementById("ev-clusters").innerHTML = (d.viewpoints || [])
      .map((c) => `<div class="cluster">
        <div class="head"><span>观点簇「${esc(c.label)}」· ${c.size} 条</span><span class="intent">${esc(c.intent)}</span></div>
        <div class="note">情感：${sentDist(c.sentiment_dist)} ｜ 关键词：${(c.keywords||[]).map(esc).join("、")}</div>
        <div class="multi" style="margin-top:6px"><b>代表样本：</b>${esc(c.representative.content)}</div>
      </div>`).join("");
    // 原文
    document.getElementById("ev-posts").innerHTML = (d.top_posts || []).map((p) => {
      const ct = p.content_type === "ocr" ? "图文OCR" : p.content_type === "transcript" ? "音视频转写" : "文本";
      const extra = p.ocr_text ? `<div class="multi"><b>图片OCR：</b>${esc(p.ocr_text)}</div>`
        : p.transcript_text ? `<div class="multi"><b>音视频转写：</b>${esc(p.transcript_text)}</div>` : "";
      return `<div class="feed-card">
        <div class="meta">
          <span class="tag tag-src">${esc(p.platform)}</span>
          <span class="tag tag-${p.sentiment}">${sentLabel(p.sentiment)}</span>
          <span class="tag tag-${p.risk_grade}">风险 ${p.risk_grade}</span>
          <span class="tag tag-src">${ct}</span>
          <span>${esc(p.author)}</span><span>互动 ${p.interaction}</span><span>${esc(p.publish_time||"")}</span>
        </div>
        <div class="content">${esc(p.content)}</div>${extra}
      </div>`;
    }).join("");
  }

  function timelineHtml(prop) {
    const items = [];
    if (prop.origin) items.push({ t: prop.origin.publish_time, title: "首发信源", body: prop.origin.content, warn: false });
    (prop.key_nodes || []).slice(0, 4).forEach((k) => {
      items.push({ t: k.publish_time, title: `${k.role} · ${k.author}`, body: `${k.platform} 互动 ${k.interaction}`, warn: true });
    });
    (prop.timeline || []).slice(-3).forEach((t) => {
      items.push({ t: t.hour, title: "小时声量 " + t.volume, body: `负面 ${t.negative}（占比 ${Math.round(t.negative_ratio * 100)}%）`, warn: false });
    });
    return items.map((i) => `<div class="tl-item ${i.warn ? "warn" : ""}">
      <div style="font-weight:600;font-size:13px">${esc(i.title)}</div>
      <div class="note">${esc(i.t || "")}</div>
      <div class="note">${esc(i.body || "")}</div></div>`).join("");
  }

  function sentLabel(s) { return s === "positive" ? "正面" : s === "negative" ? "负面" : "中性"; }
  function sentDist(d) { return `正面${d.positive}/中性${d.neutral}/负面${d.negative}`; }
  // 统一转义：兼容数字/布尔等非字符串字段，避免 .replace 抛 TypeError 中断渲染。
  function esc(s) { return String(s === null || s === undefined ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

  return { render };
})();
window.EventPage = EventPage;
