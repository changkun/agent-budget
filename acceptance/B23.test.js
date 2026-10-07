import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fixture, start } from './_helpers.js';

test('B23 books per publication year', async () => {
  const books = [...fixture, { title: 'Undated', author: 'Anon' }, { title: 'Dune Messiah', author: 'Frank Herbert', year: 1965 }];
  const app = await start({ books });
  try {
    const res = await app.request('GET', '/api/stats/years');
    assert.equal(res.status, 200);
    assert.deepEqual(res.json.years, [
      { year: 1815, count: 1 }, { year: 1817, count: 1 }, { year: 1937, count: 1 },
      { year: 1965, count: 2 }, { year: 1984, count: 1 }, { year: 1992, count: 1 },
      { year: null, count: 1 },
    ]);
  } finally {
    await app.close();
  }
});
