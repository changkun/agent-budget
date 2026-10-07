import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B28 random pick', async () => {
  const app = await start();
  try {
    const a = await app.request('GET', '/api/books/random?status=want&seed=0');
    assert.equal(a.status, 200);
    assert.equal(a.json.title, 'Emma');
    assert.equal((await app.request('GET', '/api/books/random?status=want&seed=1')).json.title, 'Snow Crash');
    assert.equal((await app.request('GET', '/api/books/random?status=want&seed=3')).json.title, 'Snow Crash');
    assert.equal((await app.request('GET', '/api/books/random?seed=4')).json.title, 'The Hobbit');
    const any = await app.request('GET', '/api/books/random?status=reading');
    assert.equal(any.json.title, 'Neuromancer');
    const none = await start({ books: [] });
    try {
      assert.equal((await none.request('GET', '/api/books/random')).status, 404);
    } finally {
      await none.close();
    }
    assert.equal((await app.request('GET', '/api/books/random?seed=-1')).status, 400);
  } finally {
    await app.close();
  }
});
