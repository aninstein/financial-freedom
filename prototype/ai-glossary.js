import { request } from './api.js';
import { esc, notify, confirmDialog, showDialog } from './ui.js';

const analyzePrompt = (term) => `请围绕「${term.title}」进行投研分析：先解释概念，再结合最新可查新闻、相关行业和市场数据说明它当前的背景、影响路径、支持与反方证据、风险及数据缺口。区分事实与推断，引用来源和时间，不把词条本身当成买卖结论。`;
const card = (term) => `<article class="glossary-card"><button class="glossary-card-main" type="button" data-action="glossary-analyze" data-title="${esc(term.title)}" title="开始分析${esc(term.title)}"><strong>${esc(term.title)}</strong><span>${esc(term.definition)}</span></button></article>`;

export async function loadGlossary(signal) {
  return request('/ai/glossary', { signal });
}

export function chatTermsMarkup(state) {
  const terms = state.glossary?.terms?.filter((term) => term.is_favorite) || [];
  const shown = state.glossaryExpanded ? terms : terms.slice(0, 4);
  const recs = (state.glossary?.recommendations || []).slice(0, 4);
  return `<section class="chat-glossary" aria-label="投研词条"><div class="chat-glossary-section"><header><div><strong>我的收藏</strong><small>${terms.length} 个词条</small></div><a href="#/glossary">管理词条</a></header>${terms.length ? `<div class="glossary-grid">${shown.map((term) => card(term)).join('')}</div>${terms.length > 4 ? `<button class="glossary-expand" type="button" data-action="glossary-expand">${state.glossaryExpanded ? '收起' : `展开全部 ${terms.length} 个收藏词条`}</button>` : ''}` : '<p class="glossary-empty">还没有收藏词条。打开词条库，收藏常用主题。</p>'}</div><div class="chat-glossary-section"><header><div><strong>新闻推荐</strong><small>每小时更新 · 4 条</small></div><a href="#/glossary">查看词条库</a></header>${recs.length ? `<div class="glossary-grid">${recs.map((term) => card(term)).join('')}</div>` : '<p class="glossary-empty">暂无推荐词条；新闻采集成功后会自动生成。</p>'}</div></section>`;
}

function libraryCard(term, kind) {
  return `<article class="glossary-library-card"><button type="button" class="glossary-card-main" data-action="glossary-analyze" data-title="${esc(term.title)}"><strong>${esc(term.title)}</strong><span>${esc(term.definition)}</span></button>${kind === 'recommendation' ? '' : `<footer><button class="button small ghost" data-action="glossary-edit-term" data-id="${esc(term.term_id)}">编辑</button><button class="button small ghost" data-action="glossary-favorite" data-id="${esc(term.term_id)}" data-favorite="${term.is_favorite}">${term.is_favorite ? '取消收藏' : '收藏'}</button><button class="button small ghost" data-action="glossary-delete" data-id="${esc(term.term_id)}">删除</button></footer>`}</article>`;
}

export async function renderGlossaryPage(_route, signal, { setPage, page, heading }) {
  const data = await loadGlossary(signal);
  if (signal?.aborted) return;
  const favorites = data.terms.filter((item) => item.is_favorite);
  setPage(page(heading('AI 词条', '收藏常用研究主题；推荐词条每小时根据已采集新闻更新。', '<button class="button primary" data-action="glossary-create">新建词条</button><a class="button small ghost" href="#/chat">返回对话</a>') +
    `<div class="glossary-page-sections"><section class="glossary-library-section"><header><div><h2>我的词条</h2><p>编辑和收藏会保存在当前账户。点击词条内容直接开始分析。</p></div><span class="tag">${data.terms.length} 条 · ${favorites.length} 条收藏</span></header><div class="glossary-library-grid">${data.terms.map((term) => libraryCard(term, 'term')).join('') || '<p class="glossary-empty">还没有词条。可从推荐中收录，或新建自己的研究主题。</p>'}</div></section><section class="glossary-library-section"><header><div><h2>新闻推荐</h2><p>仅作为研究入口；来源新闻与发布时间可展开查看。</p></div><span class="tag">${data.recommendations.length} 条</span></header><div class="glossary-library-grid">${data.recommendations.map((term) => libraryCard(term, 'recommendation')).join('') || '<p class="glossary-empty">当前没有推荐词条。系统会在每小时刷新新闻后生成。</p>'}</div></section></div>`));
  return data;
}

