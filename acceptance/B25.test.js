import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start, titles } from './_helpers.js';

test('B25 export and import the whole library as JSON', async () => {
  const app = await start();
  try {
    const exp = await app.request('GET', '/api/export');
    assert.equal(exp.status, 200);
    assert.equal(exp.json.version, 1);
    assert.equal(typeof exp.json.exportedAt, 'string');
    assert.equal(exp.json.books.length, 6);
    assert.equal(exp.json.books[0].title, 'Dune');
    const other = await start({ books: [{ title: 'Placeholder', author: 'Nobody' }] });
    try {
      const imp = await other.request('POST', '/api/import', { books: exp.json.books });
      assert.equal(imp.status, 200);
      assert.deepEqual(imp.json, { imported: 6 });
      const list = await other.request('GET', '/api/books');
      assert.deepEqual(titles(list.json.items), titles(exp.json.books));
      assert.deepEqual(list.json.items.map((b) => b.id), [1, 2, 3, 4, 5, 6]);
      assert.deepEqual(list.json.items[2].tags, ['science-fiction', 'cyberpunk']);
      const bad = await other.request('POST', '/api/import', { books: [{ title: 'Ok', author: 'A' }, { title: '' }] });
      assert.equal(bad.status, 400);
      assert.equal((await other.request('GET', '/api/books')).json.total, 6);
      assert.equal((await other.request('POST', '/api/import', { nope: true })).status, 400);
    } finally {
      await other.close();
    }
  } finally {
    await app.close();
  }
});
