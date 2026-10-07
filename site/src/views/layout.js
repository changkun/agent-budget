import { html, toHtml } from './escape.js';

export function layout({ title, body }) {
  return toHtml(html`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${title} · Bookshelf</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <header class="site-header">
    <a class="brand" href="/">Bookshelf</a>
    <nav><a href="/">Books</a> <a href="/books/new">Add a book</a></nav>
  </header>
  <main>
    ${body}
  </main>
  <script src="/static/app.js" defer></script>
</body>
</html>`);
}

export function errorPage(status, message) {
  return layout({
    title: `Error ${status}`,
    body: html`<h1>Error ${status}</h1><p class="error">${message}</p><p><a href="/">Back to books</a></p>`,
  });
}
