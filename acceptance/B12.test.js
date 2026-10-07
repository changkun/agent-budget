import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fixture, start, titles } from './_helpers.js';

test('B12 filter books by year range', async () => {
  const app = await start({ books: [...fixture, { title: 'Undated', author: 'Anon' }] });
  try {
    const range = await app.request('GET', '/api/books?yearFrom=1900&yearTo=1984');
    assert.deepEqual(titles(range.json.items), ['Dune', 'Neuromancer', 'The Hobbit']);
    assert.equal(range.json.total, 3);
    const from = await app.request('GET', '/api/books?yearFrom=1985');
    assert.deepEqual(titles(from.json.items), ['Snow Crash']);
    const to = await app.request('GET', '/api/books?yearTo=1815');
    assert.deepEqual(titles(to.json.items), ['Emma']);
    const all = await app.request('GET', '/api/books');
    assert.equal(all.json.total, 7);
    const bad = await app.request('GET', '/api/books?yearFrom=old');
    assert.equal(bad.status, 400);
  } finally {
    await app.close();
  }
});
