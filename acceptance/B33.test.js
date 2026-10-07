import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fixture, manualClock, start } from './_helpers.js';

test('B33 lending books', async () => {
  const clock = manualClock('2024-07-01T09:00:00Z');
  const app = await start({ books: fixture, clock });
  try {
    assert.equal((await app.request('GET', '/api/books/1')).json.loan, null);
    const lent = await app.request('POST', '/api/books/1/loan', { to: 'Ana' });
    assert.equal(lent.status, 200);
    assert.deepEqual(lent.json.loan, { to: 'Ana', since: '2024-07-01T09:00:00.000Z' });
    assert.equal((await app.request('POST', '/api/books/1/loan', { to: 'Ben' })).status, 409);
    assert.equal((await app.request('POST', '/api/books/3/loan', { to: '' })).status, 400);
    assert.equal((await app.request('POST', '/api/books/99/loan', { to: 'Ana' })).status, 404);
    clock.set('2024-07-02T09:00:00Z');
    await app.request('POST', '/api/books/5/loan', { to: 'Cleo' });
    const loans = await app.request('GET', '/api/loans');
    assert.deepEqual(loans.json.loans, [
      { bookId: 1, title: 'Dune', to: 'Ana', since: '2024-07-01T09:00:00.000Z' },
      { bookId: 5, title: 'The Hobbit', to: 'Cleo', since: '2024-07-02T09:00:00.000Z' },
    ]);
    const back = await app.request('POST', '/api/books/1/return');
    assert.equal(back.status, 200);
    assert.equal(back.json.loan, null);
    assert.equal((await app.request('POST', '/api/books/1/return')).status, 409);
    assert.equal((await app.request('GET', '/api/loans')).json.loans.length, 1);
  } finally {
    await app.close();
  }
});
