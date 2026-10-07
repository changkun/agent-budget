import { test } from 'node:test';
import assert from 'node:assert/strict';
import { start, titles } from './_helpers.js';

test('B04 sort books', async () => {
  const app = await start();
  try {
    const byYear = await app.request('GET', '/api/books?sort=year');
    assert.deepEqual(titles(byYear.json.items),
      ['Emma', 'Persuasion', 'The Hobbit', 'Dune', 'Neuromancer', 'Snow Crash']);
    const byYearDesc = await app.request('GET', '/api/books?sort=year&order=desc');
    assert.deepEqual(titles(byYearDesc.json.items),
      ['Snow Crash', 'Neuromancer', 'Dune', 'The Hobbit', 'Persuasion', 'Emma']);
    // null ratings go last in both directions; ties keep insertion order
    const byRating = await app.request('GET', '/api/books?sort=rating&order=desc');
    assert.deepEqual(titles(byRating.json.items),
      ['Dune', 'The Hobbit', 'Neuromancer', 'Persuasion', 'Emma', 'Snow Crash']);
    const byRatingAsc = await app.request('GET', '/api/books?sort=rating');
    assert.deepEqual(titles(byRatingAsc.json.items),
      ['Neuromancer', 'Persuasion', 'Dune', 'The Hobbit', 'Emma', 'Snow Crash']);
    const byTitle = await app.request('GET', '/api/books?sort=title&pageSize=2');
    assert.deepEqual(titles(byTitle.json.items), ['Dune', 'Emma']);
    const bad = await app.request('GET', '/api/books?sort=colour');
    assert.equal(bad.status, 400);
    const badOrder = await app.request('GET', '/api/books?sort=year&order=up');
    assert.equal(badOrder.status, 400);
    const unsorted = await app.request('GET', '/api/books');
    assert.equal(unsorted.json.items[0].title, 'Dune');
  } finally {
    await app.close();
  }
});
