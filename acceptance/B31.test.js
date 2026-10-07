import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

// Reference definition from the backlog item.
function coverColor(title) {
  let h = 0;
  for (const ch of title.toLowerCase()) h = (h * 31 + ch.codePointAt(0)) % 360;
  const s = 0.45;
  const l = 0.55;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  const hex = (v) => Math.round((v + m) * 255).toString(16).padStart(2, '0');
  return `#${hex(r)}${hex(g)}${hex(b)}`;
}

test('B31 deterministic cover colour', async () => {
  const app = await start();
  try {
    const list = await app.request('GET', '/api/books');
    for (const book of list.json.items) {
      assert.match(book.coverColor, /^#[0-9a-f]{6}$/);
      assert.equal(book.coverColor, coverColor(book.title));
    }
    assert.notEqual(list.json.items[0].coverColor, list.json.items[1].coverColor);
    const renamed = await app.request('PUT', '/api/books/1', { title: 'Dune Messiah' });
    assert.equal(renamed.json.coverColor, coverColor('Dune Messiah'));
    const page = await app.request('GET', '/books/2');
    const tag = page.text.match(/<[^>]*class="cover"[^>]*>/);
    assert.ok(tag, 'detail page has an element with class "cover"');
    assert.ok(tag[0].includes(coverColor('Emma')));
  } finally {
    await app.close();
  }
});
