import { request } from './api.js';
import { esc, notify, confirmDialog } from './ui.js';

const statusText = (status) => status === 'connected' ? '已连接' : status === 'not_checked' ? '待检查' : '连接失败';

export function extensionsMarkup(data) {
  const skills = data.skills || [];
  const servers = data.mcp || [];
  return `<section class="extension-settings section-gap" id="extension-settings" aria-label="Agent 扩展配置">
    <div class="split">
      <section class="panel"><div class="panel-header"><h2>Skills</h2><span class="tag">${skills.length} 个已安装</span></div>
        <div class="panel-body">
          <p class="field-help">粘贴公开 GitHub 仓库链接，或上传包含 SKILL.md 的 ZIP。安装后，Agent 会按名称和描述发现 Skill，并在相关对话中读取说明。Skill 脚本不会自动执行。</p>
          <form id="skill-url-form" novalidate class="section-gap">
            <div class="form-row"><label class="field-label" for="skill-source">Skill 仓库链接</label><input class="field" id="skill-source" name="source" type="url" placeholder="https://github.com/owner/repository" autocomplete="off" /></div>
            <div class="form-row"><label class="field-label" for="skill-name">Skill 名称（仓库有多个时填写）</label><input class="field" id="skill-name" name="name" placeholder="stock-research-executor" autocomplete="off" /></div>
            <p class="form-error" id="skill-url-error" role="alert"></p><button class="button primary" type="submit">安装 Skill</button>
          </form>
          <form id="skill-zip-form" novalidate class="section-gap">
            <div class="form-row"><label class="field-label" for="skill-zip">或上传 Skill ZIP</label><input class="field" id="skill-zip" name="file" type="file" accept=".zip,application/zip" /></div>
            <p class="form-error" id="skill-zip-error" role="alert"></p><button class="button" type="submit">安装 ZIP</button>
          </form>
          <p class="field-help section-gap">安装目录：<code>${esc(data.skills_dir || '')}</code></p>
          <div id="skill-list" class="extension-list section-gap">${skills.length ? skills.map((item) => `<article class="extension-item"><div><strong>${esc(item.name)}</strong><span class="tag ready">已安装</span></div><p>${esc(item.description)}</p>${item.requested_tools?.length ? `<p class="field-help">声明所需工具：${esc(item.requested_tools.join(' · '))}。安装不会自动授予这些权限。</p>` : ''}<button class="button small" type="button" data-action="remove-skill" data-extension-action="remove-skill" data-name="${esc(item.name)}">移除</button></article>`).join('') : '<p class="field-help">还没有安装 Skill。安装后会显示在这里。</p>'}</div>
        </div></section>
      <section class="panel"><div class="panel-header"><h2>MCP 连接</h2><span class="tag">${servers.length} 个已配置</span></div>
        <div class="panel-body">
          <p class="field-help">粘贴标准 <code>mcpServers</code> JSON。服务端私有保存凭据，连接后显示工具清单。对话默认只开放服务标注为只读的工具。</p>
          <form id="mcp-config-form" novalidate class="section-gap">
            <div class="form-row"><label class="field-label" for="mcp-config">MCP 配置 JSON</label><textarea class="field resize-none extension-config" id="mcp-config" name="config" rows="8" spellcheck="false" placeholder='{"mcpServers":{"research":{"command":"npx","args":["-y","package-name"],"env":{"API_TOKEN":""}}}}'></textarea></div>
            <p class="field-help">提交前检查命令、包名和权限；配置不会发送给 AI 模型。</p><p class="form-error" id="mcp-config-error" role="alert"></p><button class="button primary" type="submit">保存并连接</button>
          </form>
          <p class="field-help section-gap">私有配置文件：<code>${esc(data.mcp_config_file || '')}</code></p>
          <div id="mcp-list" class="extension-list section-gap">${servers.length ? servers.map((item) => `<article class="extension-item"><div><strong>${esc(item.managed ? 'Finch 平台' : item.name)}</strong><span class="tag ${item.status === 'connected' ? 'ready' : 'amber'}">${item.managed ? '内置' : statusText(item.status)}</span></div><p>${esc(item.managed ? '账户绑定 · 页面同源数据与工作台操作' : item.command || item.url || '连接配置')} · ${item.tool_count} 个工具</p>${item.tools?.length ? `<p class="extension-tool-list">${item.tools.map(esc).join(' · ')}</p>` : '<p class="field-help">连接后才能发现工具；没有只读标注的工具不会进入对话。</p>'}<p class="field-help">${item.managed ? '可读取平台数据；仅按用户请求修改本人内容。' : item.allow_write_tools ? "已允许此连接的可写工具进入对话" : "仅允许服务标注为只读的工具进入对话"}</p>${item.managed ? '' : `<div class="actions"><button class="button small" type="button" data-action="toggle-mcp-write" data-extension-action="toggle-mcp-write" data-name="${esc(item.name)}" data-enabled="${item.allow_write_tools}">${item.allow_write_tools ? "关闭可写工具" : "启用可写工具"}</button><button class="button small" type="button" data-action="probe-mcp" data-extension-action="probe-mcp" data-name="${esc(item.name)}">重新连接</button><button class="button small" type="button" data-action="remove-mcp" data-extension-action="remove-mcp" data-name="${esc(item.name)}">移除</button></div>`}</article>`).join('') : '<p class="field-help">还没有配置 MCP。保存配置后会自动检查连接。</p>'}</div>
        </div></section>
    </div></section>`;
}

