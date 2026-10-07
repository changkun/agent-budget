import { Router } from 'express';
import { HttpError } from '../lib/errors.js';
import { bookDetailPage } from '../views/bookDetail.js';
import { bookFormPage } from '../views/bookForm.js';
import { bookListPage } from '../views/bookList.js';
import { errorPage } from '../views/layout.js';

// Form posts send strings; empty optional fields become absent.
function formToInput(form) {
  const input = {};
  for (const [key, value] of Object.entries(form || {})) {
    input[key] = typeof value === 'string' && value.trim() === '' ? undefined : value;
  }
  return input;
}

export function pages(store) {
  const router = Router();

  function findOr404(id, res) {
    const book = store.get(id);
    if (!book) {
      res.status(404).send(errorPage(404, 'Book not found'));
      return null;
    }
    return book;
  }

  router.get('/', (req, res) => {
    res.send(bookListPage({ books: store.list() }));
  });

  router.get('/books/new', (req, res) => {
    res.send(bookFormPage({ action: '/books', title: 'Add a book' }));
  });

  router.post('/books', (req, res) => {
    try {
      const book = store.create(formToInput(req.body));
      res.redirect(303, `/books/${book.id}`);
    } catch (err) {
      if (!(err instanceof HttpError)) throw err;
      res.status(400).send(bookFormPage({
        book: req.body, errors: err.fields || {}, action: '/books', title: 'Add a book',
      }));
    }
  });

  router.get('/books/:id', (req, res) => {
    const book = findOr404(req.params.id, res);
    if (book) res.send(bookDetailPage({ book }));
  });

  router.get('/books/:id/edit', (req, res) => {
    const book = findOr404(req.params.id, res);
    if (book) {
      res.send(bookFormPage({ book, action: `/books/${book.id}`, title: `Edit ${book.title}` }));
    }
  });

  router.post('/books/:id', (req, res) => {
    const book = findOr404(req.params.id, res);
    if (!book) return;
    try {
      store.update(book.id, formToInput(req.body));
      res.redirect(303, `/books/${book.id}`);
    } catch (err) {
      if (!(err instanceof HttpError)) throw err;
      res.status(400).send(bookFormPage({
        book: { ...book, ...req.body }, errors: err.fields || {},
        action: `/books/${book.id}`, title: `Edit ${book.title}`,
      }));
    }
  });

  router.post('/books/:id/delete', (req, res) => {
    const book = findOr404(req.params.id, res);
    if (!book) return;
    store.remove(book.id);
    res.redirect(303, '/');
  });

  return router;
}
