import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B09 reject duplicate books', async () => {
  const app = await start();
  try {
    const dup = await app.request('POST', '/api/books', { title: '  dune ', author: 'FRANK HERBERT' });
    assert.equal(dup.status, 409);
    assert.equal(dup.json.error.code, 'conflict');
    assert.equal(dup.json.error.existingId, 1);
    const other = await app.request('POST', '/api/books', { title: 'Dune', author: 'Brian Herbert' });
    assert.equal(other.status, 201);
    const rename = await app.request('PUT', `/api/books/${other.json.id}`, { author: 'Frank Herbert' });
    assert.equal(rename.status, 409);
    const self = await app.request('PUT', '/api/books/1', { title: 'Dune', rating: 4 });
    assert.equal(self.status, 200);
    assert.equal((await app.request('GET', '/api/books')).json.total, 7);
  } finally {
    await app.close();
  }
});
