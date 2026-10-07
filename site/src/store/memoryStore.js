import { readFileSync, writeFileSync } from 'node:fs';
import { validateBook } from '../models/book.js';
import { badRequest } from '../lib/errors.js';

// In-memory book store. Ids are increasing integers. Optional JSON persistence.
export class BookStore {
  constructor({ books = [], clock = () => new Date(), file = null } = {}) {
    this.clock = clock;
    this.file = file;
    this.books = new Map();
    this.nextId = 1;
    for (const input of books) {
      this.create(input, { persist: false });
    }
  }

  static load(file, options = {}) {
    let books = [];
    try {
      books = JSON.parse(readFileSync(file, 'utf8')).books || [];
    } catch (err) {
      if (err.code !== 'ENOENT') throw err;
    }
    return new BookStore({ ...options, books, file });
  }

  now() {
    return this.clock().toISOString();
  }

  list() {
    return [...this.books.values()].sort((a, b) => a.id - b.id);
  }

  get(id) {
    return this.books.get(Number(id)) || null;
  }

  create(input, { persist = true } = {}) {
    const { value, errors } = validateBook(input);
    if (Object.keys(errors).length > 0) {
      throw badRequest('invalid book', errors);
    }
    const now = this.now();
    const book = { id: this.nextId++, ...value, createdAt: now, updatedAt: now };
    this.books.set(book.id, book);
    if (persist) this.save();
    return book;
  }

  update(id, patch) {
    const book = this.get(id);
    if (!book) return null;
    const { value, errors } = validateBook(patch, { partial: true });
    if (Object.keys(errors).length > 0) {
      throw badRequest('invalid book', errors);
    }
    Object.assign(book, value, { updatedAt: this.now() });
    this.save();
    return book;
  }

  remove(id) {
    const existed = this.books.delete(Number(id));
    if (existed) this.save();
    return existed;
  }

  save() {
    if (!this.file) return;
    writeFileSync(this.file, JSON.stringify({ books: this.list() }, null, 2));
  }
}
