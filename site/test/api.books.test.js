import { after, before, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { sampleBooks, startApp } from './helpers.js';

describe('books API', () => {
  let app;
  before(async () => { app = await startApp({ books: sampleBooks }); });
  after(() => app.close());

  test('lists books in insertion order with pagination fields', async () => {
    const res = await app.request('GET', '/api/books');
    assert.equal(res.status, 200);
    assert.equal(res.json.total, 3);
    assert.equal(res.json.page, 1);
    assert.deepEqual(res.json.items.map((b) => b.title), ['Dune', 'Emma', 'Neuromancer']);
  });

  test('paginates', async () => {
    const res = await app.request('GET', '/api/books?page=2&pageSize=2');
    assert.equal(res.json.items.length, 1);
    assert.equal(res.json.pages, 2);
  });

  test('rejects a bad page number', async () => {
    const res = await app.request('GET', '/api/books?page=0');
    assert.equal(res.status, 400);
    assert.equal(res.json.error.code, 'bad_request');
  });

  test('gets one book', async () => {
    const res = await app.request('GET', '/api/books/1');
    assert.equal(res.status, 200);
    assert.equal(res.json.title, 'Dune');
    assert.deepEqual(res.json.tags, ['science-fiction']);
  });

  test('returns 404 for a missing book', async () => {
    const res = await app.request('GET', '/api/books/999');
    assert.equal(res.status, 404);
    assert.equal(res.json.error.code, 'not_found');
  });

  test('creates a book', async () => {
    const res = await app.request('POST', '/api/books', {
      title: '  Kindred ', author: 'Octavia E. Butler', year: 1979, tags: ['Classic', 'time travel'],
    });
    assert.equal(res.status, 201);
    assert.equal(res.json.title, 'Kindred');
    assert.equal(res.json.status, 'want');
    assert.deepEqual(res.json.tags, ['classic', 'time-travel']);
    assert.match(res.headers.get('location'), /^\/api\/books\/\d+$/);
  });

  test('validates input', async () => {
    const res = await app.request('POST', '/api/books', { title: '', year: 'soon', status: 'lost' });
    assert.equal(res.status, 400);
    assert.deepEqual(Object.keys(res.json.error.fields).sort(), ['author', 'status', 'title', 'year']);
  });

  test('rejects malformed JSON', async () => {
    const res = await app.request('POST', '/api/books', '{"title":', { 'content-type': 'application/json' });
    assert.equal(res.status, 400);
  });

  test('updates a book partially', async () => {
    const res = await app.request('PUT', '/api/books/2', { status: 'reading', rating: 4 });
    assert.equal(res.status, 200);
    assert.equal(res.json.status, 'reading');
    assert.equal(res.json.rating, 4);
    assert.equal(res.json.title, 'Emma');
  });

  test('deletes a book', async () => {
    const created = await app.request('POST', '/api/books', { title: 'Temp', author: 'Someone' });
    const del = await app.request('DELETE', `/api/books/${created.json.id}`);
    assert.equal(del.status, 204);
    const again = await app.request('GET', `/api/books/${created.json.id}`);
    assert.equal(again.status, 404);
  });

  test('unknown API path returns JSON 404', async () => {
    const res = await app.request('GET', '/api/nothing');
    assert.equal(res.status, 404);
    assert.equal(res.json.error.code, 'not_found');
  });
});
