/* Manhuaju Autopilot — tiny client-side auth shim.
 *
 * Storage key: localStorage.manhuaju_auth = JSON {token, username, expires_at}
 * Public API:
 *   getAuth()           -> {token, username, expires_at} | null
 *   getToken()          -> string | null  (auto-clears if expired)
 *   getUsername()       -> string | null
 *   setAuth(payload)    -> void           (also dispatches 'manhuaju-auth' event)
 *   clearAuth()         -> void
 *   authedFetch(u, init)-> Promise<Response>   injects bearer if present
 *   renderAuthPill(id)  -> void           writes login/logout markup into a node
 */
(function () {
  const STORAGE_KEY = 'manhuaju_auth';

  function getAuth() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const obj = JSON.parse(raw);
      if (!obj || !obj.token) return null;
      if (obj.expires_at && Date.now() / 1000 > Number(obj.expires_at)) {
        localStorage.removeItem(STORAGE_KEY);
        return null;
      }
      return obj;
    } catch (_e) {
      return null;
    }
  }

  function getToken() {
    const a = getAuth();
    return a ? a.token : null;
  }

  function getUsername() {
    const a = getAuth();
    return a ? a.username : null;
  }

  function setAuth(payload) {
    if (!payload || !payload.token) return;
    const obj = {
      token: payload.token,
      username: payload.username || (payload.user && payload.user.username) || '',
      expires_at: payload.expires_at || null,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(obj));
    try { window.dispatchEvent(new CustomEvent('manhuaju-auth', { detail: obj })); } catch (_e) {}
  }

  function clearAuth() {
    localStorage.removeItem(STORAGE_KEY);
    try { window.dispatchEvent(new CustomEvent('manhuaju-auth', { detail: null })); } catch (_e) {}
  }

  async function authedFetch(url, init) {
    const opts = Object.assign({}, init || {});
    const headers = new Headers((opts.headers) || {});
    const tok = getToken();
    if (tok && !headers.has('Authorization')) {
      headers.set('Authorization', 'Bearer ' + tok);
    }
    opts.headers = headers;
    const res = await fetch(url, opts);
    if (res.status === 401 && tok) {
      // Token rejected by server — drop it so the user re-logs in.
      clearAuth();
    }
    return res;
  }

  async function logoutServer() {
    const tok = getToken();
    if (!tok) return;
    try {
      await fetch('/v1/auth/logout', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + tok },
      });
    } catch (_e) {}
  }

  function renderAuthPill(elementId) {
    const el = (typeof elementId === 'string') ? document.getElementById(elementId) : elementId;
    if (!el) return;
    // Make sure the host span itself is laid out horizontally and never wraps
    // its inline text content character-by-character (which can happen when
    // the parent is a flex container that shrinks children below their
    // intrinsic min content width).
    el.style.display = 'inline-flex';
    el.style.alignItems = 'center';
    el.style.whiteSpace = 'nowrap';
    el.style.flex = '0 0 auto';
    function paint() {
      const a = getAuth();
      if (a && a.username) {
        el.innerHTML =
          '<span class="auth-user" style="font-size:13px;color:var(--accent2,#7fb3ff);white-space:nowrap">' +
            '👤 ' + escapeHtml(a.username) +
          '</span>' +
          '<a href="#" id="manhuaju-logout-btn" style="font-size:13px;color:var(--muted,#8a93a1);margin-left:10px;text-decoration:none;white-space:nowrap">退出</a>';
        const btn = el.querySelector('#manhuaju-logout-btn');
        if (btn) {
          btn.addEventListener('click', async function (e) {
            e.preventDefault();
            await logoutServer();
            clearAuth();
            paint();
          });
        }
      } else {
        el.innerHTML =
          '<a href="/login" style="font-size:13px;color:var(--accent2,#7fb3ff);text-decoration:none;white-space:nowrap;display:inline-block;padding:2px 6px">登录 / 注册</a>';
      }
    }
    paint();
    window.addEventListener('manhuaju-auth', paint);
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  window.ManhuajuAuth = {
    getAuth: getAuth,
    getToken: getToken,
    getUsername: getUsername,
    setAuth: setAuth,
    clearAuth: clearAuth,
    authedFetch: authedFetch,
    renderAuthPill: renderAuthPill,
    logoutServer: logoutServer,
  };
  window.authedFetch = authedFetch;
})();
