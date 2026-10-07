import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start, titles } from './_helpers.js';

test('B03 search books by title or author', async () => {
  const app = await start();
  try {
    const byAuthor = await app.request('GET', '/api/books?q=austen');
    assert.deepEqual(titles(byAuthor.json.items), ['Emma', 'Persuasion']);
    assert.equal(byAuthor.json.total, 2);
    const byTitle = await app.request('GET', '/api/books?q=CRASH');
    assert.deepEqual(titles(byTitle.json.items), ['Snow Crash']);
    const partial = await app.request('GET', '/api/books?q=ob');
    assert.deepEqual(titles(partial.json.items), ['The Hobbit']);
    const empty = await app.request('GET', '/api/books?q=');
    assert.equal(empty.json.total, 6);
  } finally {
    await app.close();
  }
});
