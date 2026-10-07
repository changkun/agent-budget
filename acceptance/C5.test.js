import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fixture, start } from './_helpers.js';

test('C5 oldest and newest books', async () => {
  const books = [{ title: 'Undated', author: 'Anon' }, ...fixture, { title: 'Also 1992', author: 'Z', year: 1992 }];
  const app = await start({ books });
  try {
    const oldest = await app.request('GET', '/api/books/oldest');
    assert.equal(oldest.status, 200);
    assert.equal(oldest.json.title, 'Emma');
    const newest = await app.request('GET', '/api/books/newest');
    assert.equal(newest.json.title, 'Snow Crash');
  } finally {
    await app.close();
  }
  const none = await start({ books: [{ title: 'Undated', author: 'Anon' }] });
  try {
    assert.equal((await none.request('GET', '/api/books/oldest')).status, 404);
    assert.equal((await none.request('GET', '/api/books/newest')).status, 404);
  } finally {
    await none.close();
  }
});
