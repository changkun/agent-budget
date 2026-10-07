import { STATUSES } from '../models/book.js';
import { html } from './escape.js';
import { layout } from './layout.js';
import { statusLabel } from './bookList.js';

function field(name, label, value, error, type = 'text') {
  return html`<p class="field${error ? ' has-error' : ''}">
    <label for="${name}">${label}</label>
    <input id="${name}" name="${name}" type="${type}" value="${value ?? ''}">
    ${error ? html`<span class="error">${error}</span>` : ''}
  </p>`;
}

export function bookFormPage({ book = {}, errors = {}, action, title }) {
  const tags = Array.isArray(book.tags) ? book.tags.join(', ') : book.tags;
  const body = html`<h1>${title}</h1>
    <form method="post" action="${action}" class="book-form">
      ${field('title', 'Title', book.title, errors.title)}
      ${field('author', 'Author', book.author, errors.author)}
      ${field('year', 'Year', book.year, errors.year, 'number')}
      ${field('tags', 'Tags (comma separated)', tags, errors.tags)}
      <p class="field${errors.status ? ' has-error' : ''}">
        <label for="status">Status</label>
        <select id="status" name="status">
          ${STATUSES.map((s) => html`<option value="${s}"${(book.status || 'want') === s ? html` selected` : ''}>${statusLabel(s)}</option>`)}
        </select>
      </p>
      ${field('rating', 'Rating (1-5)', book.rating, errors.rating, 'number')}
      <p class="field${errors.notes ? ' has-error' : ''}">
        <label for="notes">Notes</label>
        <textarea id="notes" name="notes" rows="6">${book.notes ?? ''}</textarea>
        ${errors.notes ? html`<span class="error">${errors.notes}</span>` : ''}
      </p>
      <p><button type="submit">Save</button></p>
    </form>`;
  return layout({ title, body });
}
