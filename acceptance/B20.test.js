import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start, titles } from './_helpers.js';

test('B20 favorites', async () => {
  const app = await start();
  try {
    assert.equal((await app.request('GET', '/api/books/3')).json.favorite, false);
    const on = await app.request('POST', '/api/books/3/favorite');
    assert.equal(on.status, 200);
    assert.equal(on.json.favorite, true);
    await app.request('POST', '/api/books/5/favorite');
    const favs = await app.request('GET', '/api/books?favorite=true');
    assert.deepEqual(titles(favs.json.items), ['Neuromancer', 'The Hobbit']);
    const off = await app.request('POST', '/api/books/3/favorite');
    assert.equal(off.json.favorite, false);
    const favs2 = await app.request('GET', '/api/books?favorite=true');
    assert.deepEqual(titles(favs2.json.items), ['The Hobbit']);
    assert.equal((await app.request('POST', '/api/books/99/favorite')).status, 404);
  } finally {
    await app.close();
  }
});
