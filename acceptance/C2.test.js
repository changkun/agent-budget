import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('C2 word count of notes', async () => {
  const app = await start();
  try {
    assert.equal((await app.request('GET', '/api/books/1')).json.notesWordCount, 1);
    assert.equal((await app.request('GET', '/api/books/2')).json.notesWordCount, 0);
    const upd = await app.request('PUT', '/api/books/2', { notes: '  two  words\nthree ' });
    assert.equal(upd.json.notesWordCount, 3);
    const list = await app.request('GET', '/api/books');
    assert.deepEqual(list.json.items.map((b) => b.notesWordCount), [1, 3, 0, 0, 0, 0]);
    const page = await app.request('GET', '/books/2');
    assert.match(page.text, /3 words/);
  } finally {
    await app.close();
  }
});
