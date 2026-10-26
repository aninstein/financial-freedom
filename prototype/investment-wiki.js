import { request } from './api.js';
import { esc, icon, markdown, notify, confirmDialog } from './ui.js';

let currentDocument = null;
let directoryCollapsed = false;
let directoryBeforeEdit = false;

function setDirectoryCollapsed(collapsed) {
  directoryCollapsed = collapsed;
  const layout = document.querySelector('.wiki-layout');
  const browser = document.querySelector('.wiki-browser');
  const expand = document.querySelector('.wiki-expand-directory');
  layout?.classList.toggle('is-collapsed', collapsed);
  if (browser) browser.hidden = collapsed;
  if (expand) {
    expand.hidden = !collapsed;
    expand.setAttribute('aria-expanded', String(!collapsed));
  }
  document.querySelector('[data-action="wiki-collapse-directory"]')?.setAttribute('aria-expanded', String(!collapsed));
}

function todayInShanghai() {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date()).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function linkFor(directory, file = '') {
  const params = new URLSearchParams();
  if (directory) params.set('dir', directory);
  if (file) params.set('file', file);
  return `#/memory${params.size ? '?' + params.toString() : ''}`;
}

function locationMarkup(directory) {
  const crumbs = [{ name: 'llm-wiki', path: '' }];
  let prefix = '';
  for (const part of directory.split('/').filter(Boolean)) {
    prefix = prefix ? `${prefix}/${part}` : part;
    crumbs.push({ name: part, path: prefix });
  }
  return `<nav class="wiki-crumbs" aria-label="记忆目录位置">${crumbs.map((crumb, index) =>
    `<a href="${linkFor(crumb.path)}" ${index === crumbs.length - 1 ? 'aria-current="location"' : ''}>${esc(crumb.name)}</a>`).join('<span aria-hidden="true">/</span>')}</nav>`;
}

function itemMarkup(item, selected) {
  const isDirectory = item.type === 'directory';
  const href = isDirectory ? linkFor(item.path) : linkFor(item.path.split('/').slice(0, -1).join('/'), item.path);
  return `<a class="wiki-tree-item ${item.path === selected ? 'is-selected' : ''}" href="${href}" ${item.path === selected ? 'aria-current="page"' : ''}>${icon(isDirectory ? 'layers' : 'file')}<span>${esc(item.name)}</span>${isDirectory ? '<span aria-hidden="true">›</span>' : ''}</a>`;
}

function previewMarkup(document) {
  const source = document.content || '';
  if (source.startsWith('---\n')) {
    const end = source.indexOf('\n---\n', 4);
    if (end > 0) {
      const metadata = source.slice(4, end);
      const body = source.slice(end + 5);
      return `<details class="wiki-frontmatter"><summary>来源与状态元数据</summary><pre>${esc(metadata)}</pre></details><div class="wiki-markdown">${markdown(body)}</div>`;
    }
  }
  return `<div class="wiki-markdown">${markdown(source)}</div>`;
}

function editHint(document) {
  if (document.kind === 'entry') return '可修改正文；来源、状态和到期时间由系统维护。保存后记为你确认的投资记忆。';
  if (document.kind === 'daily') return '保存会生成新版日报；状态、输入哈希和来源索引由系统维护。当天暂存日报在次日归档时会再次生成新版。';
  if (document.kind === 'summary') return '可修改议题部分；会话和消息来源元数据由系统维护。';
  if (document.kind === 'index') return '编辑索引后将使用你的版本，目录列表仍会自动显示新文件。Agent 的投资记忆以日报和长短期条目为准。';
  if (document.kind === 'log') return '事件日志会继续追加系统事件；过期事件仍按保留期限清理。Agent 不把事件日志当成投资偏好。';
  return '目录说明保存在当前账户的私有 wiki 中；如需改变 Agent 使用的投资偏好，请编辑长短期记忆条目。';
}

