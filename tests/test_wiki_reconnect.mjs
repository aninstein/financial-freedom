import test from 'node:test';
import assert from 'node:assert/strict';
import { renderWikiPage } from '../prototype/investment-wiki.js';

test('daily wiki recovers when the API briefly disconnects', async () => {
  const originalFetch = globalThis.fetch;
  const attempts = new Map();
  globalThis.fetch = async (url) => {
    const count = (attempts.get(url) || 0) + 1;
    attempts.set(url, count);
    if (count === 1) throw new TypeError('Failed to fetch');
    const result = url.includes('/tree?')
      ? { items: [{ name: 'report.md', path: 'daily/2026-10-27/report.md', type: 'markdown' }] }
      : url.includes('/settings')
        ? { latest_archive: { local_date: '2026-10-27', status: 'published' } }
        : { name: 'index.md', path: 'daily/index.md', kind: 'index', editable: true, content: '# 每日日报' };
    return new Response(JSON.stringify(result), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  try {
    let html = '';
    await renderWikiPage({ params: new URLSearchParams('dir=daily') }, undefined, {
      setPage: (value) => { html = value; },
      page: (value) => value,
      heading: (title) => title,
    });
    assert.match(html, /report\.md/);
    assert.doesNotMatch(html, /Failed to fetch/);
    assert.deepEqual([...attempts.values()], [2, 2, 2]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
