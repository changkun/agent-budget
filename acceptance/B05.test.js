import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B05 library statistics endpoint', async () => {
  const app = await start();
  try {
    const res = await app.request('GET', '/api/stats');
    assert.equal(res.status, 200);
    assert.equal(res.json.total, 6);
    assert.deepEqual(res.json.byStatus, { want: 2, reading: 1, done: 3 });
    assert.equal(res.json.averageRating, 4.5);
    assert.deepEqual(res.json.topTags, [
      { name: 'classic', count: 4 },
      { name: 'science-fiction', count: 3 },
      { name: 'cyberpunk', count: 2 },
    ]);
  } finally {
    await app.close();
  }
  const empty = await start({ books: [] });
  try {
    const res = await empty.request('GET', '/api/stats');
    assert.deepEqual(res.json, { total: 0, byStatus: { want: 0, reading: 0, done: 0 }, averageRating: null, topTags: [] });
  } finally {
    await empty.close();
  }
});
