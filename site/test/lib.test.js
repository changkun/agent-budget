import { test } from 'node:test';
import assert from 'node:assert/strict';
import { paginate } from '../src/lib/paginate.js';
import { byField, sortedBy } from '../src/lib/sort.js';
import { optionalInteger, stringList } from '../src/lib/validate.js';
import { escapeHtml, html, toHtml } from '../src/views/escape.js';

test('paginate', () => {
  const r = paginate([1, 2, 3, 4, 5], { page: 2, pageSize: 2 });
  assert.deepEqual(r, { items: [3, 4], total: 5, page: 2, pageSize: 2, pages: 3 });
});

test('sortedBy is stable', () => {
  const items = [{ n: 'b', i: 1 }, { n: 'a', i: 2 }, { n: 'b', i: 3 }];
  assert.deepEqual(sortedBy(items, byField('n')).map((x) => x.i), [2, 1, 3]);
});

test('optionalInteger parses strings', () => {
  assert.deepEqual(optionalInteger('12'), { value: 12 });
  assert.ok(optionalInteger('1.5').error);
});

test('stringList splits and dedupes', () => {
  assert.deepEqual(stringList('a, b, a', { normalize: (s) => s.trim() }), { value: ['a', 'b'] });
});

test('html escapes values', () => {
  assert.equal(escapeHtml('<a href="x">'), '&lt;a href=&quot;x&quot;&gt;');
  assert.equal(toHtml(html`<p>${'<i>'}</p>`), '<p>&lt;i&gt;</p>');
});
