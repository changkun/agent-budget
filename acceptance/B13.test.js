import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B13 authors endpoint', async () => {
  const app = await start();
  try {
    const res = await app.request('GET', '/api/authors');
    assert.equal(res.status, 200);
    assert.deepEqual(res.json.authors, [
      { name: 'Jane Austen', count: 2, books: [2, 4] },
      { name: 'Frank Herbert', count: 1, books: [1] },
      { name: 'J.R.R. Tolkien', count: 1, books: [5] },
      { name: 'Neal Stephenson', count: 1, books: [6] },
      { name: 'William Gibson', count: 1, books: [3] },
    ]);
  } finally {
    await app.close();
  }
});
