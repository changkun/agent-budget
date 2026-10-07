import { test } from 'node:test';
import assert from 'node:assert/strict';
import { toPublic, validateBook } from '../src/models/book.js';
import { normalizeTag, tagCounts } from '../src/models/tag.js';

test('validateBook applies defaults', () => {
  const { value, errors } = validateBook({ title: 'A', author: 'B' });
  assert.deepEqual(errors, {});
  assert.equal(value.status, 'want');
  assert.equal(value.rating, null);
  assert.deepEqual(value.tags, []);
});

test('validateBook partial only checks given fields', () => {
  const { value, errors } = validateBook({ rating: 6 }, { partial: true });
  assert.deepEqual(Object.keys(value), []);
  assert.ok(errors.rating);
});

test('validateBook rejects non-objects', () => {
  assert.ok(validateBook(null).errors.body);
});

test('normalizeTag', () => {
  assert.equal(normalizeTag('  Science   Fiction '), 'science-fiction');
});

test('tagCounts', () => {
  assert.deepEqual(tagCounts([{ tags: ['a', 'b'] }, { tags: ['b'] }]), [
    { name: 'b', count: 2 }, { name: 'a', count: 1 },
  ]);
});

test('toPublic copies tags', () => {
  const book = { id: 1, title: 't', author: 'a', year: null, tags: ['x'], status: 'want', rating: null, notes: '' };
  const pub = toPublic(book);
  pub.tags.push('y');
  assert.deepEqual(book.tags, ['x']);
});
