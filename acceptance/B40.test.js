import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FORM, form, start } from './_helpers.js';

test('B40 rate a book from its page', async () => {
  const app = await start();
  try {
    const page = await app.request('GET', '/books/2');
    assert.match(page.text, /<form[^>]*method="post"[^>]*action="\/books\/2\/rating"/);
    assert.match(page.text, /<select[^>]*name="rating"/);
    const res = await app.request('POST', '/books/2/rating', form({ rating: '4' }), FORM);
    assert.equal(res.status, 303);
    assert.equal(res.headers.get('location'), '/books/2');
    assert.equal((await app.request('GET', '/api/books/2')).json.rating, 4);
    const bad = await app.request('POST', '/books/2/rating', form({ rating: '9' }), FORM);
    assert.equal(bad.status, 400);
    assert.equal((await app.request('GET', '/api/books/2')).json.rating, 4);
    assert.equal((await app.request('POST', '/books/99/rating', form({ rating: '3' }), FORM)).status, 404);
  } finally {
    await app.close();
  }
});
