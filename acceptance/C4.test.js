import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start, titles } from './_helpers.js';

test('C4 format field and filter', async () => {
  const app = await start();
  try {
    assert.equal((await app.request('GET', '/api/books/1')).json.format, 'paper');
    const audio = await app.request('POST', '/api/books', { title: 'Circe', author: 'Madeline Miller', format: 'audio' });
    assert.equal(audio.status, 201);
    assert.equal(audio.json.format, 'audio');
    await app.request('PUT', '/api/books/3', { format: 'ebook' });
    assert.equal((await app.request('POST', '/api/books', { title: 'X', author: 'Y', format: 'scroll' })).status, 400);
    assert.deepEqual(titles((await app.request('GET', '/api/books?format=ebook')).json.items), ['Neuromancer']);
    const paper = await app.request('GET', '/api/books?format=paper');
    assert.equal(paper.json.total, 5);
    assert.equal((await app.request('GET', '/api/books?format=vinyl')).status, 400);
  } finally {
    await app.close();
  }
});
