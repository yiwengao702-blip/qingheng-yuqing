// 文件位置: backend/app/static/js/online.js
// 功能: 用户管理（管理员专属独立页）—— 列出系统中所有已注册用户，
//       在线用户靠前高亮，支持对任意账号加时（刷新在线状态 +30 天）或删除。
const OnlineAccounts = (() => {
  function esc(s) { return String(s === null || s === undefined ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

  // 角色徽章：英文角色 → 中文彩色徽章（管理员金 / 分析师蓝 / 公关青）
  function roleBadge(role) {
    const map = {
      admin:   { text: "管理员", cls: "rb-admin" },
      analyst: { text: "分析师", cls: "rb-analyst" },
      pr:      { text: "公关",   cls: "rb-pr" },
    };
    const r = map[role] || { text: role, cls: "rb-other" };
    return `<span class="role-badge ${r.cls}">${esc(r.text)}</span>`;
  }

  // 时间格式化：2026-09-27T20:53:51 → 09-27 20:53（手机窄屏更易读）
  function fmtTime(t) {
    if (!t) return "—";
    const m = String(t).match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]}` : esc(t);
  }

  async function render() {
    const page = document.getElementById("page");
    page.innerHTML = `
      <h2>用户管理</h2>
      <div class="desc">系统所有已注册用户（在线用户靠前显示），管理员可对任意账号加时（刷新有效期 +30 天）或删除</div>
      <div class="card" id="users-card"><div class="loading">加载中…</div></div>`;

    const box = document.getElementById("users-card");
    try {
      const { users } = await API.get("/api/auth/all-users");
      if (!users.length) { box.innerHTML = `<div class="note">当前没有注册用户</div>`; return; }
      // 统计在线数，展示在标题行右侧
      const onlineCount = users.filter((u) => u.online).length;
      box.innerHTML = `<div class="um-head"><span>共 ${users.length} 个账号 · <b class="um-online">${onlineCount} 在线</b></span></div>`
        + `<table class="tbl"><thead><tr><th>用户名</th><th>角色</th><th>姓名</th><th>状态</th><th>登录时间</th><th>有效期至</th><th>操作</th></tr></thead><tbody>`
        + users.map((u) => {
            const rowCls = u.online ? ' class="online-row"' : '';
            const statusHtml = u.online
              ? `<span class="pill pill-online"><i class="dot-live"></i>在线</span>`
              : `<span class="pill muted">离线</span>`;
            const expireText = u.expire_at || "—";
            return `<tr${rowCls}><td><span class="um-name">${esc(u.username)}</span></td><td>${roleBadge(u.role)}</td><td class="um-fullname">${esc(u.name)}</td><td>${statusHtml}</td><td class="muted um-time">${fmtTime(u.login_at)}</td><td class="muted um-expire">${esc(expireText)}</td>
              <td class="op">
                <button class="btn op-ext btn-sm" data-ext="${esc(u.username)}">加时</button>
                <button class="btn danger op-del btn-sm" data-del="${esc(u.username)}">删除</button>
              </td></tr>`;
          }).join("")
        + `</tbody></table>`;
      // 加时：在线→追加 30 天；离线→重新登记为在线并给 30 天有效期
      box.querySelectorAll("button[data-ext]").forEach((b) => {
        b.onclick = async () => {
          try {
            const r = await API.post(`/api/auth/online-accounts/${b.dataset.ext}/extend`);
            toast(`已加时 30 天（${r.online ? "已上线" : ""}）`);
            render();
          } catch (e) { toast(e.message); }
        };
      });
      // 删除：彻底移除账号（在线则同时吊销令牌）
      box.querySelectorAll("button[data-del]").forEach((b) => {
        b.onclick = async () => {
          if (!confirm(`确定要删除账号「${b.dataset.del}」？此操作不可撤销。`)) return;
          try {
            await API.post(`/api/auth/users/${b.dataset.del}`);
            toast("已删除账号");
            render();
          } catch (e) { toast(e.message); }
        };
      });
    } catch (e) { box.innerHTML = `<div class="note">${esc(e.message)}</div>`; }
  }

  return { render };
})();
window.OnlineAccounts = OnlineAccounts;
