import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start, titles } from './_helpers.js';

test('B02 filter books by tag', async () => {
  const app = await start();
  try {
    const res = await app.request('GET', '/api/books?tag=cyberpunk');
    assert.equal(res.status, 200);
    assert.deepEqual(titles(res.json.items), ['Neuromancer', 'Snow Crash']);
    assert.equal(res.json.total, 2);
    const normalized = await app.request('GET', '/api/books?tag=Science%20Fiction');
    assert.deepEqual(titles(normalized.json.items), ['Dune', 'Neuromancer', 'Snow Crash']);
    const none = await app.request('GET', '/api/books?tag=poetry');
    assert.equal(none.status, 200);
    assert.deepEqual(none.json.items, []);
    assert.equal(none.json.total, 0);
  } finally {
    await app.close();
  }
});
