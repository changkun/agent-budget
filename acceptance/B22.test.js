import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FORM, form, manualClock, start } from './_helpers.js';

test('B22 activity log', async () => {
  const clock = manualClock('2024-06-01T00:00:00Z');
  const app = await start({ books: [{ title: 'Old', author: 'Seed' }], clock });
  try {
    assert.deepEqual((await app.request('GET', '/api/activity')).json.events, []);
    const a = await app.request('POST', '/api/books', { title: 'Alpha', author: 'One' });
    clock.set('2024-06-01T00:01:00Z');
    await app.request('PUT', `/api/books/${a.json.id}`, { rating: 3 });
    clock.set('2024-06-01T00:02:00Z');
    await app.request('POST', '/books', form({ title: 'Beta', author: 'Two' }), FORM);
    clock.set('2024-06-01T00:03:00Z');
    await app.request('DELETE', `/api/books/${a.json.id}`);
    const res = await app.request('GET', '/api/activity');
    assert.equal(res.status, 200);
    assert.deepEqual(res.json.events.map((e) => [e.type, e.title]), [
      ['deleted', 'Alpha'], ['created', 'Beta'], ['updated', 'Alpha'], ['created', 'Alpha'],
    ]);
    assert.equal(res.json.events[0].bookId, a.json.id);
    assert.equal(res.json.events[0].at, '2024-06-01T00:03:00.000Z');
    const limited = await app.request('GET', '/api/activity?limit=2');
    assert.equal(limited.json.events.length, 2);
    assert.equal((await app.request('GET', '/api/activity?limit=0')).status, 400);
    assert.equal((await app.request('GET', '/api/activity?limit=51')).status, 400);
  } finally {
    await app.close();
  }
});
