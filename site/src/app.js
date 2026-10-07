import express from 'express';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { errorBody, toHttpError } from './lib/errors.js';
import { booksApi } from './routes/api/books.js';
import { tagsApi } from './routes/api/tags.js';
import { pages } from './routes/pages.js';
import { BookStore } from './store/memoryStore.js';
import { errorPage } from './views/layout.js';

const distDir = fileURLToPath(new URL('../dist', import.meta.url));

// Builds the Express app. Acceptance tests call createApp({ books, clock }).
//   books: initial books (array of book inputs), default none
//   clock: function returning the current Date, default real time
//   store: a ready BookStore (overrides books and clock)
export function createApp({ books = [], clock, store } = {}) {
  const bookStore = store || new BookStore({ books, clock });
  const app = express();
  app.locals.store = bookStore;
  app.disable('x-powered-by');
  app.use(express.json({ limit: '1mb' }));
  app.use(express.urlencoded({ extended: false }));
  if (existsSync(distDir)) {
    app.use('/static', express.static(distDir));
  }

  app.get('/healthz', (req, res) => {
    res.json({ ok: true, books: bookStore.list().length });
  });
  app.use('/api/books', booksApi(bookStore));
  app.use('/api/tags', tagsApi(bookStore));
  app.use('/', pages(bookStore));

  app.use('/api', (req, res) => {
    res.status(404).json({ error: { code: 'not_found', message: 'no such endpoint' } });
  });
  app.use((req, res) => {
    res.status(404).send(errorPage(404, 'Page not found'));
  });

  // eslint-disable-next-line no-unused-vars
  app.use((err, req, res, next) => {
    const httpErr = toHttpError(err);
    if (httpErr.status >= 500) console.error(err);
    if (req.path.startsWith('/api/')) {
      res.status(httpErr.status).json(errorBody(httpErr));
    } else {
      res.status(httpErr.status).send(errorPage(httpErr.status, httpErr.message));
    }
  });

  return app;
}
