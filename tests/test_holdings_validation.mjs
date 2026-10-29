import test from 'node:test';
import assert from 'node:assert/strict';
import { holdingValidationIssue } from '../prototype/holdings.js';

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

test('a text holding can use a stated value without share count', () => {
  const position = { instrument_id: 'FUND:018044', name: '示例基金', asset_class: 'fund', quantity: null, manual_value: 5162.81 };
  assert.equal(holdingValidationIssue([position]), null);
  assert.equal(holdingValidationIssue([{ ...position, manual_value: null }]).field, 'manual_value');
});
