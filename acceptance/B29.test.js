import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start } from './_helpers.js';

test('B29 rename a tag', async () => {
  const app = await start();
  try {
    const res = await app.request('POST', '/api/tags/science-fiction/rename', { to: 'Sci Fi' });
    assert.equal(res.status, 200);
    assert.deepEqual(res.json, { renamed: 3 });
    assert.deepEqual((await app.request('GET', '/api/books/1')).json.tags, ['sci-fi', 'classic']);
    const merge = await app.request('POST', '/api/tags/romance/rename', { to: 'classic' });
    assert.deepEqual(merge.json, { renamed: 2 });
    assert.deepEqual((await app.request('GET', '/api/books/2')).json.tags, ['classic']);
    assert.equal((await app.request('POST', '/api/tags/poetry/rename', { to: 'verse' })).status, 404);
    assert.equal((await app.request('POST', '/api/tags/classic/rename', { to: '  ' })).status, 400);
  } finally {
    await app.close();
  }
});
