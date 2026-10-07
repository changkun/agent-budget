import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fixture, start } from './_helpers.js';

test('B06 export books as CSV', async () => {
  const books = [...fixture.slice(0, 2), { title: 'Hello, "World"', author: 'A\nB', status: 'want' }];
  const app = await start({ books });
  try {
    const res = await app.request('GET', '/api/books.csv');
    assert.equal(res.status, 200);
    assert.match(res.headers.get('content-type'), /^text\/csv/);
    const lines = res.text.trimEnd().split(/\r?\n/);
    assert.equal(lines[0], 'id,title,author,year,status,rating,tags');
    assert.equal(lines[1], '1,Dune,Frank Herbert,1965,done,5,science-fiction;classic');
    assert.equal(lines[2], '2,Emma,Jane Austen,1815,want,,classic;romance');
    assert.equal(lines.slice(3).join('\n'), '3,"Hello, ""World""","A\nB",,want,,');
  } finally {
    await app.close();
  }
});
