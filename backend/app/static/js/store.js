// 文件位置: backend/app/static/js/store.js
// 功能: 前端鉴权状态（持久化到 localStorage，刷新/重开浏览器仍保持登录）+ 角色权限判断。
const Store = (() => {
  const KEY = "yuqing_auth";
  let auth = null; // { token, user:{username,name,role,permissions} }

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)); } catch (e) { return null; }
  }
  function save(a) {
    try { if (a) localStorage.setItem(KEY, JSON.stringify(a)); else localStorage.removeItem(KEY); } catch (e) {}
  }
  function set(authData) {
    auth = authData;
    window.__auth = auth;
    save(auth);
  }
  function get() {
    if (auth) return auth;
    auth = load(); // 刷新后从 localStorage 恢复
    return auth;
  }
  function clear() {
    auth = null;
    window.__auth = null;
    save(null);
  }
  function has(perm) {
    if (!auth) return false;
    if (perm == null) return true; // 未声明权限要求的菜单项默认放行（由 role 过滤兜底）
    return auth.user.permissions.includes(perm);
  }
  function role() { return auth ? auth.user.role : null; }
  function logout(force) {
    clear();
    if (window.App && window.App.onLogout) window.App.onLogout(force);
  }
  return { set, get, clear, has, role, logout };
})();
window.Store = Store;
