import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B26 ISBN field and lookup', async () => {
  const app = await start();
  try {
    const a = await app.request('POST', '/api/books', { title: 'Dune (paperback)', author: 'Frank Herbert', isbn: '978-0-441-17271-9' });
    assert.equal(a.status, 201);
    assert.equal(a.json.isbn, '9780441172719');
    const b = await app.request('POST', '/api/books', { title: 'Dune (old)', author: 'Frank Herbert', isbn: '0 441 17271 7' });
    assert.equal(b.json.isbn, '0441172717');
    const x = await app.request('POST', '/api/books', { title: 'Shogun', author: 'James Clavell', isbn: '080442957x' });
    assert.equal(x.status, 201);
    assert.equal(x.json.isbn, '080442957X');
    const bad = await app.request('POST', '/api/books', { title: 'Bad', author: 'B', isbn: '978-0-441-17271-8' });
    assert.equal(bad.status, 400);
    assert.ok(bad.json.error.fields.isbn);
    assert.equal((await app.request('GET', '/api/books/1')).json.isbn, null);
    const found = await app.request('GET', '/api/books/isbn/978-0441172719');
    assert.equal(found.status, 200);
    assert.equal(found.json.id, a.json.id);
    assert.equal((await app.request('GET', '/api/books/isbn/9780306406157')).status, 404);
  } finally {
    await app.close();
  }
});
