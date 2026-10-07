import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sampleBooks, startApp } from './helpers.js';

test('tags are counted and sorted by count then name', async () => {
  const app = await startApp({ books: sampleBooks });
  try {
    const res = await app.request('GET', '/api/tags');
    assert.equal(res.status, 200);
    assert.deepEqual(res.json.tags, [
      { name: 'science-fiction', count: 2 },
      { name: 'classic', count: 1 },
      { name: 'cyberpunk', count: 1 },
    ]);
  } finally {
    await app.close();
  }
});

test('health check reports the number of books', async () => {
  const app = await startApp({ books: sampleBooks });
  try {
    const res = await app.request('GET', '/healthz');
    assert.deepEqual(res.json, { ok: true, books: 3 });
  } finally {
    await app.close();
  }
});
