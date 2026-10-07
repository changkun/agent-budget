import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B18 pagination on the home page', async () => {
  const books = Array.from({ length: 25 }, (_, i) => ({ title: `Book ${String(i + 1).padStart(2, '0')}`, author: 'Writer' }));
  const app = await start({ books });
  try {
    const p1 = await app.request('GET', '/');
    assert.match(p1.text, /Book 01/);
    assert.match(p1.text, /Book 10/);
    assert.doesNotMatch(p1.text, /Book 11/);
    assert.match(p1.text, /25 books/);
    assert.match(p1.text, /href="\/\?page=2"/);
    const p3 = await app.request('GET', '/?page=3');
    assert.match(p3.text, /Book 21/);
    assert.match(p3.text, /Book 25/);
    assert.doesNotMatch(p3.text, /Book 20/);
    assert.match(p3.text, /href="\/\?page=2"/);
    assert.doesNotMatch(p3.text, /href="\/\?page=4"/);
    const bad = await app.request('GET', '/?page=zero');
    assert.equal(bad.status, 400);
  } finally {
    await app.close();
  }
});
