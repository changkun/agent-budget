import { test } from 'node:test';
import assert from 'node:assert/strict';
import { manualClock, start } from './_helpers.js';

test('B11 started and finished dates follow status changes', async () => {
  const clock = manualClock('2024-03-01T10:00:00Z');
  const app = await start({ books: [], clock });
  try {
    const b = await app.request('POST', '/api/books', { title: 'Beloved', author: 'Toni Morrison' });
    assert.equal(b.json.startedAt, null);
    assert.equal(b.json.finishedAt, null);
    clock.set('2024-03-05T08:00:00Z');
    const reading = await app.request('PUT', `/api/books/${b.json.id}`, { status: 'reading' });
    assert.equal(reading.json.startedAt, '2024-03-05T08:00:00.000Z');
    assert.equal(reading.json.finishedAt, null);
    clock.set('2024-04-01T12:00:00Z');
    const done = await app.request('PUT', `/api/books/${b.json.id}`, { status: 'done' });
    assert.equal(done.json.startedAt, '2024-03-05T08:00:00.000Z');
    assert.equal(done.json.finishedAt, '2024-04-01T12:00:00.000Z');
    const back = await app.request('PUT', `/api/books/${b.json.id}`, { status: 'want' });
    assert.equal(back.json.startedAt, null);
    assert.equal(back.json.finishedAt, null);
    clock.set('2024-05-01T00:00:00Z');
    const direct = await app.request('POST', '/api/books', { title: 'Sula', author: 'Toni Morrison', status: 'done' });
    assert.equal(direct.json.startedAt, '2024-05-01T00:00:00.000Z');
    assert.equal(direct.json.finishedAt, '2024-05-01T00:00:00.000Z');
  } finally {
    await app.close();
  }
});
