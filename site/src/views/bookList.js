import { html } from './escape.js';
import { layout } from './layout.js';

const STATUS_LABELS = { want: 'Want to read', reading: 'Reading', done: 'Done' };

export function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

function ratingStars(rating) {
  if (!rating) return '';
  return '★'.repeat(rating) + '☆'.repeat(5 - rating);
}

function row(book) {
  return html`<tr data-id="${book.id}">
    <td><a href="/books/${book.id}">${book.title}</a></td>
    <td>${book.author}</td>
    <td>${book.year ?? ''}</td>
    <td>${book.tags.map((t) => html`<span class="tag">${t}</span> `)}</td>
    <td>${statusLabel(book.status)}</td>
    <td class="rating">${ratingStars(book.rating)}</td>
  </tr>`;
}

export function bookListPage({ books }) {
  const body = books.length === 0
    ? html`<h1>Books</h1><p class="empty">No books yet. <a href="/books/new">Add one</a>.</p>`
    : html`<h1>Books</h1>
      <p class="count">${books.length} book${books.length === 1 ? '' : 's'}</p>
      <table class="books">
        <thead><tr><th>Title</th><th>Author</th><th>Year</th><th>Tags</th><th>Status</th><th>Rating</th></tr></thead>
        <tbody>${books.map(row)}</tbody>
      </table>`;
  return layout({ title: 'Books', body });
}
