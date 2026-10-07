import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { BookStore } from '../src/store/memoryStore.js';

test('store assigns ids and timestamps from the clock', () => {
  const clock = () => new Date('2024-01-02T03:04:05Z');
  const store = new BookStore({ clock });
  const book = store.create({ title: 'A', author: 'B' });
  assert.equal(book.id, 1);
  assert.equal(book.createdAt, '2024-01-02T03:04:05.000Z');
});

test('store persists to a file and loads it back', () => {
  const file = join(mkdtempSync(join(tmpdir(), 'shelf-')), 'data.json');
  const store = BookStore.load(file);
  store.create({ title: 'A', author: 'B' });
  assert.equal(JSON.parse(readFileSync(file, 'utf8')).books.length, 1);
  const again = BookStore.load(file);
  assert.equal(again.list()[0].title, 'A');
});
