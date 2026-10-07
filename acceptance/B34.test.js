import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B34 reviews', async () => {
  const app = await start();
  try {
    const r1 = await app.request('POST', '/api/books/1/reviews', { text: 'Great world-building.', rating: 5 });
    assert.equal(r1.status, 201);
    assert.equal(r1.json.bookId, 1);
    assert.equal(r1.json.text, 'Great world-building.');
    assert.equal(r1.json.rating, 5);
    assert.equal(typeof r1.json.createdAt, 'string');
    const r2 = await app.request('POST', '/api/books/1/reviews', { text: 'Slow middle.' });
    assert.equal(r2.json.rating, null);
    assert.equal((await app.request('POST', '/api/books/1/reviews', { text: '' })).status, 400);
    assert.equal((await app.request('POST', '/api/books/1/reviews', { text: 'x', rating: 6 })).status, 400);
    assert.equal((await app.request('POST', '/api/books/99/reviews', { text: 'x' })).status, 404);
    const list = await app.request('GET', '/api/books/1/reviews');
    assert.deepEqual(list.json.reviews.map((r) => r.text), ['Great world-building.', 'Slow middle.']);
    assert.deepEqual((await app.request('GET', '/api/books/2/reviews')).json.reviews, []);
    assert.equal((await app.request('DELETE', `/api/books/1/reviews/${r1.json.id}`)).status, 204);
    assert.deepEqual((await app.request('GET', '/api/books/1/reviews')).json.reviews.map((r) => r.id), [r2.json.id]);
    assert.equal((await app.request('DELETE', `/api/books/1/reviews/${r1.json.id}`)).status, 404);
  } finally {
    await app.close();
  }
});
