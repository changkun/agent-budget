import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start, titles } from './_helpers.js';

test('C1 language field and filter', async () => {
  const app = await start();
  try {
    assert.equal((await app.request('GET', '/api/books/1')).json.language, null);
    const fr = await app.request('POST', '/api/books', { title: "L'Etranger", author: 'Albert Camus', language: 'FR' });
    assert.equal(fr.status, 201);
    assert.equal(fr.json.language, 'fr');
    await app.request('PUT', '/api/books/2', { language: 'en' });
    const bad = await app.request('POST', '/api/books', { title: 'X', author: 'Y', language: 'french' });
    assert.equal(bad.status, 400);
    assert.ok(bad.json.error.fields.language);
    const list = await app.request('GET', '/api/books?language=fr');
    assert.deepEqual(titles(list.json.items), ["L'Etranger"]);
    assert.equal(list.json.total, 1);
    assert.deepEqual(titles((await app.request('GET', '/api/books?language=en')).json.items), ['Emma']);
    assert.equal((await app.request('GET', '/api/books?language=xyz')).status, 400);
  } finally {
    await app.close();
  }
});
