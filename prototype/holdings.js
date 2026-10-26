import { request } from './api.js';
import { esc, money, number, percent, tone, time, notify, stockHref } from './ui.js';

let selectedCurrency = 'CNY';
let selectedAsset = 'all';
let currentPortfolio = null;
let screenshotDraft = null;

export function clearHoldingsDraft() {
  screenshotDraft = null;
  currentPortfolio = null;
}

const classes = { stock: '股票', fund: '基金', gold: '黄金' };
const assetFilters = { all: '全部持仓', stock: '股票', fund: '基金', gold: '黄金' };
const holdingsURL = (currency, asset) => `#/holdings?currency=${encodeURIComponent(currency)}&asset=${encodeURIComponent(asset)}`;

export function isHoldingsImportIntent(question) {
  const action = '(?:导(?:入|一下|进|到)|同步|录入|添加|加入|加进|加到|放(?:入|进|到)|更新|保存|登记)';
  return new RegExp(`${action}.{0,24}(?:持仓|仓位)|(?:持仓|仓位).{0,24}${action}`).test(question);
}

export function holdingValidationIssue(positions) {
  for (const [index, item] of positions.entries()) {
    const label = `第 ${index + 1} 条${item.name ? `“${item.name}”` : '持仓'}`;
    if (!item.instrument_id) {
      const goldFund = item.asset_class === 'gold' && /ETF|联接|基金/i.test(item.name);
      return { index, field: 'instrument_id', message: `${label}缺少标的代码。${goldFund ? '黄金 ETF 或联接基金请填写 FUND: 后接实际基金代码。' : '请填写真实标的代码。'}` };
    }
    if (!item.name) return { index, field: 'name', message: `第 ${index + 1} 条持仓缺少名称。` };
    if (!Number.isFinite(item.quantity) || item.quantity <= 0)
      return { index, field: 'quantity', message: `${label}的数量必须大于零。` };
    if (item.reported_return_pct != null && (!Number.isFinite(item.reported_return_pct) || item.reported_return_pct < -100 || item.reported_return_pct > 100_000))
      return { index, field: 'reported_return_pct', message: `${label}的截图收益率无效；负收益率可以填写，允许范围为 -100% 至 100000%。` };
  }
  return null;
}

function showScreenshotDraft() {
  const target = document.getElementById('holdings-import-preview');
  if (!target || !screenshotDraft || screenshotDraft.currency !== selectedCurrency) return;
  const draft = screenshotDraft;
  const rows = draft.positions.map(item => `<li><strong>${esc(item.name)} · ${item.instrument_id ? esc(item.instrument_id) : '代码待补'}</strong><span>数量 ${number(item.quantity, 4)} · 投入 ${money(item.cost_basis, selectedCurrency)} · 截图市值 ${money(item.manual_value, selectedCurrency)}</span><span class="${tone(item.reported_return_pct)}">截图收益率 ${percent(item.reported_return_pct)}</span></li>`).join('');
  target.innerHTML = `<div class="holding-import-result"><p>识别于 ${time(draft.extracted_at)} · ${draft.positions.length} 条持仓。账户本金 ${money(draft.principal, selectedCurrency)}，现金 ${money(draft.cash, selectedCurrency)}。</p>${rows ? `<ul>${rows}</ul>` : ''}${draft.warnings?.length ? `<p class="field-help">需要手动检查：${draft.warnings.map(esc).join('；')}</p>` : ''}<p class="field-help">截图可能只覆盖部分持仓；填入表单时会保留原有未出现的标的。请核对数量、成本和收益率，再点击保存持仓。</p><button class="button primary" type="button" data-action="holdings-import-apply">填入编辑表单</button></div>`;
}

export async function previewChatHoldingsScreenshot(imageSource, currency = 'CNY') {
  const draft = await request('/holdings/import-preview', {
    method: 'POST', body: { currency, ...imageSource }, timeout: 60000,
  });
  screenshotDraft = draft;
  return { currency: draft.currency, count: draft.positions.length, warnings: draft.warnings?.length || 0 };
}

