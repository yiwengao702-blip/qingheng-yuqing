// 文件位置: backend/app/static/js/api.js
// 功能: 类型化 fetch 封装。Base URL 走相对路径（同源），自动附加 Bearer 令牌，
//       将后端错误映射为可读文案；5xx 自动重试最多 3 次，4xx 不重试。
const API = (() => {
  const RETRY = 3;

  function authHeader() {
    const a = window.__auth || {};
    // 兼容两种存储形态：规范为 { token }，历史上曾直接存过登录响应 { access_token }
    const t = a.token || a.access_token;
    // 同时下发自定义头 X-Auth-Token：部分托管平台的反向代理会覆盖标准 Authorization 头，
    // 自定义头不会被改写，后端优先读取它，保证线上鉴权可用。
    return t ? { Authorization: "Bearer " + t, "X-Auth-Token": t } : {};
  }

  function errText(data) {
    if (data && data.error && data.error.message) return data.error.message;
    if (typeof data === "string") return data;
    return "请求失败，请稍后重试";
  }

  async function request(method, path, body, _attempt = 1) {
    const opts = {
      method,
      headers: { "Content-Type": "application/json", ...authHeader() },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    let resp;
    try {
      resp = await fetch(path, opts);
    } catch (e) {
      if (_attempt < RETRY) {
        await new Promise((r) => setTimeout(r, 600 * _attempt));
        return request(method, path, body, _attempt + 1);
      }
      throw new Error("网络异常，请检查服务是否启动");
    }
    const text = await resp.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
    if (resp.status === 401) {
      // 令牌失效，退回登录
      if (window.Store) window.Store.logout(true);
      throw new Error("登录已失效，请重新登录");
    }
    if (!resp.ok) {
      const msg = errText(data);
      if (resp.status >= 500 && _attempt < RETRY) {
        await new Promise((r) => setTimeout(r, 600 * _attempt));
        return request(method, path, body, _attempt + 1);
      }
      throw new Error(msg);
    }
    return data;
  }

  return {
    get: (p) => request("GET", p),
    post: (p, b) => request("POST", p, b),
    put: (p, b) => request("PUT", p, b),
    del: (p) => request("DELETE", p),
    raw: (p) => fetch(p, { headers: authHeader() }), // 用于文件导出（浏览器直接下载）
  };
})();

// 轻量提示
function toast(msg) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 2600);
}