function documentMarkup(document, error = '') {
  if (error) return `<section class="wiki-document panel"><div class="panel-body"><p class="alert error" role="alert">${esc(error)}</p></div></section>`;
  const currentReport = document.kind === 'daily-version' ? document.path.replace(/report-v\d+\.md$/, 'report.md') : '';
  return `<section class="wiki-document panel" aria-label="Markdown 文档"><header class="wiki-document-header"><div><span class="eyebrow">MARKDOWN DOCUMENT</span><h2>${esc(document.name)}</h2><p>${esc(document.path)}</p></div><div class="actions">${document.editable ? '<button class="button small" data-action="wiki-edit">编辑 Markdown</button>' : `<span class="tag">历史版本 · 只读</span><a class="button small ghost" href="${linkFor(document.path.split('/').slice(0, -1).join('/'), currentReport)}">编辑当前版本</a>`}${document.kind === 'entry' ? '<button class="button small ghost" data-action="wiki-delete-entry">删除记忆</button>' : ''}</div></header><div class="wiki-preview">${previewMarkup(document)}</div><div class="wiki-editor" hidden><div class="wiki-editor-toolbar"><p class="field-help">${esc(editHint(document))}</p><div class="actions"><button class="button primary" data-action="wiki-save">保存 Markdown</button><button class="button ghost" data-action="wiki-cancel">取消</button></div></div><p id="wiki-editor-error" class="field-help" role="alert"></p><div class="wiki-edit-workspace"><div class="wiki-edit-pane"><label class="field-label" for="wiki-source">编辑 Markdown</label><textarea id="wiki-source" class="field wiki-source" spellcheck="false" maxlength="30000" aria-describedby="wiki-editor-error"></textarea></div></div></div></section>`;
}

export async function renderWikiPage(route, signal, { setPage, page, heading }) {
  const directory = route.params.get('dir') || '';
  const selected = route.params.get('file') || (directory ? `${directory}/index.md` : 'index.md');
  const [listingResult, settingsResult, documentResult] = await Promise.all([
    request(`/ai/memory/wiki/tree?path=${encodeURIComponent(directory)}`, { signal }).catch((error) => ({ error: error.message })),
    request('/ai/memory/settings', { signal }).catch((error) => ({ error: error.message })),
    request(`/ai/memory/wiki/file?path=${encodeURIComponent(selected)}`, { signal }).catch((error) => ({ error: error.message })),
  ]);
  if (signal?.aborted) return;
  const listing = listingResult.items || [];
  const settings = settingsResult.error ? null : settingsResult;
  currentDocument = documentResult.error ? null : documentResult;
  const rootLinks = [['全部目录', ''], ['每日日报', 'daily'], ['短期记忆', 'short-term'], ['长期记忆', 'long-term'], ['会话摘要', 'sessions']];
  const quickLinks = rootLinks.map(([label, path]) => `<a href="${linkFor(path)}" ${directory === path ? 'aria-current="location"' : ''}>${esc(label)}</a>`).join('');
  const files = listing.map((item) => itemMarkup(item, selected)).join('') || '<p class="field-help">这里暂时没有 Markdown 文档。</p>';
  const day = todayInShanghai();
  const archive = settings?.latest_archive;
  const archiveLabel = archive ? `${archive.local_date} · ${archive.status === 'empty' ? '无对话' : archive.status === 'failed' ? '归档失败' : '已处理'}` : '尚无日报';
  setPage(page(heading('投资记忆', `当前账户的私有记忆空间 · 最近归档：${archiveLabel}`, '<a class="button small" href="#/chat">返回对话</a><button class="button small" data-action="wiki-archive">生成日报</button><button class="button small ghost" data-action="wiki-refresh">刷新</button>') +
    `<p class="wiki-intro">按目录查看投资日报、长短期记忆和会话摘要。文档以 Markdown 展示和编辑；历史日报保留原样，编辑当前 report.md 会生成新版本。${settings?.wiki_path ? `空间位置：<code>${esc(settings.wiki_path)}</code>` : ''}</p>` +
    `<div class="wiki-layout ${directoryCollapsed ? 'is-collapsed' : ''}"><aside id="wiki-browser" class="wiki-browser panel" aria-label="记忆文件目录" ${directoryCollapsed ? 'hidden' : ''}><div class="wiki-browser-title"><strong>目录</strong><span>${listing.length} 项</span><button class="button small ghost" type="button" data-action="wiki-collapse-directory" aria-controls="wiki-browser" aria-expanded="true" aria-label="收起目录">收起目录</button></div><label class="field-label wiki-archive-date" for="wiki-archive-date">归档日期<input class="field" id="wiki-archive-date" type="date" min="${esc(settings?.session_cutoff_day || day)}" max="${day}" value="${day}"></label><nav class="wiki-quick-links" aria-label="记忆分区">${quickLinks}</nav>${locationMarkup(directory)}<div class="wiki-tree">${listingResult.error ? `<p class="alert error" role="alert">${esc(listingResult.error)}</p>` : files}</div></aside><div class="wiki-document-shell"><button class="button small ghost wiki-expand-directory" type="button" data-action="wiki-expand-directory" aria-controls="wiki-browser" aria-expanded="false" ${directoryCollapsed ? '' : 'hidden'}>显示目录</button>${documentMarkup(currentDocument, documentResult.error)}</div></div>`));
}

