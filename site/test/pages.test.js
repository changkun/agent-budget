import { after, before, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { FORM, form, sampleBooks, startApp } from './helpers.js';

describe('pages', () => {
  let app;
  before(async () => { app = await startApp({ books: sampleBooks }); });
  after(() => app.close());

  test('home page lists books', async () => {
    const res = await app.request('GET', '/');
    assert.equal(res.status, 200);
    assert.match(res.text, /Dune/);
    assert.match(res.text, /3 books/);
  });

  test('detail page escapes HTML', async () => {
    const created = await app.request('POST', '/api/books', { title: '<b>Bold</b>', author: 'X' });
    const res = await app.request('GET', `/books/${created.json.id}`);
    assert.match(res.text, /&lt;b&gt;Bold&lt;\/b&gt;/);
  });

  test('form creates a book and redirects', async () => {
    const res = await app.request('POST', '/books', form({ title: 'Beloved', author: 'Toni Morrison', year: '', tags: 'classic, novel' }), FORM);
    assert.equal(res.status, 303);
    const page = await app.request('GET', res.headers.get('location'));
    assert.match(page.text, /Beloved/);
    assert.match(page.text, /novel/);
  });

  test('form shows validation errors', async () => {
    const res = await app.request('POST', '/books', form({ title: '', author: '' }), FORM);
    assert.equal(res.status, 400);
    assert.match(res.text, /is required/);
  });

  test('edit form updates a book', async () => {
    const edit = await app.request('GET', '/books/1/edit');
    assert.match(edit.text, /value="Dune"/);
    const res = await app.request('POST', '/books/1', form({ title: 'Dune', author: 'Frank Herbert', status: 'reading' }), FORM);
    assert.equal(res.status, 303);
  });

  test('missing book page is 404', async () => {
    const res = await app.request('GET', '/books/12345');
    assert.equal(res.status, 404);
    assert.match(res.text, /not found/);
  });
});
