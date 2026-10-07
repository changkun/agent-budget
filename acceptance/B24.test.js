import { test } from 'node:test';
import assert from 'node:assert/strict';
import { manualClock, start } from './_helpers.js';

test('B24 yearly reading goal', async () => {
  const clock = manualClock('2024-02-01T00:00:00Z');
  const app = await start({ books: [], clock });
  try {
    assert.equal((await app.request('GET', '/api/goal?year=2024')).status, 404);
    const set = await app.request('PUT', '/api/goal', { year: 2024, target: 4 });
    assert.equal(set.status, 200);
    assert.deepEqual(set.json, { year: 2024, target: 4 });
    await app.request('POST', '/api/books', { title: 'A', author: 'X', status: 'done' });
    const b = await app.request('POST', '/api/books', { title: 'B', author: 'X' });
    await app.request('PUT', `/api/books/${b.json.id}`, { status: 'done' });
    await app.request('POST', '/api/books', { title: 'C', author: 'X', status: 'reading' });
    clock.set('2025-01-02T00:00:00Z');
    await app.request('POST', '/api/books', { title: 'D', author: 'X', status: 'done' });
    const goal = await app.request('GET', '/api/goal?year=2024');
    assert.deepEqual(goal.json, { year: 2024, target: 4, done: 2, remaining: 2, percent: 50 });
    assert.equal((await app.request('PUT', '/api/goal', { year: 2024, target: 0 })).status, 400);
    assert.equal((await app.request('PUT', '/api/goal', { year: 'next', target: 3 })).status, 400);
    await app.request('PUT', '/api/goal', { year: 2025, target: 1 });
    const over = await app.request('GET', '/api/goal?year=2025');
    assert.deepEqual(over.json, { year: 2025, target: 1, done: 1, remaining: 0, percent: 100 });
  } finally {
    await app.close();
  }
});
