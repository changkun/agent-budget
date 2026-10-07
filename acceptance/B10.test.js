import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B10 reading progress', async () => {
  const app = await start();
  try {
    const created = await app.request('POST', '/api/books', { title: 'Middlemarch', author: 'George Eliot', pageCount: 880, currentPage: 220 });
    assert.equal(created.status, 201);
    assert.equal(created.json.pageCount, 880);
    assert.equal(created.json.currentPage, 220);
    assert.equal(created.json.progress, 25);
    const upd = await app.request('PUT', `/api/books/${created.json.id}`, { currentPage: 293 });
    assert.equal(upd.json.progress, 33);
    const noPages = await app.request('GET', '/api/books/1');
    assert.equal(noPages.json.progress, null);
    const tooFar = await app.request('PUT', `/api/books/${created.json.id}`, { currentPage: 900 });
    assert.equal(tooFar.status, 400);
    assert.ok(tooFar.json.error.fields.currentPage);
    const badCount = await app.request('POST', '/api/books', { title: 'X', author: 'Y', pageCount: 0 });
    assert.equal(badCount.status, 400);
    assert.ok(badCount.json.error.fields.pageCount);
  } finally {
    await app.close();
  }
});
