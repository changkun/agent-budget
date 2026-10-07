import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B08 bulk delete', async () => {
  const app = await start();
  try {
    const res = await app.request('POST', '/api/books/bulk-delete', { ids: [2, 4, 99] });
    assert.equal(res.status, 200);
    assert.deepEqual(res.json, { deleted: [2, 4], missing: [99] });
    assert.equal((await app.request('GET', '/api/books/2')).status, 404);
    assert.equal((await app.request('GET', '/api/books')).json.total, 4);
    const bad = await app.request('POST', '/api/books/bulk-delete', { ids: 'all' });
    assert.equal(bad.status, 400);
    const badItem = await app.request('POST', '/api/books/bulk-delete', { ids: [1, 'x'] });
    assert.equal(badItem.status, 400);
    assert.equal((await app.request('GET', '/api/books/1')).status, 200);
  } finally {
    await app.close();
  }
});
