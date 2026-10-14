// 文件位置: backend/app/static/js/config.js
// 功能: 监测配置 —— 监测主题词包、信源接入开关与权重、预警告警阈值规则、通知渠道。
//       按角色权限：管理员可配置信源/阈值/通知；分析师可维护主题词包；公关仅查看。
const Config = (() => {
  async function render() {
    const page = document.getElementById("page");
    page.innerHTML = `
      <h2>监测配置</h2>
      <div class="desc">配置监测主题词包、信源接入通道、预警阈值与通知渠道（修改即时生效并持久化）</div>
      <div class="grid cols-2">
        <div class="card" id="cfg-topics"><h3><span class="dot"></span>监测主题词包</h3><div class="loading">加载中…</div></div>
        <div class="card" id="cfg-sources"><h3><span class="dot"></span>信源接入通道</h3><div class="loading">加载中…</div></div>
      </div>
      <div class="grid cols-2" style="margin-top:16px">
        <div class="card" id="cfg-thresholds"><h3><span class="dot"></span>预警告警阈值规则</h3><div class="loading">加载中…</div></div>
        <div class="card" id="cfg-notify"><h3><span class="dot"></span>通知渠道</h3><div class="loading">加载中…</div></div>
      </div>`;

    let cfg;
    try { cfg = await API.get("/api/config"); }
    catch (e) { page.innerHTML = `<div class="loading">${e.message}</div>`; return; }

    renderTopics(cfg);
    renderSources(cfg);
    renderThresholds(cfg);
    renderNotify(cfg);
  }

  function renderTopics(cfg) {
    const box = document.getElementById("cfg-topics");
    const canEdit = Store.has("topic:manage");
    box.innerHTML = cfg.topic_packs.map((t) => `
      <div class="config-row">
        <div><b>${esc(t.name)}</b><div class="note">${(t.keywords || []).map(esc).join("、")}</div></div>
        ${canEdit ? `<button class="btn ghost" data-id="${t.id}">删除</button>` : `<span class="tag tag-src">仅查看</span>`}
      </div>`).join("") + (canEdit ? `<div class="toolbar" style="margin-top:10px">
        <input id="tp-name" placeholder="新主题名称" style="max-width:160px" />
        <input id="tp-kw" class="grow" placeholder="关键词，逗号分隔" />
        <button class="btn" id="tp-add">添加</button>
      </div>` : "");
    if (canEdit) {
      box.querySelectorAll("button[data-id]").forEach((b) => {
        b.onclick = async () => {
          try { await API.del("/api/config/topics/" + b.dataset.id); toast("已删除"); render(); }
          catch (e) { toast(e.message); }
        };
      });
      document.getElementById("tp-add").onclick = async () => {
        const name = document.getElementById("tp-name").value.trim();
        const kw = document.getElementById("tp-kw").value.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
        if (!name) { toast("请填写主题名称"); return; }
        try {
          await API.post("/api/config/topics", { id: "tp_" + Date.now(), name, keywords: kw, enabled: true });
          toast("已添加"); render();
        } catch (e) { toast(e.message); }
      };
    }
  }

  function renderSources(cfg) {
    const box = document.getElementById("cfg-sources");
    const canEdit = Store.has("source:config");
    box.innerHTML = cfg.source_channels.map((c) => `
      <div class="config-row">
        <div><b>${esc(c.name)}</b> <span class="tag tag-src">${esc(c.type)}</span><div class="note">权重 ${c.weight}</div></div>
        <label class="switch"><input type="checkbox" data-id="${c.source_id}" ${c.enabled ? "checked" : ""} ${canEdit ? "" : "disabled"}/><span class="slider"></span></label>
      </div>`).join("") + (canEdit ? `<button class="btn" id="src-save" style="margin-top:10px">保存信源配置</button>` : `<div class="note" style="margin-top:8px">当前角色无修改权限</div>`);
    if (canEdit) {
      document.getElementById("src-save").onclick = async () => {
        const updates = cfg.source_channels.map((c) => ({
          source_id: c.source_id,
          enabled: box.querySelector(`input[data-id="${c.source_id}"]`).checked,
          weight: c.weight,
        }));
        try { await API.put("/api/config/sources", updates); toast("信源配置已保存"); }
        catch (e) { toast(e.message); }
      };
    }
  }

  function renderThresholds(cfg) {
    const box = document.getElementById("cfg-thresholds");
    const canEdit = Store.has("threshold:config");
    const r = cfg.threshold_rules;
    box.innerHTML = `
      <div class="config-row"><span>负面声量占比阈值</span><input id="th-neg" type="number" step="0.01" min="0" max="1" value="${r.negative_ratio}" ${canEdit ? "" : "disabled"} style="width:90px" /></div>
      <div class="config-row"><span>声量阈值（触发关注）</span><input id="th-vol" type="number" min="0" value="${r.volume}" ${canEdit ? "" : "disabled"} style="width:90px" /></div>
      <div class="config-row"><span>突发环比倍数</span><input id="th-burst" type="number" step="0.1" min="1" value="${r.burst_multiplier}" ${canEdit ? "" : "disabled"} style="width:90px" /></div>
      ${canEdit ? `<button class="btn" id="th-save" style="margin-top:10px">保存阈值</button>` : `<div class="note" style="margin-top:8px">当前角色无修改权限</div>`}`;
    if (canEdit) {
      document.getElementById("th-save").onclick = async () => {
        const body = {
          negative_ratio: parseFloat(document.getElementById("th-neg").value),
          volume: parseInt(document.getElementById("th-vol").value, 10),
          burst_multiplier: parseFloat(document.getElementById("th-burst").value),
        };
        try { await API.put("/api/config/thresholds", body); toast("阈值已保存"); }
        catch (e) { toast(e.message); }
      };
    }
  }

  function renderNotify(cfg) {
    const box = document.getElementById("cfg-notify");
    const canEdit = Store.has("notification:config");
    const all = ["站内消息", "邮件", "短信", "企业微信"];
    box.innerHTML = all.map((c) => `
      <div class="config-row"><span>${c}</span>
        <label class="switch"><input type="checkbox" data-ch="${c}" ${cfg.notification_channels.includes(c) ? "checked" : ""} ${canEdit ? "" : "disabled"}/><span class="slider"></span></label>
      </div>`).join("") + (canEdit ? `<button class="btn" id="nt-save" style="margin-top:10px">保存通知渠道</button>` : `<div class="note" style="margin-top:8px">当前角色无修改权限</div>`);
    if (canEdit) {
      document.getElementById("nt-save").onclick = async () => {
        const channels = all.filter((c) => box.querySelector(`input[data-ch="${c}"]`).checked);
        try { await API.put("/api/config/notifications", { channels }); toast("通知渠道已保存"); }
        catch (e) { toast(e.message); }
      };
    }
  }

  // 统一转义：兼容数字/布尔等非字符串字段，避免 .replace 抛 TypeError 中断渲染。
  function esc(s) { return String(s === null || s === undefined ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

  return { render };
})();
window.Config = Config;
