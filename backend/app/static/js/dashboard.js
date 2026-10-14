// 文件位置: backend/app/static/js/dashboard.js
// 功能: 舆情态势大盘 —— 声量趋势、情感分布、实时风险预警滚动、热点词云、风险分布。
const Dashboard = (() => {
  async function render() {
    const page = document.getElementById("page");
    page.innerHTML = `
      <h2>舆情态势大盘</h2>
      <div class="desc">全网多源舆情实时态势感知 · 数据每访问刷新一次，预警通过下方滚动列表实时推送</div>
      <div class="grid cols-4" id="metrics"></div>
      <div class="grid cols-1" style="margin-top:16px">
        <div class="card"><h3><span class="dot"></span>在监测事件一览（点击进入研判工作台）</h3><div id="ev-chips" class="loading">加载中…</div></div>
      </div>
      <div class="grid cols-2" style="margin-top:16px">
        <div class="card"><h3><span class="dot"></span>全网舆情声量趋势（小时）</h3><div id="trend" class="chart"></div></div>
        <div class="card"><h3><span class="dot"></span>情感倾向分布</h3><div id="sentiment" class="chart sm"></div></div>
      </div>
      <div class="grid cols-3" style="margin-top:16px">
        <div class="card"><h3><span class="dot"></span>实时风险预警</h3><div id="alerts" class="alert-feed"><div class="loading">连接预警通道…</div></div></div>
        <div class="card"><h3><span class="dot"></span>热点词云</h3><div id="words" class="wordcloud"></div></div>
        <div class="card"><h3><span class="dot"></span>风险等级分布</h3><div id="risk" class="chart sm"></div></div>
      </div>
      <div class="grid cols-2" style="margin-top:16px">
        <div class="card"><h3><span class="dot"></span>信源分布</h3><div id="source" class="chart sm"></div></div>
        <div class="card"><h3><span class="dot"></span>细粒度情绪分布</h3><div id="emotion" class="chart sm"></div></div>
      </div>`;

    let ov;
    try {
      ov = await API.get("/api/overview");
    } catch (e) {
      page.innerHTML = `<div class="loading">加载失败：${e.message}</div>`;
      return;
    }

    // 一并拉取事件列表，用于「在监测事件一览」快捷入口（与大盘聚合解耦，互不影响）
    let evList = { events: [] };
    try { evList = await API.get("/api/events"); } catch (e) {}

    // 指标卡
    document.getElementById("metrics").innerHTML = [
      { n: ov.total_volume, l: "监测总声量（去重）" },
      { n: ov.event_count, l: "在监测事件" },
      { n: ov.alert_count, l: "活跃预警" },
      { n: ov.dedup.duplicates, l: "SimHash 去重命中" },
    ].map((m) => `<div class="card metric"><div class="num">${m.n}</div><div class="lbl">${m.l}</div></div>`).join("");

    // 在监测事件一览：按风险等级排序的可点击标签，点击直达研判工作台
    const chipsBox = document.getElementById("ev-chips");
    const allEvents = (evList.events || []).slice();
    const GRADE_ORDER = { S: 0, A: 1, B: 2, C: 3 };
    allEvents.sort((a, b) => ((GRADE_ORDER[a.grade] ?? 9) - (GRADE_ORDER[b.grade] ?? 9)));
    if (chipsBox) {
      chipsBox.className = "ev-chips";
      if (allEvents.length) {
        chipsBox.innerHTML = allEvents.map((e) =>
          `<span class="tag tag-${e.grade} ev-chip" data-id="${e.event_id}" title="${esc(e.title)}">${e.grade} · ${esc(e.title)}</span>`
        ).join("");
        chipsBox.querySelectorAll(".ev-chip").forEach((el) => {
          el.onclick = () => { window._feedPendingEventId = el.dataset.id; App.go("event"); };
        });
      } else {
        chipsBox.innerHTML = `<div class="note">暂无在监测事件</div>`;
      }
    }

    // 声量趋势
    const trend = ov.trend || [];
    echarts.init(document.getElementById("trend")).setOption({
      tooltip: { trigger: "axis" },
      legend: { data: ["声量", "负面"], right: 10, top: 0 },
      grid: { left: 40, right: 16, top: 36, bottom: 30 },
      xAxis: { type: "category", data: trend.map((t) => t.hour), axisLabel: { rotate: 40, fontSize: 10 } },
      yAxis: { type: "value" },
      series: [
        { name: "声量", type: "line", smooth: true, data: trend.map((t) => t.volume), areaStyle: { opacity: .15 } },
        { name: "负面", type: "bar", data: trend.map((t) => t.negative), itemStyle: { color: "#e23b3b" } },
      ],
    });

    // 情感分布
    const s = ov.sentiment;
    echarts.init(document.getElementById("sentiment")).setOption({
      tooltip: { trigger: "item" },
      series: [{
        type: "pie", radius: ["45%", "72%"], center: ["50%", "52%"],
        label: { formatter: "{b}\n{d}%", fontSize: 12 },
        data: [
          { name: "正面", value: s.positive, itemStyle: { color: "#2bbf6a" } },
          { name: "中性", value: s.neutral, itemStyle: { color: "#f0a93b" } },
          { name: "负面", value: s.negative, itemStyle: { color: "#e23b3b" } },
        ],
      }],
    });

    // 风险分布
    const r = ov.risk_distribution;
    echarts.init(document.getElementById("risk")).setOption({
      tooltip: { trigger: "item" },
      series: [{
        type: "pie", radius: ["45%", "72%"], center: ["50%", "52%"],
        label: { formatter: "{b}\n{d}%", fontSize: 12 },
        data: [
          { name: "S 特别重大", value: r.S || 0, itemStyle: { color: "#b00" } },
          { name: "A 重大", value: r.A || 0, itemStyle: { color: "#e08a00" } },
          { name: "B 较大", value: r.B || 0, itemStyle: { color: "#f0c419" } },
          { name: "C 一般", value: r.C || 0, itemStyle: { color: "#2f6df6" } },
        ],
      }],
    });

    // 信源分布
    const src = ov.source_distribution || {};
    echarts.init(document.getElementById("source")).setOption({
      tooltip: { trigger: "item" },
      series: [{
        type: "pie", radius: "68%", center: ["50%", "52%"],
        label: { formatter: "{b}\n{d}%", fontSize: 11 },
        data: Object.entries(src).map(([k, v]) => ({ name: k, value: v })),
      }],
    });

    // 细粒度情绪分布
    // 说明：emotion_distribution 含「非负向」且数量往往远大于各负向细分，
    // 若直接整体画条形会把负向刻度假压成一条线，故只画负向主导情绪 5 项，
    // 负向合计 / 非负向数量以 title 副标题形式给出，信息不丢失。
    const emoAll = ov.emotion || {};
    const NEG_EMO_ORDER = ["愤怒", "失望", "恐慌", "质疑", "其他负向"];
    const NEG_EMO_COLOR = { "愤怒": "#e23b3b", "失望": "#e08a00", "恐慌": "#8a4fd3", "质疑": "#2f6df6", "其他负向": "#8a94a6" };
    const emoNeg = NEG_EMO_ORDER.map((k) => ({ name: k, value: emoAll[k] || 0 }));
    const emoNegSum = emoNeg.reduce((a, b) => a + b.value, 0);
    const emoNonNeg = emoAll["非负向"] || 0;
    echarts.init(document.getElementById("emotion")).setOption({
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

    // 热点词云（自定义标签，按权重缩放字号）
    const words = (ov.hotwords || []).slice(0, 40);
    const maxw = Math.max(...words.map((w) => w.weight), 1);
    document.getElementById("words").innerHTML = words
      .map((w) => {
        const size = 12 + Math.round((w.weight / maxw) * 26);
        const hue = 210 - Math.round((w.weight / maxw) * 40);
        return `<span style="font-size:${size}px;color:hsl(${hue},70%,42%)" title="权重 ${w.weight}">${w.word}</span>`;
      }).join("");

    // 连接 SSE 预警
    connectAlerts(document.getElementById("alerts"));
  }

  // 单条预警 DOM（SSE 与 REST 兜底共用）
  function alertItemEl(a) {
    const el = document.createElement("div");
    el.className = "alert-item " + (a.level || "");
    el.innerHTML = `<span class="lv">${a.level || ""}</span><div class="t">[${a.type}] ${a.title}</div><div class="d">${a.detail || ""}<br/><span class="note">${a.time || ""}</span></div>`;
    return el;
  }

  function connectAlerts(box) {
    // 与 api.js 同样的兼容兜底：token / access_token 双键兼容
    const a = window.__auth || {};
    const token = a.token || a.access_token;
    if (!token) return;
    const es = new EventSource("/api/stream/alerts?token=" + encodeURIComponent(token));
    box.innerHTML = "";
    let got = false; // 是否已收到任意 SSE 事件
    es.addEventListener("alert", (ev) => {
      got = true;
      box.prepend(alertItemEl(JSON.parse(ev.data)));
      while (box.children.length > 30) box.removeChild(box.lastChild);
    });
    es.addEventListener("connected", (ev) => {
      got = true;
      const d = JSON.parse(ev.data);
      const el = document.createElement("div");
      el.className = "note";
      el.style.padding = "4px 0";
      el.textContent = `预警通道已建立，存量预警 ${d.total} 条`;
      box.appendChild(el);
    });
    es.onerror = () => { /* 浏览器会自动重连 */ };
    window.__alertES = es;

    // 兜底：部分托管平台的反向代理会缓冲 SSE 流（迟迟不推送），
    // 若 3.5s 内一条事件都没到，则改用 REST 拉取存量预警，保证大盘有数据。
    setTimeout(async () => {
      if (got) return;
      try {
        const data = await API.get("/api/alerts");
        if (got) return; // 兜底期间 SSE 恢复则不覆盖
        box.innerHTML = "";
        (data.alerts || []).slice(0, 30).forEach((x) => box.prepend(alertItemEl(x)));
        const tip = document.createElement("div");
        tip.className = "note";
        tip.style.padding = "4px 0";
        tip.textContent = `已加载存量预警 ${data.total} 条`;
        box.appendChild(tip);
      } catch (e) {
        box.innerHTML = `<div class="note" style="padding:6px 0">预警数据暂不可用（${e.message}）</div>`;
      }
    }, 3500);
  }

  return { render };
})();
window.Dashboard = Dashboard;
