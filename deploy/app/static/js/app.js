// 文件位置: backend/app/static/js/app.js
// 功能: 应用入口 —— 登录流程、按角色/权限渲染导航、哈希路由装配、SSE 连接管理。
const App = (() => {
  const NAV = [
    { key: "dashboard", label: "态势大盘", perm: "feed:view", mod: "Dashboard" },
    { key: "feed", label: "舆情监测", perm: "feed:view", mod: "Feed" },
    { key: "event", label: "研判工作台", perm: "event:view", mod: "EventPage" },
    { key: "disposal", label: "处置协同", perm: "event:view", mod: "Disposal" },
    { key: "report", label: "报告中心", perm: "event:view", mod: "ReportPage" },
    { key: "config", label: "监测配置", perm: "feed:view", mod: "Config" },
    { key: "industryboard", label: "行业风险全景", perm: "feed:view", mod: "IndustryBoard" },  // 行业风险全景看板：多维度风险聚合
    { key: "online", label: "用户管理", role: "admin", mod: "OnlineAccounts" },  // 仅管理员可见：查看所有注册用户（在线/离线）
  ];

  // 侧边栏菜单图标（内联 SVG，stroke=currentColor 自动跟随文字颜色）
  const ICONS = {
    dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 13v-3M12 13V8M16 13v-2M9 21h6"/></svg>',
    feed: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h16M4 18h10"/></svg>',
    event: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>',
    disposal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    report: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M9 13h6M9 17h4"/></svg>',
    config: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 21v-6M4 9V3M12 21v-9M12 6V3M20 21v-4M20 11V3M1 13h6M9 9h6M17 15h6"/></svg>',
    // 行业风险全景：网格/分层图标（行业多维语义）
    industryboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M14 17.5h7M17.5 14v7"/></svg>',
    // 在线账号：双人像图标（用户管理语义）
    online: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
  };

  function renderNav() {
    const nav = document.getElementById("nav");
    nav.innerHTML = "";
    NAV.forEach((n) => {
      // role 限定的菜单项（如「在线账号」仅管理员可见）——必须先于 perm 判断，
      // 因为这类菜单项没有 perm 字段，Store.has(undefined) 恒为 false 会把它拦掉
      if (n.role && Store.role() !== n.role) return;
      if (n.perm && !Store.has(n.perm)) return;
      const a = document.createElement("a");
      a.innerHTML = (ICONS[n.key] || "") + "<span>" + n.label + "</span>";
      a.dataset.key = n.key;
      a.onclick = () => go(n.key);
      nav.appendChild(a);
    });
  }

  async function go(key) {
    document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.key === key));
    const item = NAV.find((n) => n.key === key);
    if (item && window[item.mod] && window[item.mod].render) await window[item.mod].render();
    location.hash = key;
  }

  function showApp() {
    document.getElementById("login-mask").classList.add("hidden");
    document.getElementById("topbar").classList.remove("hidden");
    document.getElementById("page").classList.remove("hidden");
    const u = Store.get().user;
    // 名称与角色文案相同时（如 admin 的「系统管理员」）只保留金色角色徽章，避免重复
    const nameEl = document.getElementById("user-name");
    nameEl.textContent = u.name;
    nameEl.classList.toggle("hidden", u.name === roleName(u.role));
    document.getElementById("user-role").textContent = roleName(u.role);
    renderNav();
    const hash = location.hash.replace("#", "");
    // hash 直跳也要过 role/perm 两道校验，防止非管理员用地址栏进受限页
    const target = NAV.find((n) => n.key === hash
      && (!n.role || Store.role() === n.role)
      && (!n.perm || Store.has(n.perm)));
    go(target ? target.key : "dashboard");
  }

  function hideApp() {
    document.getElementById("login-mask").classList.remove("hidden");
    document.getElementById("topbar").classList.add("hidden");
    document.getElementById("page").classList.add("hidden");
    if (window.__alertES) { window.__alertES.close(); window.__alertES = null; }
  }

  async function doLogin(user, pass) {
    const err = document.getElementById("login-err");
    err.textContent = "";
    try {
      const r = await API.post("/api/auth/login", { username: user, password: pass });
      // 注意：登录接口返回的是 { access_token, token_type, user }，
      // 必须拆包成 Store 约定的 { token, user } 结构，否则 authHeader() 拿不到令牌，
      // 后续所有请求都会因缺少 Authorization 头而 401 被踢回登录页。
      Store.set({ token: r.access_token, user: r.user });
      // 记住账号密码：勾选则写入 localStorage，否则清除（明文仅适合本地演示环境）
      try {
        const rm = document.getElementById("login-remember");
        if (rm && rm.checked) localStorage.setItem("yuqing_remember", JSON.stringify({ u: user, p: pass }));
        else localStorage.removeItem("yuqing_remember");
      } catch (e) {}
      showApp();
    } catch (e) {
      err.textContent = e.message;
    }
  }

  // 登录 / 注册 视图切换
  function showLoginView() {
    document.getElementById("login-view").classList.remove("hidden");
    document.getElementById("register-view").classList.add("hidden");
  }
  function showRegisterView() {
    document.getElementById("register-view").classList.remove("hidden");
    document.getElementById("login-view").classList.add("hidden");
  }

  // 注册：前端先做基础校验，再调后端；成功后直接登录进入系统
  async function doRegister() {
    const err = document.getElementById("reg-err");
    err.textContent = "";
    const username = document.getElementById("reg-user").value.trim();
    const name = document.getElementById("reg-name").value.trim();
    const p1 = document.getElementById("reg-pass").value;
    const p2 = document.getElementById("reg-pass2").value;
    const role = document.getElementById("reg-role").value;
    if (!/^[A-Za-z0-9_]{3,20}$/.test(username)) { err.textContent = "用户名需为 3-20 位字母、数字或下划线"; return; }
    if (p1.length < 6) { err.textContent = "密码长度至少 6 位"; return; }
    if (p1 !== p2) { err.textContent = "两次输入的密码不一致"; return; }
    try {
      const r = await API.post("/api/auth/register", { username, password: p1, name, role });
      Store.set({ token: r.access_token, user: r.user });
      showApp();
    } catch (e) {
      err.textContent = e.message;
    }
  }

  function onLogout(force) {
    hideApp();
    if (force) document.getElementById("login-err").textContent = "登录已失效，请重新登录";
    if (Store.get()) Store.clear();
  }

  function roleName(r) {
    return { admin: "系统管理员", analyst: "舆情分析师", pr: "公关运营人员" }[r] || r;
  }

  // 通用确认弹窗：返回 Promise<boolean>（确定=true / 取消或点遮罩或 Esc=false）
  function askConfirm({ title, message, okText = "确定", cancelText = "取消" }) {
    return new Promise((resolve) => {
      const mask = document.getElementById("confirm-mask");
      const ok = document.getElementById("confirm-ok");
      const cancel = document.getElementById("confirm-cancel");
      document.getElementById("confirm-title").textContent = title;
      document.getElementById("confirm-msg").textContent = message;
      ok.textContent = okText;
      cancel.textContent = cancelText;
      mask.classList.remove("hidden");
      const done = (val) => {
        mask.classList.add("hidden");
        ok.onclick = null; cancel.onclick = null; mask.onclick = null;
        document.removeEventListener("keydown", onKey);
        resolve(val);
      };
      const onKey = (e) => { if (e.key === "Escape") done(false); else if (e.key === "Enter") done(true); };
      ok.onclick = () => done(true);
      cancel.onclick = () => done(false);
      mask.onclick = (e) => { if (e.target === mask) done(false); };
      document.addEventListener("keydown", onKey);
    });
  }

  function bindLogin() {
    document.getElementById("login-btn").onclick = () => {
      const u = document.getElementById("login-user").value.trim();
      const p = document.getElementById("login-pass").value;
      if (!u || !p) { document.getElementById("login-err").textContent = "请输入用户名和密码"; return; }
      doLogin(u, p);
    };
    document.getElementById("login-pass").addEventListener("keydown", (e) => { if (e.key === "Enter") document.getElementById("login-btn").click(); });
    // 退出登录：先弹确认框，确认后再清会话并回到登录页
    document.getElementById("logout-btn").onclick = async () => {
      const ok = await askConfirm({ title: "退出登录", message: "确定要退出当前账号吗？退出后需重新登录。", okText: "退出登录", cancelText: "再想想" });
      if (!ok) return;
      API.post("/api/auth/logout").catch(() => {}); // 后台移除在线登记（best-effort）
      Store.clear();
      onLogout(false);
    };
    // 注册相关绑定
    document.getElementById("to-register").onclick = () => { document.getElementById("reg-err").textContent = ""; showRegisterView(); };
    document.getElementById("to-login").onclick = () => { document.getElementById("login-err").textContent = ""; showLoginView(); };
    document.getElementById("reg-btn").onclick = doRegister;
    ["reg-user", "reg-name", "reg-pass", "reg-pass2"].forEach((id) => {
      document.getElementById(id).addEventListener("keydown", (e) => { if (e.key === "Enter") document.getElementById("reg-btn").click(); });
    });
  }

  async function init() {
    bindLogin();
    // 回填"记住的账号密码"
    try {
      const raw = localStorage.getItem("yuqing_remember");
      if (raw) {
        const o = JSON.parse(raw);
        document.getElementById("login-user").value = o.u || "";
        document.getElementById("login-pass").value = o.p || "";
        const rm = document.getElementById("login-remember");
        if (rm) rm.checked = true;
      }
    } catch (e) {}
    // 若已有会话（同标签页刷新），尝试用 me 校验
    const saved = Store.get();
    if (saved) {
      try {
        const me = await API.get("/api/auth/me");
        Store.set({ token: saved.token, user: me });
        showApp();
        return;
      } catch (e) { Store.clear(); }
    }
    hideApp();
  }

  window.App = { onLogout, go };
  init();
})();
