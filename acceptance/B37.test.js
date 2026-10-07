import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B37 copy a book', async () => {
  const app = await start();
  try {
    const res = await app.request('POST', '/api/books/1/copy');
    assert.equal(res.status, 201);
    assert.equal(res.headers.get('location'), `/api/books/${res.json.id}`);
    assert.equal(res.json.id, 7);
    assert.equal(res.json.title, 'Dune (copy)');
    assert.equal(res.json.author, 'Frank Herbert');
    assert.equal(res.json.year, 1965);
    assert.deepEqual(res.json.tags, ['science-fiction', 'classic']);
    assert.equal(res.json.notes, 'Spice.');
    assert.equal(res.json.status, 'want');
    assert.equal(res.json.rating, null);
    assert.equal((await app.request('GET', '/api/books')).json.total, 7);
    assert.equal((await app.request('POST', '/api/books/99/copy')).status, 404);
  } finally {
    await app.close();
  }
});
