import test from 'node:test';
import assert from 'node:assert/strict';
import { holdingValidationIssue, isHoldingsImportIntent } from '../prototype/holdings.js';

test('a negative screenshot return is valid and a missing fund code is identified', () => {
  const positions = [
    { instrument_id: 'FUND:513100', name: '纳斯达克', asset_class: 'fund', quantity: 4500, reported_return_pct: 15.98 },
    { instrument_id: 'CN:002594', name: '比亚迪', asset_class: 'stock', quantity: 300, reported_return_pct: -16.13 },
    { instrument_id: '', name: '易方达黄金ETF联接C', asset_class: 'gold', quantity: 35686.3, reported_return_pct: -15.22 },
  ];
  const issue = holdingValidationIssue(positions);
  assert.equal(issue.index, 2);
  assert.equal(issue.field, 'instrument_id');
  assert.match(issue.message, /第 3 条.*缺少标的代码/);
  positions[2].instrument_id = 'FUND:002963';
  assert.equal(holdingValidationIssue(positions), null);
});

test('adding a screenshot holding routes to the import draft', () => {
  assert.equal(isHoldingsImportIntent('帮我把这个黄金持仓加入我的持仓'), true);
  assert.equal(isHoldingsImportIntent('把这张截图导入我的持仓'), true);
  assert.equal(isHoldingsImportIntent('分析我的黄金持仓'), false);
});
