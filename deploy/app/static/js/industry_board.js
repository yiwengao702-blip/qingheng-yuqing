// 文件位置: backend/app/static/js/industry_board.js
// 功能: 通用行业看板「行业风险全景」——在通用舆情大盘之外，聚焦跨行业的监管维度
//       （用户权益 / 服务质量 / 安全隐患 / 宣传合规 / 合规风险 / 正面评价），
//       将通用事件按稳定 event_id 静态映射到上述维度，复用 /api/events、/api/overview、/api/config，
//       不做任何后端改造。渲染风格与 dashboard.js 保持一致（echarts 初始化、卡片栅格、词云）。
const IndustryBoard = (() => {
  // 行业监管维度（顺序即图表 x 轴顺序）
  const DIMENSIONS = [
    "用户权益", "服务质量", "安全隐患", "宣传合规", "合规风险", "正面评价",
  ];

  // event_id → 所属监管维度（一个事件可命中多个维度）。
  // 这些 event_id 在语料层是稳定的，前端静态映射足以支撑行业专属聚合。
  const DIM_MAP = {
    ev_g1: ["用户权益", "服务质量"],
    ev_g2: ["安全隐患", "服务质量"],
    ev_g3: ["宣传合规", "合规风险"],
    ev_g4: ["安全隐患", "合规风险"],
    ev_g5: ["用户权益", "服务质量"],
    ev_g6: ["正面评价"],
    ev_g7: ["用户权益", "服务质量"],
    ev_g8: ["宣传合规", "合规风险"],
  };

  // 风险等级 → 展示色（与态势大盘一致）
  const GRADE_COLOR = { S: "#b00", A: "#e08a00", B: "#f0c419", C: "#2f6df6" };
  const GRADE_ORDER = ["S", "A", "B", "C"];

  // 类别中文名归一（后端 category 已是中文，这里仅作兜底）
  function catLabel(c) {
    return ({ "合规风险": "合规风险", "服务纠纷": "服务纠纷", "质量争议": "质量争议",
              "公共事件": "公共事件", "其他": "其他" })[c] || c || "其他";
  }

  async function render() {
    const page = document.getElementById("page");
    page.innerHTML = `
      <h2>行业风险全景</h2>
      <div class="desc">通用行业视图 · 围绕用户权益、服务质量、安全隐患、宣传合规、合规风险、正面评价等维度聚合在测事件</div>
      <div class="grid cols-4" id="ib-metrics"></div>
      <div class="grid cols-2" style="margin-top:16px">
        <div class="card"><h3><span class="dot"></span>监管维度分布（事件数）</h3><div id="ib-dim" class="chart"></div></div>
        <div class="card"><h3><span class="dot"></span>风险等级 × 事件类别</h3><div id="ib-grade" class="chart"></div></div>
      </div>
      <div class="grid cols-2" style="margin-top:16px">
        <div class="card"><h3><span class="dot"></span>各维度风险强度（按事件综合强度）</h3><div id="ib-radar" class="chart"></div></div>
        <div class="card"><h3><span class="dot"></span>重点风险事件清单</h3><div id="ib-events" style="max-height:340px;overflow:auto"></div></div>
      </div>
      <div class="grid cols-1" style="margin-top:16px">
        <div class="card"><h3><span class="dot"></span>合规风险专项 · 处置要点</h3><div id="ib-compliance"></div></div>
      </div>`;

    // 并行拉取三个接口
    let eventsRes, ov, cfg;
    try {
      [eventsRes, ov, cfg] = await Promise.all([
        API.get("/api/events"),
        API.get("/api/overview"),
        API.get("/api/config").catch(() => ({})), // 配置非强依赖，缺失不影响主视图
      ]);
    } catch (e) {
      page.innerHTML = `<div class="loading">加载失败：${e.message}</div>`;
      return;
    }

    const events = (eventsRes && eventsRes.events) || [];
    const drafts = (cfg && cfg.response_drafts) || {};

    // —— 维度聚合 ——
    const dimEventCount = {};   // 维度 → 命中事件数
    const dimVolume = {};       // 维度 → 累计声量
    const dimIntensity = {};    // 维度 → 综合强度均值
    DIMENSIONS.forEach((d) => { dimEventCount[d] = 0; dimVolume[d] = 0; dimIntensity[d] = 0; });

    let highRisk = 0;           // S + A 事件数
    let complianceCount = 0;    // 合规风险类事件数
    let rightsRelated = 0;      // 用户权益相关
    const RIGHTS_DIMS = ["用户权益"];

    const enriched = events.map((ev) => {
      const dims = DIM_MAP[ev.event_id] || ["其他"];
      const isHigh = ev.grade === "S" || ev.grade === "A";
      if (isHigh) highRisk++;
      if (catLabel(ev.category) === "合规风险") complianceCount++;
      const hitRights = dims.some((d) => RIGHTS_DIMS.includes(d));
      if (hitRights) rightsRelated++;
      dims.forEach((d) => {
        if (!(d in dimEventCount)) return;
        dimEventCount[d] += 1;
        dimVolume[d] += (ev.volume || 0);
        dimIntensity[d] += (ev.intensity || 0);
      });
      return { ...ev, dims, isHigh };
    });

    // —— 指标卡 ——
    document.getElementById("ib-metrics").innerHTML = [
      { n: events.length, l: "在测事件" },
      { n: highRisk, l: "高风险事件（S+A）" },
      { n: complianceCount, l: "合规风险类事件" },
      { n: rightsRelated, l: "用户权益相关事件" },
    ].map((m) => `<div class="card metric"><div class="num">${m.n}</div><div class="lbl">${m.lbl}</div></div>`).join("");

    // —— 图 1：监管维度分布（事件数）——
    echarts.init(document.getElementById("ib-dim")).setOption({
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" },
        formatter: (ps) => {
          const p = ps[0];
          return `维度「${p.name}」<br/>命中事件：${p.value} 个 · 累计声量 ${dimVolume[p.name]} 条`;
        } },
      grid: { left: 70, right: 24, top: 16, bottom: 54 },
      xAxis: { type: "category", data: DIMENSIONS, axisLabel: { rotate: 38, fontSize: 11 } },
      yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#eef1f6" } } },
      series: [{
        type: "bar", barWidth: "52%",
        data: DIMENSIONS.map((d) => ({
          value: dimEventCount[d],
          itemStyle: { color: d === "正面评价" ? "#2bbf6a" : "#2f6df6", borderRadius: [6, 6, 0, 0] },
        })),
        label: { show: true, position: "top", fontSize: 11 },
      }],
    });

    // —— 图 2：风险等级 × 事件类别（堆叠柱状）——
    const cats = ["合规风险", "服务纠纷", "质量争议", "公共事件", "其他"];
    const gradeByCat = {}; // cat -> {S:..,A:..,B:..,C:..}
    cats.forEach((c) => { gradeByCat[c] = { S: 0, A: 0, B: 0, C: 0 }; });
    enriched.forEach((ev) => {
      const c = catLabel(ev.category);
      const g = (GRADE_ORDER.includes(ev.grade) ? ev.grade : "C");
      gradeByCat[c][g] += 1;
    });
    echarts.init(document.getElementById("ib-grade")).setOption({
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { data: GRADE_ORDER.map((g) => g + " 级"), top: 0, right: 8 },
      grid: { left: 44, right: 16, top: 36, bottom: 28 },
      xAxis: { type: "category", data: cats },
      yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: "#eef1f6" } } },
      series: GRADE_ORDER.map((g) => ({
        name: g + " 级",
        type: "bar",
        stack: "total",
        itemStyle: { color: GRADE_COLOR[g] },
        data: cats.map((c) => gradeByCat[c][g]),
      })),
    });

    // —— 图 3：各维度风险强度雷达 ——
    echarts.init(document.getElementById("ib-radar")).setOption({
      tooltip: {},
      radar: {
        radius: "66%",
        indicator: DIMENSIONS.map((d) => ({ name: d, max: 100 })),
        axisName: { fontSize: 10, color: "#5a6478" },
        splitArea: { areaStyle: { color: ["#fafbfd", "#f2f5fa"] } },
      },
      series: [{
        type: "radar",
        data: [{
          value: DIMENSIONS.map((d) => {
            const n = dimEventCount[d];
            return n ? Math.round(dimIntensity[d] / n) : 0;
          }),
          name: "维度风险强度",
          areaStyle: { color: "rgba(47,109,246,0.18)" },
          lineStyle: { color: "#2f6df6" },
          itemStyle: { color: "#2f6df6" },
        }],
      }],
    });

    // —— 重点风险事件清单（按等级排序，复用排序结果）——
    const evRows = enriched
      .slice()
      .sort((a, b) => GRADE_ORDER.indexOf(a.grade) - GRADE_ORDER.indexOf(b.grade))
      .map((ev) => {
        const g = GRADE_COLOR[ev.grade] || "#8a94a6";
        return `<tr>
          <td><span class="pill" style="background:${g}1a;color:${g}">${ev.grade}</span></td>
          <td class="ev-title">${ev.title || ev.event_id}</td>
          <td>${catLabel(ev.category)}</td>
          <td>${(ev.dims || []).join("、")}</td>
          <td>${ev.volume || 0}</td>
          <td>${((ev.negative_ratio || 0) * 100).toFixed(0)}%</td>
        </tr>`;
      }).join("");
    document.getElementById("ib-events").innerHTML = `
      <table class="tbl">
        <thead><tr><th>等级</th><th>事件</th><th>类别</th><th>维度</th><th>声量</th><th>负向比</th></tr></thead>
        <tbody>${evRows}</tbody>
      </table>`;

    // —— 合规风险专项 · 处置要点 ——
    const complianceEvents = enriched.filter((ev) => catLabel(ev.category) === "合规风险");
    const compHtml = complianceEvents.length
      ? complianceEvents.map((ev) => {
          const draft = drafts[ev.event_id];
          const strat = draft && draft.strategy ? draft.strategy
            : (ev.summary || "暂无专项处置策略，建议结合事件研判结论制定应对口径。");
          return `<div class="comp-item">
            <div class="comp-head"><span class="pill" style="background:${GRADE_COLOR[ev.grade] || "#8a94a6"}1a;color:${GRADE_COLOR[ev.grade] || "#8a94a6"}">${ev.grade}</span>
              <b>${ev.title || ev.event_id}</b><span class="comp-dim">${(ev.dims || []).join("、")}</span></div>
            <div class="comp-body">${strat}</div>
          </div>`;
        }).join("")
      : `<div class="note">当前无合规风险类事件。</div>`;
    document.getElementById("ib-compliance").innerHTML = compHtml;
  }

  return { render };
})();
window.IndustryBoard = IndustryBoard;
