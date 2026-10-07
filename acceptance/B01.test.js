import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start, titles } from './_helpers.js';

test('B01 filter books by status', async () => {
  const app = await start();
  try {
    const done = await app.request('GET', '/api/books?status=done');
    assert.equal(done.status, 200);
    assert.deepEqual(titles(done.json.items), ['Dune', 'Persuasion', 'The Hobbit']);
    assert.equal(done.json.total, 3);
    const want = await app.request('GET', '/api/books?status=want&pageSize=1');
    assert.equal(want.json.total, 2);
    assert.deepEqual(titles(want.json.items), ['Emma']);
    const bad = await app.request('GET', '/api/books?status=lost');
    assert.equal(bad.status, 400);
    assert.equal(bad.json.error.code, 'bad_request');
  } finally {
    await app.close();
  }
});
