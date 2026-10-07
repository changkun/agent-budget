import { html } from './escape.js';
import { layout } from './layout.js';
import { statusLabel } from './bookList.js';

function paragraphs(text) {
  return text
    .split(/\n{2,}/)
    .filter((p) => p.trim() !== '')
    .map((p) => html`<p>${p}</p>`);
}

export function bookDetailPage({ book }) {
  const body = html`<article class="book" data-id="${book.id}">
    <h1>${book.title}</h1>
    <p class="author">by ${book.author}${book.year ? html` (${book.year})` : ''}</p>
    <dl>
      <dt>Status</dt><dd class="status">${statusLabel(book.status)}</dd>
      <dt>Rating</dt><dd class="rating">${book.rating ? `${book.rating} / 5` : 'not rated'}</dd>
      <dt>Tags</dt><dd>${book.tags.length ? book.tags.map((t) => html`<span class="tag">${t}</span> `) : 'none'}</dd>
    </dl>
    <section class="notes">${book.notes ? paragraphs(book.notes) : html`<p class="empty">No notes.</p>`}</section>
    <p class="actions">
      <a href="/books/${book.id}/edit">Edit</a>
    </p>
    <form method="post" action="/books/${book.id}/delete" class="delete-form">
      <button type="submit">Delete</button>
    </form>
  </article>`;
  return layout({ title: book.title, body });
}
