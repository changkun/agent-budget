import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start, titles } from './_helpers.js';

test('B07 import books from CSV', async () => {
  const app = await start({ books: [] });
  try {
    const csv = [
      'title,author,year,status,rating,tags',
      'Kindred,Octavia E. Butler,1979,done,5,classic;time-travel',
      'Nameless,,2001,want,,',
      '"Middlemarch, A Study",George Eliot,1871,want,,classic',
      '',
    ].join('\n');
    const res = await app.request('POST', '/api/books/import', csv, { 'content-type': 'text/csv' });
    assert.equal(res.status, 200);
    assert.equal(res.json.created, 2);
    assert.equal(res.json.errors.length, 1);
    assert.equal(res.json.errors[0].line, 3);
    assert.ok(res.json.errors[0].fields.author);
    const list = await app.request('GET', '/api/books');
    assert.deepEqual(titles(list.json.items), ['Kindred', 'Middlemarch, A Study']);
    assert.deepEqual(list.json.items[0].tags, ['classic', 'time-travel']);
    assert.equal(list.json.items[0].rating, 5);
    const missingHeader = await app.request('POST', '/api/books/import', 'name,writer\nX,Y\n', { 'content-type': 'text/csv' });
    assert.equal(missingHeader.status, 400);
  } finally {
    await app.close();
  }
});
