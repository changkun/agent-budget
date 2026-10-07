import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B19 lightweight formatting in notes', async () => {
  const notes = 'Hello **world** and *you*\nline two\n\n`x<y` <script>alert(1)</script>';
  const app = await start({ books: [{ title: 'Notes', author: 'Me', notes }] });
  try {
    const page = await app.request('GET', '/books/1');
    assert.match(page.text, /<strong>world<\/strong>/);
    assert.match(page.text, /<em>you<\/em>/);
    assert.match(page.text, /<br>\s*line two/);
    assert.match(page.text, /<code>x&lt;y<\/code>/);
    assert.doesNotMatch(page.text, /<script>alert/);
    assert.match(page.text, /&lt;script&gt;/);
    assert.equal((page.text.match(/<p>/g) || []).length >= 2, true);
  } finally {
    await app.close();
  }
});
