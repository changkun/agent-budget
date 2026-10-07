import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B21 shelves', async () => {
  const app = await start();
  try {
    const shelf = await app.request('POST', '/api/shelves', { name: 'Summer' });
    assert.equal(shelf.status, 201);
    assert.deepEqual(shelf.json, { id: shelf.json.id, name: 'Summer', bookIds: [] });
    assert.equal((await app.request('POST', '/api/shelves', { name: '' })).status, 400);
    assert.equal((await app.request('POST', '/api/shelves', { name: 'summer' })).status, 409);
    const id = shelf.json.id;
    const add = await app.request('PUT', `/api/shelves/${id}/books/3`);
    assert.equal(add.status, 200);
    await app.request('PUT', `/api/shelves/${id}/books/3`);
    await app.request('PUT', `/api/shelves/${id}/books/5`);
    assert.deepEqual((await app.request('GET', '/api/shelves')).json.shelves, [{ id, name: 'Summer', bookIds: [3, 5] }]);
    assert.equal((await app.request('PUT', `/api/shelves/${id}/books/99`)).status, 404);
    assert.equal((await app.request('PUT', '/api/shelves/999/books/1')).status, 404);
    const rm = await app.request('DELETE', `/api/shelves/${id}/books/3`);
    assert.equal(rm.status, 200);
    assert.deepEqual(rm.json.bookIds, [5]);
    await app.request('DELETE', '/api/books/5');
    assert.deepEqual((await app.request('GET', '/api/shelves')).json.shelves[0].bookIds, []);
  } finally {
    await app.close();
  }
});
