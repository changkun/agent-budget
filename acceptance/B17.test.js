import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B17 search box on the home page', async () => {
  const app = await start();
  try {
    const page = await app.request('GET', '/?q=austen');
    assert.equal(page.status, 200);
    assert.match(page.text, /Emma/);
    assert.match(page.text, /Persuasion/);
    assert.doesNotMatch(page.text, /Neuromancer/);
    assert.match(page.text, /2 books/);
    assert.match(page.text, /<form[^>]*action="\/"[^>]*>/);
    assert.match(page.text, /<input[^>]*name="q"[^>]*value="austen"/);
    const all = await app.request('GET', '/');
    assert.match(all.text, /6 books/);
    assert.match(all.text, /<input[^>]*name="q"/);
  } finally {
    await app.close();
  }
});
