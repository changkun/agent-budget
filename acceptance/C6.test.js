import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('C6 dropped status with a reason', async () => {
  const app = await start();
  try {
    assert.equal((await app.request('GET', '/api/books/3')).json.droppedReason, null);
    const noReason = await app.request('PUT', '/api/books/3', { status: 'dropped' });
    assert.equal(noReason.status, 400);
    assert.ok(noReason.json.error.fields.droppedReason);
    const dropped = await app.request('PUT', '/api/books/3', { status: 'dropped', droppedReason: 'Too dense' });
    assert.equal(dropped.status, 200);
    assert.equal(dropped.json.status, 'dropped');
    assert.equal(dropped.json.droppedReason, 'Too dense');
    const resumed = await app.request('PUT', '/api/books/3', { status: 'reading' });
    assert.equal(resumed.json.droppedReason, null);
    const created = await app.request('POST', '/api/books', { title: 'Ulysses', author: 'James Joyce', status: 'dropped', droppedReason: 'Later' });
    assert.equal(created.status, 201);
    const page = await app.request('GET', `/books/${created.json.id}`);
    assert.match(page.text, /Later/);
  } finally {
    await app.close();
  }
});
