import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FORM, form, start } from './_helpers.js';

test('B32 trash with restore and purge', async () => {
  const app = await start();
  try {
    assert.equal((await app.request('DELETE', '/api/books/2')).status, 204);
    assert.equal((await app.request('GET', '/api/books/2')).status, 404);
    assert.equal((await app.request('GET', '/api/books')).json.total, 5);
    const trash = await app.request('GET', '/api/trash');
    assert.equal(trash.status, 200);
    assert.deepEqual(trash.json.items.map((b) => [b.id, b.title]), [[2, 'Emma']]);
    assert.equal(typeof trash.json.items[0].deletedAt, 'string');
    const restored = await app.request('POST', '/api/trash/2/restore');
    assert.equal(restored.status, 200);
    assert.equal(restored.json.title, 'Emma');
    assert.equal((await app.request('GET', '/api/books/2')).status, 200);
    assert.deepEqual((await app.request('GET', '/api/trash')).json.items, []);
    await app.request('DELETE', '/api/books/2');
    assert.equal((await app.request('DELETE', '/api/trash/2')).status, 204);
    assert.deepEqual((await app.request('GET', '/api/trash')).json.items, []);
    assert.equal((await app.request('POST', '/api/trash/2/restore')).status, 404);
    assert.equal((await app.request('DELETE', '/api/trash/2')).status, 404);
    const viaForm = await app.request('POST', '/books/3/delete', form({}), FORM);
    assert.equal(viaForm.status, 303);
    assert.deepEqual((await app.request('GET', '/api/trash')).json.items.map((b) => b.id), [3]);
  } finally {
    await app.close();
  }
});
