import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B27 series', async () => {
  const app = await start({ books: [] });
  try {
    await app.request('POST', '/api/books', { title: 'The Two Towers', author: 'J.R.R. Tolkien', series: 'The Lord of the Rings', seriesNumber: 2 });
    await app.request('POST', '/api/books', { title: 'Foundation', author: 'Isaac Asimov', series: 'Foundation', seriesNumber: 1 });
    await app.request('POST', '/api/books', { title: 'The Fellowship of the Ring', author: 'J.R.R. Tolkien', series: 'The Lord of the Rings', seriesNumber: 1 });
    await app.request('POST', '/api/books', { title: 'Standalone', author: 'Someone' });
    const res = await app.request('GET', '/api/series');
    assert.equal(res.status, 200);
    assert.deepEqual(res.json.series, [
      { name: 'Foundation', books: [{ id: 2, title: 'Foundation', seriesNumber: 1 }] },
      { name: 'The Lord of the Rings', books: [
        { id: 3, title: 'The Fellowship of the Ring', seriesNumber: 1 },
        { id: 1, title: 'The Two Towers', seriesNumber: 2 },
      ] },
    ]);
    const book = await app.request('GET', '/api/books/1');
    assert.equal(book.json.series, 'The Lord of the Rings');
    assert.equal(book.json.seriesNumber, 2);
    assert.equal((await app.request('GET', '/api/books/4')).json.series, null);
    const orphan = await app.request('POST', '/api/books', { title: 'X', author: 'Y', seriesNumber: 3 });
    assert.equal(orphan.status, 400);
    const badNum = await app.request('POST', '/api/books', { title: 'X', author: 'Y', series: 'S', seriesNumber: 0 });
    assert.equal(badNum.status, 400);
  } finally {
    await app.close();
  }
});