export async function handleWikiAction(button, rerender) {
  const action = button.dataset.action;
  if (!action?.startsWith('wiki-')) return false;
  if (action === 'wiki-collapse-directory' || action === 'wiki-expand-directory') {
    setDirectoryCollapsed(action === 'wiki-collapse-directory');
  } else if (action === 'wiki-edit') {
    if (!currentDocument?.editable) return true;
    const editor = document.querySelector('.wiki-editor');
    const preview = document.querySelector('.wiki-preview');
    if (!editor || !preview) return true;
    directoryBeforeEdit = directoryCollapsed;
    setDirectoryCollapsed(true);
    document.querySelector('.wiki-layout')?.classList.add('is-editing');
    const source = document.getElementById('wiki-source');
    source.value = currentDocument.content;
    editor.hidden = false;
    preview.hidden = true;
    button.hidden = true;
    source.focus();
  } else if (action === 'wiki-cancel') {
    document.querySelector('.wiki-editor').hidden = true;
    document.querySelector('.wiki-preview').hidden = false;
    document.querySelector('[data-action="wiki-edit"]')?.removeAttribute('hidden');
    document.querySelector('.wiki-layout')?.classList.remove('is-editing');
    setDirectoryCollapsed(directoryBeforeEdit);
  } else if (action === 'wiki-save') {
    const source = document.getElementById('wiki-source');
    const error = document.getElementById('wiki-editor-error');
    if (!source.value.trim()) {
      error.textContent = 'Markdown 文档不能为空。';
      source.focus();
      return true;
    }
    button.disabled = true;
    error.textContent = '';
    try {
      await request('/ai/memory/wiki/file', { method: 'PUT', body: {
        path: currentDocument.path, content: source.value, expected_sha256: currentDocument.sha256,
      } });
      notify('Markdown 已保存');
      directoryCollapsed = directoryBeforeEdit;
      await rerender();
    } catch (failure) {
      error.textContent = failure.message || '保存失败，请重试。';
    } finally {
      button.disabled = false;
    }
  } else if (action === 'wiki-archive') {
    const date = document.getElementById('wiki-archive-date')?.value;
    if (!date) {
      notify('请选择归档日期');
      return true;
    }
    button.disabled = true;
    try {
      await request('/ai/memory/archive', { method: 'POST', body: { date } });
      notify(`${date} 的日报已进入归档队列`);
      await rerender();
    } catch (failure) {
      notify(failure.message || '归档失败');
    } finally {
      button.disabled = false;
    }
  } else if (action === 'wiki-refresh') {
    await rerender();
  } else if (action === 'wiki-delete-entry') {
    if (currentDocument?.kind !== 'entry') return true;
    if (!await confirmDialog('删除投资记忆', '<p>这条记忆将从 wiki 和 Agent 召回中移除，并阻止相同来源再次生成。</p>', '删除记忆', true)) return true;
    try {
      await request(`/ai/memory/entries/${encodeURIComponent(currentDocument.name.slice(0, -3))}`, { method: 'DELETE' });
      notify('投资记忆已删除');
      location.hash = linkFor(currentDocument.path.split('/').slice(0, -1).join('/'));
    } catch (failure) {
      notify(failure.message || '删除失败');
    }
  }
  return true;
}
