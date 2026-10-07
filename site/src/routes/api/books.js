import { Router } from 'express';
import { notFound } from '../../lib/errors.js';
import { paginate, parsePageQuery } from '../../lib/paginate.js';
import { toPublic } from '../../models/book.js';

export function booksApi(store) {
  const router = Router();

  function findOr404(id) {
    const book = store.get(id);
    if (!book) throw notFound('book');
    return book;
  }

  router.get('/', (req, res) => {
    const pageQuery = parsePageQuery(req.query);
    const result = paginate(store.list(), pageQuery);
    res.json({ ...result, items: result.items.map(toPublic) });
  });

  router.get('/:id', (req, res) => {
    res.json(toPublic(findOr404(req.params.id)));
  });

  router.post('/', (req, res) => {
    const book = store.create(req.body ?? {});
    res.status(201).location(`/api/books/${book.id}`).json(toPublic(book));
  });

  router.put('/:id', (req, res) => {
    findOr404(req.params.id);
    const book = store.update(req.params.id, req.body ?? {});
    res.json(toPublic(book));
  });

  router.delete('/:id', (req, res) => {
    findOr404(req.params.id);
    store.remove(req.params.id);
    res.status(204).end();
  });

  return router;
}
