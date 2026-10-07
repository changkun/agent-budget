import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B14 author page', async () => {
  const app = await start();
  try {
    const page = await app.request('GET', '/authors/Jane%20Austen');
    assert.equal(page.status, 200);
    assert.match(page.text, /<a href="\/books\/2">Emma<\/a>/);
    assert.match(page.text, /<a href="\/books\/4">Persuasion<\/a>/);
    assert.doesNotMatch(page.text, /Dune/);
    const missing = await app.request('GET', '/authors/Nobody');
    assert.equal(missing.status, 404);
    const home = await app.request('GET', '/');
    assert.match(home.text, /href="\/authors\/Jane%20Austen"/);
    const detail = await app.request('GET', '/books/5');
    assert.match(detail.text, /href="\/authors\/J\.R\.R\.%20Tolkien"/);
  } finally {
    await app.close();
  }
});
