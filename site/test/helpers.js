import { createApp } from '../src/app.js';

export const sampleBooks = [
  { title: 'Dune', author: 'Frank Herbert', year: 1965, tags: ['science-fiction'], status: 'done', rating: 5 },
  { title: 'Emma', author: 'Jane Austen', year: 1815, tags: ['classic'], status: 'want' },
  { title: 'Neuromancer', author: 'William Gibson', year: 1984, tags: ['science-fiction', 'cyberpunk'], status: 'reading' },
];

// Starts the app on a random port. Returns { base, request, close }.
export async function startApp(options = {}) {
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
  return {
    base,
    app,
    request,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

export function form(fields) {
  return new URLSearchParams(fields).toString();
}

export const FORM = { 'content-type': 'application/x-www-form-urlencoded' };