function editDialog(title, definition, isFavorite = true, saveLabel = '保存到我的词条') {
  showDialog('编辑词条', `<form id="glossary-edit-form" novalidate><label class="field-label" for="glossary-edit-title">词条名称<input class="field" id="glossary-edit-title" name="title" maxlength="80" value="${esc(title)}" required></label><label class="field-label" for="glossary-edit-definition">释义<textarea class="field glossary-definition-input" id="glossary-edit-definition" name="definition" maxlength="2000" required>${esc(definition)}</textarea></label><label class="glossary-favorite-control"><input name="is_favorite" type="checkbox" ${isFavorite ? 'checked' : ''}> 收藏到新会话首页</label><p class="field-help" id="glossary-edit-error" role="alert"></p><div class="actions"><button class="button primary" type="submit">${esc(saveLabel)}</button><button class="button ghost" type="button" data-action="close-dialog">取消</button></div></form>`);
}

export async function handleGlossaryAction(button, { state, refresh, sendChat }) {
  const action = button?.dataset.action;
  if (!action?.startsWith('glossary-')) return false;
  if (action === 'glossary-analyze') {
    if (state.route?.name !== 'chat') {
      await new Promise((resolve) => {
        let finished = false;
        const finish = () => {
          if (finished) return;
          finished = true;
          window.removeEventListener('hashchange', finish);
          resolve();
        };
        window.addEventListener('hashchange', finish, { once: true });
        location.hash = '/chat';
        setTimeout(finish, 500);
      });
    }
    await sendChat(analyzePrompt({ title: button.dataset.title }));
  } else if (action === 'glossary-expand') {
    state.glossaryExpanded = !state.glossaryExpanded;
    const content = document.querySelector('#messages-inner');
    if (content) content.querySelector('.chat-glossary')?.replaceWith(Object.assign(document.createElement('div'), { innerHTML: chatTermsMarkup(state) }).firstElementChild);
  } else if (action === 'glossary-create') {
    editDialog('', '', true, '创建词条');
    document.querySelector('#glossary-edit-form')?.setAttribute('data-mode', 'create');
  } else if (action === 'glossary-edit-recommendation') {
    const term = state.glossary?.recommendations?.find((item) => item.recommendation_id === button.dataset.id);
    if (!term) { notify('推荐词条已更新，请刷新页面', 'error'); return true; }
    editDialog(term.title, term.definition);
    document.querySelector('#glossary-edit-form')?.setAttribute('data-mode', 'recommendation');
    document.querySelector('#glossary-edit-form')?.setAttribute('data-id', term.recommendation_id);
  } else if (action === 'glossary-edit-term') {
    const term = state.glossary?.terms?.find((item) => item.term_id === button.dataset.id);
    if (!term) return true;
    editDialog(term.title, term.definition, term.is_favorite, '保存修改');
    document.querySelector('#glossary-edit-form')?.setAttribute('data-mode', 'edit');
    document.querySelector('#glossary-edit-form')?.setAttribute('data-id', term.term_id);
    document.querySelector('#glossary-edit-form')?.setAttribute('data-expected-updated-at', term.updated_at);
  } else if (action === 'glossary-favorite') {
    await request(`/ai/glossary/terms/${encodeURIComponent(button.dataset.id)}/favorite`, { method: 'PATCH', body: { is_favorite: button.dataset.favorite !== 'true' } });
    notify(button.dataset.favorite === 'true' ? '已取消收藏' : '已加入收藏');
    await refresh();
  } else if (action === 'glossary-delete') {
    if (!await confirmDialog('删除我的词条', '<p>删除后，这条词条将从词条库和新会话收藏中移除。</p>', '删除词条', true)) return true;
    await request(`/ai/glossary/terms/${encodeURIComponent(button.dataset.id)}`, { method: 'DELETE' });
    notify('词条已删除');
    await refresh();
  } else if (action === 'glossary-submit') {
    const form = document.querySelector('#glossary-edit-form');
    if (!form) return true;
    const title = form.elements.title.value.trim();
    const definition = form.elements.definition.value.trim();
    const error = document.querySelector('#glossary-edit-error');
    if (!title || definition.length < 3) { error.textContent = '请输入词条名称和至少 3 个字符的释义。'; return true; }
    const body = { title, definition, is_favorite: form.elements.is_favorite.checked };
    const mode = form.dataset.mode;
    try {
      if (mode === 'recommendation') await request(`/ai/glossary/recommendations/${encodeURIComponent(form.dataset.id)}/save`, { method: 'POST', body });
      else if (mode === 'edit') await request(`/ai/glossary/terms/${encodeURIComponent(form.dataset.id)}`, { method: 'PUT', body: { ...body, expected_updated_at: form.dataset.expectedUpdatedAt } });
      else await request('/ai/glossary/terms', { method: 'POST', body });
      document.querySelector('#app-dialog')?.close();
      notify(mode === 'recommendation' ? '已收录到我的词条' : mode === 'edit' ? '词条已保存' : '词条已创建');
      await refresh();
    } catch (error) { if (document.querySelector('#glossary-edit-error')) document.querySelector('#glossary-edit-error').textContent = error.message; }
  }
  return true;
}
