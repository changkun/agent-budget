import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B39 request ids', async () => {
  const app = await start();
  try {
    const a = await app.request('GET', '/api/books');
    const b = await app.request('GET', '/');
    const idA = a.headers.get('x-request-id');
    const idB = b.headers.get('x-request-id');
    assert.match(idA, /^[A-Za-z0-9-]{8,}$/);
    assert.match(idB, /^[A-Za-z0-9-]{8,}$/);
    assert.notEqual(idA, idB);
    const missing = await app.request('GET', '/api/books/999');
    assert.match(missing.headers.get('x-request-id'), /^[A-Za-z0-9-]{8,}$/);
    const echoed = await app.request('GET', '/healthz', undefined, { 'x-request-id': 'abc-123' });
    assert.equal(echoed.headers.get('x-request-id'), 'abc-123');
  } finally {
    await app.close();
  }
});