export function mountExtensions(refresh) {
  const root = document.querySelector('#extension-settings');
  if (!root) return;
  const submit = async (form, errorId, action) => {
    const button = form.querySelector('button[type="submit"]');
    if (button.disabled) return;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    const error = document.getElementById(errorId);
    error.textContent = '';
    try {
      await action();
      form.reset();
      notify('扩展配置已更新');
      await refresh();
    } catch (exc) {
      error.textContent = exc.message;
      form.querySelector('input, textarea')?.focus();
    } finally {
      button.disabled = false;
      button.removeAttribute('aria-busy');
    }
  };
  root.querySelector('#skill-url-form').onsubmit = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    submit(form, 'skill-url-error', async () => {
      const source = form.elements.source.value.trim();
      const name = form.elements.name.value.trim();
      if (!source) throw new Error('请输入 GitHub 仓库链接');
      await request('/agent/extensions/skills/url', { method: 'POST', body: { source, name: name || null }, timeout: 45000 });
    });
  };
  root.querySelector('#skill-zip-form').onsubmit = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    submit(form, 'skill-zip-error', async () => {
      const file = form.elements.file.files[0];
      if (!file || !file.name.toLowerCase().endsWith('.zip')) throw new Error('请选择 ZIP 文件');
      if (file.size > 10 * 1024 * 1024) throw new Error('ZIP 最大 10 MB');
      const data = new FormData();
      data.append('file', file);
      await request('/agent/extensions/skills/upload', { method: 'POST', body: data, timeout: 45000 });
    });
  };
  root.querySelector('#mcp-config-form').onsubmit = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    submit(form, 'mcp-config-error', async () => {
      let config;
      try { config = JSON.parse(form.elements.config.value); }
      catch { throw new Error('请输入有效的 JSON 配置'); }
      if (!config || typeof config !== 'object' || !config.mcpServers) throw new Error('配置需要 mcpServers 对象');
      await request('/agent/extensions/mcp', { method: 'POST', body: { config }, timeout: 45000 });
    });
  };
  root.onclick = async (event) => {
    const button = event.target.closest('[data-extension-action]');
    if (!button) return;
    event.stopPropagation();
    const { extensionAction: action, name } = button.dataset;
    if (action.startsWith('remove-') && !await confirmDialog('移除扩展？', `<p>将移除 <strong>${esc(name)}</strong> 的本地配置。正在进行的对话不会继续使用它。</p>`, '移除', true)) return;
    button.disabled = true;
    try {
      if (action === 'remove-skill') await request('/agent/extensions/skills/' + encodeURIComponent(name), { method: 'DELETE' });
      if (action === 'remove-mcp') await request('/agent/extensions/mcp/' + encodeURIComponent(name), { method: 'DELETE' });
      if (action === 'toggle-mcp-write') {
        const writeEnabled = button.dataset.enabled === 'true';
        if (!writeEnabled && !await confirmDialog('启用可写 MCP 工具？', `<p>Agent 将可以调用 <strong>${esc(name)}</strong> 提供的可写工具。请先检查其工具清单和外部权限。</p>`, '启用')) { button.disabled = false; return; }
        await request('/agent/extensions/mcp/' + encodeURIComponent(name) + '/tools', { method: 'PUT', body: { allow_write_tools: !writeEnabled } });
      }
      if (action === 'probe-mcp') await request('/agent/extensions/mcp/' + encodeURIComponent(name) + '/probe', { method: 'POST', timeout: 45000 });
      notify(action === 'probe-mcp' ? '连接状态已更新' : action === 'toggle-mcp-write' ? 'MCP 工具权限已更新' : '扩展已移除');
      await refresh();
    } catch (exc) {
      notify(exc.message);
      button.disabled = false;
    }
  };
}
