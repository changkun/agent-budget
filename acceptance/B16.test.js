import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

function stat(htmlText, name) {
  const m = htmlText.match(new RegExp(`class="stat-${name}"[^>]*>\\s*(\\d+)\\s*<`));
  return m ? Number(m[1]) : null;
}

test('B16 statistics page', async () => {
  const app = await start();
  try {
    const page = await app.request('GET', '/stats');
    assert.equal(page.status, 200);
    assert.equal(stat(page.text, 'total'), 6);
    assert.equal(stat(page.text, 'want'), 2);
    assert.equal(stat(page.text, 'reading'), 1);
    assert.equal(stat(page.text, 'done'), 3);
    const home = await app.request('GET', '/');
    assert.match(home.text, /<nav>[\s\S]*href="\/stats"[\s\S]*<\/nav>/);
  } finally {
    await app.close();
  }
});
