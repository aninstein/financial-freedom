import test from 'node:test';
import assert from 'node:assert/strict';
import { requestEvents } from '../prototype/api.js';

test('research events arrive before the final result across split chunks', async () => {
  const originalFetch = globalThis.fetch;
  const encoder = new TextEncoder();
  const pieces = ['data: {"type":"status","message":"正在查', '询"}\n\n',
    'data: {"type":"answer_delta","text":"第一段"}\n\n',
    'data: {"type":"done","result":{"answer":"第一段"}}\n\n'];
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) {
      for (const piece of pieces) controller.enqueue(encoder.encode(piece));
      controller.close();
    },
  }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
  try {
    const events = [];
    await requestEvents('/ai/research/stream', { body: { question: '测试' }, onEvent: (event) => events.push(event) });
    assert.deepEqual(events.map((event) => event.type), ['status', 'answer_delta', 'done']);
    assert.equal(events[0].message, '正在查询');
    assert.equal(events[2].result.answer, '第一段');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
