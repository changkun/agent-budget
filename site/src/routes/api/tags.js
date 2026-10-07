import { Router } from 'express';
import { tagCounts } from '../../models/tag.js';

export function tagsApi(store) {
  const router = Router();

  router.get('/', (req, res) => {
    res.json({ tags: tagCounts(store.list()) });
  });

  return router;
}
