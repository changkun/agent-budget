// Shared helpers for acceptance tests. Restored from the original copy before every
// evaluation; changes made inside a working copy are discarded.
import { createApp } from '../src/app.js';

export const fixture = [
  { title: 'Dune', author: 'Frank Herbert', year: 1965, tags: ['science-fiction', 'classic'], status: 'done', rating: 5, notes: 'Spice.' },
  { title: 'Emma', author: 'Jane Austen', year: 1815, tags: ['classic', 'romance'], status: 'want' },
  { title: 'Neuromancer', author: 'William Gibson', year: 1984, tags: ['science-fiction', 'cyberpunk'], status: 'reading', rating: 4 },
  { title: 'Persuasion', author: 'Jane Austen', year: 1817, tags: ['classic', 'romance'], status: 'done', rating: 4 },
  { title: 'The Hobbit', author: 'J.R.R. Tolkien', year: 1937, tags: ['fantasy', 'classic'], status: 'done', rating: 5 },
  { title: 'Snow Crash', author: 'Neal Stephenson', year: 1992, tags: ['science-fiction', 'cyberpunk'], status: 'want' },
];

// A clock whose time can be set by the test.
export function manualClock(iso) {
  let now = new Date(iso);
  const clock = () => new Date(now.getTime());
  clock.set = (next) => { now = new Date(next); };
  return clock;
}

// Starts createApp(options) on a random port.
export async function start(options = { books: fixture }) {
  const app = createApp(options);
  const server = await new Promise((resolve) => {
    const s = app.listen(0, '127.0.0.1', () => resolve(s));
  });
  const base = `http://127.0.0.1:${server.address().port}`;
  async function request(method, path, body, headers = {}) {
    const init = { method, headers: { ...headers }, redirect: 'manual' };
    if (body !== undefined) {
      if (typeof body === 'string') {
        init.body = body;
      } else {
        init.body = JSON.stringify(body);
        init.headers['content-type'] = 'application/json';
      }
    }
    const res = await fetch(base + path, init);
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* not JSON */ }
    return { status: res.status, headers: res.headers, text, json };
  }
  return { base, request, close: () => new Promise((resolve) => server.close(resolve)) };
}

export const FORM = { 'content-type': 'application/x-www-form-urlencoded' };

export function form(fields) {
  return new URLSearchParams(fields).toString();
}

export function titles(items) {
  return items.map((b) => b.title);
}
