import test from 'node:test';
import assert from 'node:assert/strict';
import { dueCalendarAlarms } from '../prototype/calendar-alarms.js';

const screenshot = { id: 'shot', name: '持仓截图同步', category: '持仓截图同步',
  enabled: true, remindAt: '22:00', createdAt: '2026-10-26T10:00:00Z' };

test('daily screenshot alarm follows Beijing 22:00 and survives a later login', () => {
  const store = { subscriptions: [screenshot], events: [], alarmAcknowledged: {} };
  assert.equal(dueCalendarAlarms(store, new Date('2026-10-27T13:59:00Z'))[0]?.date, '2026-10-26');
  assert.equal(dueCalendarAlarms(store, new Date('2026-10-27T14:00:00Z'))[0]?.id, 'daily:shot:2026-10-27');
  assert.equal(dueCalendarAlarms(store, new Date('2026-10-27T20:00:00Z'))[0]?.id, 'daily:shot:2026-10-27');
  store.alarmAcknowledged['daily:shot:2026-10-27'] = '2026-10-27T14:10:00Z';
  assert.equal(dueCalendarAlarms(store, new Date('2026-10-27T20:00:00Z')).length, 0);
  assert.equal(dueCalendarAlarms(store, new Date('2026-10-28T14:00:00Z'))[0]?.id, 'daily:shot:2026-10-28');
});

test('new late subscription waits until the next 22:00', () => {
  const late = { ...screenshot, createdAt: '2026-10-27T15:00:00Z' };
  assert.equal(dueCalendarAlarms({ subscriptions: [late] }, new Date('2026-10-27T16:00:00Z')).length, 0);
  assert.equal(dueCalendarAlarms({ subscriptions: [late] }, new Date('2026-10-28T14:00:00Z'))[0]?.date, '2026-10-28');
});

test('dated events require an enabled subscription and remain until confirmed', () => {
  const event = { id: 'e1', subscriptionId: 'news', date: '2026-10-27', time: '18:30', title: '财报提醒' };
  const store = { subscriptions: [{ id: 'news', name: '财报', enabled: true }], events: [event] };
  assert.equal(dueCalendarAlarms(store, new Date('2026-10-27T10:29:00Z')).length, 0);
  assert.equal(dueCalendarAlarms(store, new Date('2026-10-27T10:30:00Z'))[0]?.id, 'event:e1');
  assert.equal(dueCalendarAlarms(store, new Date('2026-12-10T11:00:00Z'))[0]?.id, 'event:e1');
  store.subscriptions[0].enabled = false;
  assert.equal(dueCalendarAlarms(store, new Date('2026-10-27T11:00:00Z')).length, 0);
});
