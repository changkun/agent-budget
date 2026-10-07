import { createApp } from './app.js';
import { config } from './config.js';
import { BookStore } from './store/memoryStore.js';
import { seedBooks } from './store/seed.js';

const store = config.dataFile
  ? BookStore.load(config.dataFile)
  : new BookStore({ books: seedBooks });

const app = createApp({ store });
app.listen(config.port, config.host, () => {
  console.log(`bookshelf listening on http://${config.host}:${config.port}`);
});
