import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B15 tag page', async () => {
  const app = await start();
  try {
    const page = await app.request('GET', '/tags/cyberpunk');
    assert.equal(page.status, 200);
    assert.match(page.text, /<a href="\/books\/3">Neuromancer<\/a>/);
    assert.match(page.text, /<a href="\/books\/6">Snow Crash<\/a>/);
    assert.doesNotMatch(page.text, /Persuasion/);
    const missing = await app.request('GET', '/tags/poetry');
    assert.equal(missing.status, 404);
    const home = await app.request('GET', '/');
    assert.match(home.text, /href="\/tags\/science-fiction"/);
    const detail = await app.request('GET', '/books/2');
    assert.match(detail.text, /href="\/tags\/romance"/);
  } finally {
    await app.close();
  }
});
