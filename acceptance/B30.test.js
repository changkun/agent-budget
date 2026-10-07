import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B30 delete a tag', async () => {
  const app = await start();
  try {
    const res = await app.request('DELETE', '/api/tags/classic');
    assert.equal(res.status, 200);
    assert.deepEqual(res.json, { removed: 4 });
    assert.deepEqual((await app.request('GET', '/api/books/1')).json.tags, ['science-fiction']);
    const tags = (await app.request('GET', '/api/tags')).json.tags.map((t) => t.name);
    assert.ok(!tags.includes('classic'));
    assert.equal((await app.request('DELETE', '/api/tags/classic')).status, 404);
    const normalized = await app.request('DELETE', '/api/tags/Science%20Fiction');
    assert.deepEqual(normalized.json, { removed: 3 });
  } finally {
    await app.close();
  }
});