function rowMarkup(position = {}) {
  const type = position.asset_class || (selectedAsset === 'all' ? 'stock' : selectedAsset);
  return `<div class="holding-edit-row" data-holding-row><label>类别<select class="field" data-holding="asset_class"><option value="stock" ${type === 'stock' ? 'selected' : ''}>股票</option><option value="fund" ${type === 'fund' ? 'selected' : ''}>基金 / ETF</option><option value="gold" ${type === 'gold' ? 'selected' : ''}>黄金</option></select></label><label>标的代码<input class="field" data-holding="instrument_id" value="${esc(position.instrument_id || '')}" placeholder="CN:600519 / FUND:510300 / GOLD:Au99.99" required></label><label>名称<input class="field" data-holding="name" value="${esc(position.name || '')}" placeholder="标的名称" required></label><label>数量<input class="field" data-holding="quantity" type="number" min="0.000001" step="any" value="${position.quantity ?? ''}" required></label><label>投入本金<input class="field" data-holding="cost_basis" type="number" min="0" step="0.01" value="${position.cost_basis ?? ''}" placeholder="未知可留空"></label><label>截图市值<input class="field" data-holding="manual_value" type="number" min="0" step="0.01" value="${position.manual_value ?? ''}" placeholder="无行情时使用"></label><label>截图收益率 %<input class="field" data-holding="reported_return_pct" type="number" min="-100" step="0.01" value="${position.reported_return_pct ?? ''}" placeholder="仅作校准参考"></label><button class="button small ghost" type="button" data-action="holdings-remove-row" aria-label="移除这条持仓">移除</button></div>`;
}

function metric(label, value, currency, extra = '') {
  return `<div class="holding-metric"><span>${label}</span><strong class="${extra}">${money(value, currency)}</strong></div>`;
}
function rateMetric(label, value) {
  return `<div class="holding-metric"><span>${label}</span><strong class="${tone(value)}">${percent(value)}</strong></div>`;
}

function allocationMarkup(portfolio, currency) {
  const values = portfolio?.allocation || { stock: 0, fund: 0, gold: 0 };
  const known = Object.values(values).reduce((sum, value) => sum + value, 0);
  return `<section class="panel holding-allocation"><div class="panel-header"><h2>资产分布 · 全部类别</h2><span class="tag">${esc(currency)}</span></div><div class="panel-body">${known > 0 ? `<div class="holding-allocation-bar" aria-label="已估值持仓的资产分布">${Object.entries(values).map(([type, value]) => value ? `<span class="is-${type}" style="width:${value / known * 100}%" title="${classes[type]} ${number(value / known * 100, 1)}%"></span>` : '').join('')}</div>` : '<p class="field-help">录入持仓并取得估值后显示分布。</p>'}<div class="holding-allocation-list">${Object.entries(values).map(([type, value]) => `<div><span><i class="is-${type}"></i>${classes[type]}</span><strong>${money(value, currency)}</strong><small>${known ? number(value / known * 100, 1) : '0'}%</small></div>`).join('')}</div>${portfolio && !portfolio.valuation_complete ? '<p class="field-help">部分持仓缺少报价和手工市值，分布仅按已估值项目计算。</p>' : ''}</div></section>`;
}

