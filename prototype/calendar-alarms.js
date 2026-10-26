const ZONE = 'Asia/Shanghai';

export function shanghaiClock(instant = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone: ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(instant).map(({ type, value }) => [type, value]));
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}

function previousDay(day) {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

export function dueCalendarAlarms(store, instant = new Date()) {
  const now = shanghaiClock(instant);
  const acknowledged = store.alarmAcknowledged || {};
  const subscriptions = new Map((store.subscriptions || []).filter(item => item.enabled).map(item => [item.id, item]));
  const alarms = [];

  for (const subscription of subscriptions.values()) {
    if (subscription.category !== '持仓截图同步') continue;
    const at = subscription.remindAt || '22:00';
    const day = now.time >= at ? now.date : previousDay(now.date);
    const created = shanghaiClock(new Date(subscription.createdAt || instant));
    if (day < created.date || (day === created.date && created.time > at)) continue;
    const id = `daily:${subscription.id}:${day}`;
    if (acknowledged[id]) continue;
    alarms.push({ id, date: day, time: at, title: subscription.name || '持仓截图同步',
      detail: '请截图同步持仓数量、成本、账户资产和收益率。识别结果需核对后才会写入持仓账本。',
      screenshot: true });
  }

  for (const event of store.events || []) {
    const subscription = subscriptions.get(event.subscriptionId);
    if (!subscription || !event.date || !event.time) continue;
    if (event.date > now.date || (event.date === now.date && event.time > now.time)) continue;
    const id = `event:${event.id}`;
    if (acknowledged[id]) continue;
    alarms.push({ id, date: event.date, time: event.time, title: event.title || subscription.name,
      detail: event.detail || `来自订阅「${subscription.name}」的日历事件。`, screenshot: false });
  }

  return alarms.sort((a, b) => `${b.date} ${b.time}`.localeCompare(`${a.date} ${a.time}`));
}
