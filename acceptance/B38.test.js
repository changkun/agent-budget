import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B38 export as Markdown', async () => {
  const app = await start();
  try {
    const res = await app.request('GET', '/api/books.md');
    assert.equal(res.status, 200);
    assert.match(res.headers.get('content-type'), /^text\/markdown/);
    assert.equal(res.text.trim(), [
      '## Want to read', '',
      '- *Emma* by Jane Austen (1815)',
      '- *Snow Crash* by Neal Stephenson (1992)', '',
      '## Reading', '',
      '- *Neuromancer* by William Gibson (1984)', '',
      '## Done', '',
      '- *Dune* by Frank Herbert (1965)',
      '- *Persuasion* by Jane Austen (1817)',
      '- *The Hobbit* by J.R.R. Tolkien (1937)',
    ].join('\n'));
  } finally {
    await app.close();
  }
  const app2 = await start({ books: [{ title: 'Solo', author: 'A', status: 'reading' }] });
  try {
    const res = await app2.request('GET', '/api/books.md');
    assert.equal(res.text.trim(), '## Reading\n\n- *Solo* by A');
  } finally {
    await app2.close();
  }
});
