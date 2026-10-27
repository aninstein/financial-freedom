const status = document.getElementById('state');
const [ticket, requestedRoute] = location.hash.slice(1).split('.');
history.replaceState(null, '', location.pathname);
const routes = new Set(['chat', 'holdings', 'watchlist', 'markets', 'calendar', 'indices',
  'news', 'liquidity', 'flows', 'sectors', 'gold', 'research', 'documents', 'memory',
  'settings', 'security']);
const route = routes.has(requestedRoute) ? requestedRoute : 'chat';

if (!/^[A-Za-z0-9_-]{32,128}$/.test(ticket)) {
  status.textContent = '登录凭证无效，请返回小程序重试。';
} else {
  fetch('/api/v1/auth/wechat/consume', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticket }),
  }).then(async (response) => {
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail?.message || '登录失败，请返回小程序重试。');
    location.replace(`/#/${route}`);
  }).catch((error) => {
    status.textContent = error.message || '登录失败，请返回小程序重试。';
  });
}
