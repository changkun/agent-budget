# Bookshelf

A small reading-list web app: a JSON API and server-rendered HTML pages, built on Express.
Data lives in memory (optionally persisted to a JSON file with `BOOKSHELF_DATA=path`).

## Commands

```sh
npm install
npm start           # http://127.0.0.1:3000 with sample data
npm run build       # bundle src/client into dist/
npm test            # unit and HTTP tests in test/
npm run coverage    # tests with line coverage of src/ (client code excluded)
```

## Layout

```
src/app.js              createApp({ books, clock, store }) builds the Express app
src/server.js           starts the server with seed data
src/config.js           runtime settings
src/lib/                errors, validation, pagination, sorting helpers
src/models/             book validation and public shape, tag helpers
src/store/              in-memory BookStore and seed data
src/routes/api/         JSON API: /api/books, /api/tags
src/routes/pages.js     HTML pages: /, /books/new, /books/:id, /books/:id/edit
src/views/              HTML templates (tagged template literals, escaped by default)
src/client/             browser script and stylesheet, bundled by scripts/build.mjs
test/                   node:test suites
```

## API

- `GET /api/books?page=&pageSize=` returns `{ items, total, page, pageSize, pages }` in insertion order.
- `GET /api/books/:id`, `POST /api/books`, `PUT /api/books/:id` (partial update), `DELETE /api/books/:id`.
- `GET /api/tags` returns `{ tags: [{ name, count }] }`.
- `GET /healthz` returns `{ ok, books }`.
- Errors: `{ error: { code, message, fields? } }` with codes `bad_request`, `not_found`, `internal`.

A book: `{ id, title, author, year, tags, status, rating, notes, createdAt, updatedAt }` with
status in `want | reading | done` and rating 1-5 or null.

## Testing contract

`createApp` in `src/app.js` is the entry point used by HTTP tests: it takes the initial books
and an optional clock function, and returns an Express app. Keep its signature working.
