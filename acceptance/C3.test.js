import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('C3 publisher field and publishers endpoint', async () => {
  const app = await start();
  try {
    assert.equal((await app.request('GET', '/api/books/1')).json.publisher, null);
    await app.request('PUT', '/api/books/1', { publisher: 'Chilton Books' });
    await app.request('PUT', '/api/books/3', { publisher: 'Ace' });
    await app.request('PUT', '/api/books/6', { publisher: 'Bantam' });
    await app.request('PUT', '/api/books/2', { publisher: '  Ace ' });
    const res = await app.request('GET', '/api/publishers');
    assert.equal(res.status, 200);
    assert.deepEqual(res.json.publishers, [
      { name: 'Ace', count: 2 }, { name: 'Bantam', count: 1 }, { name: 'Chilton Books', count: 1 },
    ]);
    const tooLong = await app.request('POST', '/api/books', { title: 'X', author: 'Y', publisher: 'p'.repeat(101) });
    assert.equal(tooLong.status, 400);
    assert.ok(tooLong.json.error.fields.publisher);
  } finally {
    await app.close();
  }
});
