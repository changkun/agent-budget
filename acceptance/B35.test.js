import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B35 similar books', async () => {
  const app = await start();
  try {
    const emma = await app.request('GET', '/api/books/2/similar');
    assert.equal(emma.status, 200);
    assert.deepEqual(emma.json.items, [
      { id: 4, title: 'Persuasion', score: 7 },
      { id: 1, title: 'Dune', score: 2 },
      { id: 5, title: 'The Hobbit', score: 2 },
    ]);
    const neuro = await app.request('GET', '/api/books/3/similar');
    assert.deepEqual(neuro.json.items, [
      { id: 6, title: 'Snow Crash', score: 4 },
      { id: 1, title: 'Dune', score: 2 },
    ]);
    assert.equal((await app.request('GET', '/api/books/99/similar')).status, 404);
  } finally {
    await app.close();
  }
  const many = Array.from({ length: 8 }, (_, i) => ({ title: `T${i}`, author: 'Same' }));
  const app2 = await start({ books: many });
  try {
    const res = await app2.request('GET', '/api/books/1/similar');
    assert.deepEqual(res.json.items.map((b) => b.id), [2, 3, 4, 5, 6]);
  } finally {
    await app2.close();
  }
});