function positionsMarkup(portfolio, currency, asset) {
  const positions = (portfolio?.positions || []).filter((item) => asset === 'all' || item.asset_class === asset);
  const label = assetFilters[asset];
  if (!positions.length) {
    const detail = asset === 'gold' ? '可登记实物黄金、黄金 ETF 或黄金 ETF 联接基金。' : asset === 'fund' ? '可登记普通基金和 ETF。' : asset === 'stock' ? '可登记 A 股、港股和美股。' : '可按股票、基金、黄金分别登记，选择上方类别查看。';
    return `<section class="panel holding-positions"><div class="panel-header"><h2>${label}</h2><span class="tag">0 项</span></div><div class="panel-body holding-empty"><p class="field-help">当前 ${esc(currency)} 账户还没有${asset === 'all' ? '真实' : label}持仓。${detail}</p><button class="button small primary" type="button" data-action="holdings-edit" data-add-asset="${asset}">添加${asset === 'all' ? '持仓' : label + '持仓'}</button></div></section>`;
  }
  const rows = positions.map((item) => `<tr><td><span class="holding-type is-${esc(item.asset_class)}">${classes[item.asset_class]}</span><a class="stock-link" href="${stockHref(item.instrument_id)}">${esc(item.name)}</a><small>${esc(item.instrument_id)}</small></td><td>${number(item.quantity, 4)}<small>${item.instrument_id.startsWith('FUND:') ? '份' : item.asset_class === 'gold' ? '克' : '股'}</small></td><td>${item.valuation_source === 'quote' ? `${money(item.last, currency)}<small class="${tone(item.change_percent)}">${percent(item.change_percent)}</small>` : '—<small>暂无匹配行情</small>'}</td><td>${money(item.current_value, currency)}<small>${item.valuation_source === 'quote' ? `${esc(item.provider || '缓存行情')} · ${time(item.quote_time)}` : item.valuation_source === 'manual' ? `截图/手工估值 · ${time(item.updated_at)}` : '等待报价或手工市值'}</small></td><td>${money(item.cost_basis, currency)}</td><td><span class="${tone(item.unrealized_pnl)}">${money(item.unrealized_pnl, currency)}</span><small class="${tone(item.unrealized_return_pct)}">${item.unrealized_return_pct == null ? '参考收益率 —' : `参考收益率 ${percent(item.unrealized_return_pct)}`}</small>${item.reported_return_pct == null ? '' : `<small class="${tone(item.reported_return_pct)}">截图记录 ${percent(item.reported_return_pct)}</small>`}</td></tr>`).join('');
  return `<section class="panel holding-positions"><div class="panel-header"><h2>${label}</h2><span class="tag">${positions.length} 项</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>标的</th><th>数量</th><th>当前价 / 涨跌</th><th>参考市值</th><th>投入本金</th><th>持仓盈亏 / 收益率</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
}

export async function renderHoldings(route, signal, { setPage, page, heading }) {
  const result = await request('/holdings', { signal });
  if (signal?.aborted) return;
  const available = result.currencies || ['CNY', 'HKD', 'USD'];
  selectedCurrency = available.includes(route.params.get('currency')) ? route.params.get('currency') : 'CNY';
  selectedAsset = Object.hasOwn(assetFilters, route.params.get('asset')) ? route.params.get('asset') : 'all';
  if (screenshotDraft?.currency !== selectedCurrency) screenshotDraft = null;
  currentPortfolio = result.portfolios.find((item) => item.currency === selectedCurrency) || null;
  const portfolio = currentPortfolio;
  const hasSnapshot = Boolean(portfolio);
  const tabs = available.map((currency) => `<a href="${holdingsURL(currency, selectedAsset)}" ${currency === selectedCurrency ? 'aria-current="page"' : ''}>${currency}</a>`).join('');
  const counts = Object.fromEntries(Object.keys(classes).map((asset) => [asset, (portfolio?.positions || []).filter((item) => item.asset_class === asset).length]));
  const assetTabs = Object.entries(assetFilters).map(([asset, label]) => `<a href="${holdingsURL(selectedCurrency, asset)}" ${asset === selectedAsset ? 'aria-current="page"' : ''}>${label}<span>${asset === 'all' ? portfolio?.positions?.length || 0 : counts[asset]}</span></a>`).join('');
  setPage(page(heading('我的持仓', '真实持仓按账户币种分别统计；可用行情持续更新参考市值与收益率，截图可用于校准。', '<button class="button primary" data-action="holdings-edit">录入或更新持仓</button><button class="button" data-action="holdings-import">截图同步</button><button class="button" data-action="holdings-refresh">刷新</button>') +
    `<div class="holding-navigation"><div><span>账户币种</span><nav class="holding-currency-tabs" aria-label="持仓币种">${tabs}</nav></div><div><span>持仓类别</span><nav class="holding-asset-tabs" aria-label="持仓类别">${assetTabs}</nav></div></div>` +
    `<section class="holding-summary"><div class="holding-summary-head"><div><span class="eyebrow">${esc(selectedCurrency)} PORTFOLIO</span><h2>${hasSnapshot ? '持仓概览' : '开始记录持仓'}</h2><p>${hasSnapshot ? `登记于 ${time(portfolio.updated_at)} · 行情为缓存参考价` : '还没有登记该币种的真实持仓。模拟账户不会计入这里。'}</p></div><span class="tag">${esc(selectedCurrency)}</span></div><div class="holding-metrics">${metric('账户总资产', portfolio?.total_assets, selectedCurrency)}${metric('账户本金', portfolio?.principal, selectedCurrency)}${metric('账户盈亏', portfolio?.total_pnl, selectedCurrency, tone(portfolio?.total_pnl))}${metric('现金余额', portfolio?.cash, selectedCurrency)}${rateMetric('账户收益率', portfolio?.total_return_pct)}</div><p class="field-help">总资产＝现金＋持仓参考市值；账户收益率＝（总资产－账户本金）÷账户本金。缺少现金、本金或任一持仓估值时显示“—”。不同币种不做隐式换算。</p></section>` +
    `<div class="holding-overview">${allocationMarkup(portfolio, selectedCurrency)}<section class="panel holding-cost"><div class="panel-header"><h2>持仓收益 · 全部类别</h2></div><div class="panel-body"><div>${metric('持仓投入', portfolio?.holdings_cost, selectedCurrency)}${metric('持仓市值', portfolio?.holdings_value, selectedCurrency)}${metric('浮动盈亏', portfolio?.holdings_pnl, selectedCurrency, tone(portfolio?.holdings_pnl))}${rateMetric('持仓收益率', portfolio?.holdings_return_pct)}</div><p class="field-help">按已登记成本和最新可用报价计算，可能与券商结算口径有偏差；截图收益率单独保留用于校准。</p></div></section></div>` +
    positionsMarkup(portfolio, selectedCurrency, selectedAsset) +
    `<section class="panel holding-import" id="holding-import" ${route.params.get('import') === '1' ? '' : 'hidden'}><div class="panel-header"><div><h2>截图同步 ${esc(selectedCurrency)} 持仓</h2><p>此处直接上传的图片只用于本次识别；聊天粘贴的图片保存在对应会话中。识别草稿需核对后再写入账本。</p></div></div><div class="panel-body"><label class="field-label" for="holdings-screenshot">选择券商持仓截图（PNG/JPEG/GIF/WebP，最多 5 MB）</label><input class="field" id="holdings-screenshot" type="file" accept="image/png,image/jpeg,image/gif,image/webp"><div id="holdings-import-preview"></div><p id="holdings-import-error" class="form-error" role="alert"></p><div class="actions"><button class="button ghost" type="button" data-action="holdings-import-cancel">取消</button></div></div></section>` +
    `<section class="panel holding-editor" id="holding-editor" hidden><div class="panel-header"><div><h2>更新 ${esc(selectedCurrency)} 持仓</h2><p>保存会替换该币种当前持仓清单；其他币种不受影响。</p></div></div><form id="holdings-form" class="panel-body" novalidate><div class="holding-account-fields"><label>账户本金<input class="field" name="principal" type="number" min="0" step="0.01" value="${portfolio?.principal ?? ''}" placeholder="累计投入的账户本金"></label><label>现金余额<input class="field" name="cash" type="number" min="0" step="0.01" value="${portfolio?.cash ?? ''}" placeholder="当前未投资现金"></label></div><div class="holding-editor-heading"><h3>持仓列表</h3><button class="button small" type="button" data-action="holdings-add-row">添加标的</button></div><div id="holding-rows">${(portfolio?.positions.length ? portfolio.positions : [{}]).map(rowMarkup).join('')}</div><p class="field-help">标的代码格式：股票 CN:600519、基金 FUND:510300、实物黄金 GOLD:Au99.99。黄金 ETF 或联接基金请选“黄金”类别并填写 FUND: 基金代码，数量按份。截图收益率可以是负数；填入成本后才能计算参考收益率。</p><p id="holdings-error" class="form-error" role="alert"></p><div class="actions"><button class="button primary" type="submit">保存持仓</button><button class="button ghost" type="button" data-action="holdings-cancel">取消</button></div></form></section>`));
  if (route.params.get('import') === '1') showScreenshotDraft();
}

export async function handleHoldingsAction(button, rerender) {
  const action = button.dataset.action;
  if (!action?.startsWith('holdings-')) return false;
  if (action === 'holdings-edit') {
    const editor = document.getElementById('holding-editor');
    const asset = button.dataset.addAsset;
    if (asset && classes[asset]) {
      const rows = document.getElementById('holding-rows');
      if (currentPortfolio?.positions?.length) rows.insertAdjacentHTML('beforeend', rowMarkup({ asset_class: asset }));
      else rows.innerHTML = rowMarkup({ asset_class: asset });
    }
    editor.hidden = false;
    editor.scrollIntoView({ block: 'start', behavior: 'smooth' });
  } else if (action === 'holdings-import') {
    const panel = document.getElementById('holding-import');
    panel.hidden = false;
    panel.scrollIntoView({ block: 'start', behavior: 'smooth' });
    panel.querySelector('input[type=file]')?.focus();
  } else if (action === 'holdings-import-cancel') {
    screenshotDraft = null;
    document.getElementById('holding-import').hidden = true;
    document.getElementById('holdings-import-preview').innerHTML = '';
    document.getElementById('holdings-import-error').textContent = '';
  } else if (action === 'holdings-import-apply') {
    if (!screenshotDraft || screenshotDraft.currency !== selectedCurrency) return true;
    const form = document.getElementById('holdings-form');
    const positions = new Map((currentPortfolio?.positions || []).map(item => [item.instrument_id, item]));
    for (const item of screenshotDraft.positions) {
      const known = Object.fromEntries(Object.entries(item).filter(([, value]) => value !== null && value !== undefined && value !== ''));
      if (item.instrument_id) positions.set(item.instrument_id, { ...positions.get(item.instrument_id), ...known });
      else positions.set(`review-${positions.size}`, known);
    }
    form.querySelector('[name="principal"]').value = screenshotDraft.principal ?? currentPortfolio?.principal ?? '';
    form.querySelector('[name="cash"]').value = screenshotDraft.cash ?? currentPortfolio?.cash ?? '';
    document.getElementById('holding-rows').innerHTML = [...positions.values()].map(rowMarkup).join('') || rowMarkup();
    screenshotDraft = null;
    document.getElementById('holding-import').hidden = true;
    document.getElementById('holding-editor').hidden = false;
    document.getElementById('holding-editor').scrollIntoView({ block: 'start', behavior: 'smooth' });
    notify('识别草稿已填入，请核对后保存持仓');
  } else if (action === 'holdings-cancel') {
    document.getElementById('holding-editor').hidden = true;
  } else if (action === 'holdings-add-row') {
    document.getElementById('holding-rows').insertAdjacentHTML('beforeend', rowMarkup());
  } else if (action === 'holdings-remove-row') {
    button.closest('[data-holding-row]')?.remove();
  } else if (action === 'holdings-refresh') {
    await rerender();
  }
  return true;
}

export async function handleHoldingsScreenshot(file) {
  if (!file) return;
  const error = document.getElementById('holdings-import-error');
  const target = document.getElementById('holdings-import-preview');
  const input = document.getElementById('holdings-screenshot');
  screenshotDraft = null;
  error.textContent = '';
  target.innerHTML = '';
  if (!['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024 || file.size === 0) {
    error.textContent = '请选择不超过 5 MB 的 PNG、JPEG、GIF 或 WebP 截图。';
    input.value = '';
    return;
  }
  input.disabled = true;
  target.innerHTML = '<p class="field-help" role="status">正在识别截图中的持仓与收益率…</p>';
  try {
    const image_data_url = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error('无法读取所选截图。'));
      reader.readAsDataURL(file);
    });
    const draft = await request('/holdings/import-preview', { method: 'POST', body: { currency: selectedCurrency, image_data_url }, timeout: 60000 });
    screenshotDraft = draft;
    showScreenshotDraft();
  } catch (failure) {
    target.innerHTML = '';
    error.textContent = failure.message || '截图识别失败，请换图重试。';
  } finally {
    input.disabled = false;
    input.value = '';
  }
}

export async function handleHoldingsSubmit(form, rerender, showError) {
  if (form.id !== 'holdings-form') return false;
  const value = (selector) => form.querySelector(selector)?.value.trim() || '';
  const optionalNumber = (raw) => raw === '' ? null : Number(raw);
  const rows = [...form.querySelectorAll('[data-holding-row]')].filter((row) => ['instrument_id', 'name', 'quantity', 'cost_basis', 'manual_value', 'reported_return_pct'].some((field) => row.querySelector(`[data-holding="${field}"]`)?.value.trim()));
  const positions = rows.map((row) => Object.fromEntries([...row.querySelectorAll('[data-holding]')].map((input) => [input.dataset.holding, input.value.trim()]))).map((item) => ({ ...item, quantity: Number(item.quantity), cost_basis: optionalNumber(item.cost_basis), manual_value: optionalNumber(item.manual_value), reported_return_pct: optionalNumber(item.reported_return_pct) }));
  const error = document.getElementById('holdings-error');
  const issue = holdingValidationIssue(positions);
  if (issue) {
    showError('holdings-error', issue.message, rows[issue.index].querySelector(`[data-holding="${issue.field}"]`));
    return true;
  }
  if (!positions.length && !value('[name="principal"]') && !value('[name="cash"]')) {
    error.textContent = '请至少填写账户本金、现金或一条持仓。';
    return true;
  }
  if ([value('[name="principal"]'), value('[name="cash"]'), ...positions.flatMap((item) => [item.cost_basis, item.manual_value])].some((item) => item !== '' && item !== null && (!Number.isFinite(Number(item)) || Number(item) < 0))) {
    error.textContent = '本金、现金和市值不能为负数。';
    return true;
  }
  const button = form.querySelector('[type="submit"]');
  button.disabled = true;
  error.textContent = '';
  try {
    await request(`/holdings/${selectedCurrency}`, { method: 'PUT', body: {
      principal: optionalNumber(value('[name="principal"]')),
      cash: optionalNumber(value('[name="cash"]')),
      expected_updated_at: currentPortfolio?.updated_at || null,
      positions,
    } });
    notify('持仓已保存');
    await rerender();
  } catch (failure) {
    error.textContent = failure.message || '保存失败，请重试。';
  } finally {
    button.disabled = false;
  }
  return true;
}
