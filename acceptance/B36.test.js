import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fixture, manualClock, start } from './_helpers.js';

test('B36 recently updated books', async () => {
  const clock = manualClock('2024-01-01T00:00:00Z');
  const app = await start({ books: fixture, clock });
  try {
    clock.set('2024-01-02T00:00:00Z');
    await app.request('PUT', '/api/books/2', { rating: 3 });
    clock.set('2024-01-03T00:00:00Z');
    const created = await app.request('POST', '/api/books', { title: 'Fresh', author: 'New' });
    const res = await app.request('GET', '/api/books/recent?limit=3');
    assert.equal(res.status, 200);
    assert.deepEqual(res.json.items.map((b) => b.id), [created.json.id, 2, 6]);
    const def = await app.request('GET', '/api/books/recent');
    assert.deepEqual(def.json.items.map((b) => b.id), [7, 2, 6, 5, 4]);
    assert.equal((await app.request('GET', '/api/books/recent?limit=0')).status, 400);
    assert.equal((await app.request('GET', '/api/books/recent?limit=21')).status, 400);
  } finally {
    await app.close();
  }
});
