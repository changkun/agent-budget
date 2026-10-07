import { config } from '../config.js';
import {
  oneOf, optionalInteger, optionalString, requiredString, stringList, validateFields,
} from '../lib/validate.js';
import { normalizeTag } from './tag.js';

export const STATUSES = ['want', 'reading', 'done'];

const CURRENT_YEAR = new Date().getFullYear();

const rules = {
  title: (v) => requiredString(v, { max: config.titleMaxLength }),
  author: (v) => requiredString(v, { max: config.titleMaxLength }),
  year: (v) => optionalInteger(v, { min: 0, max: CURRENT_YEAR + 1 }),
  tags: (v) => stringList(v, { max: config.tagsMax, normalize: normalizeTag }),
  status: (v) => oneOf(v, STATUSES, 'want'),
  rating: (v) => optionalInteger(v, { min: 1, max: 5 }),
  notes: (v) => optionalString(v, { max: config.notesMaxLength }),
};

export const BOOK_FIELDS = Object.keys(rules);

// Validates input for a new book (partial = false) or an update (partial = true).
// Unknown fields are ignored.
export function validateBook(input, { partial = false } = {}) {
  if (input === null || typeof input !== 'object' || Array.isArray(input)) {
    return { value: {}, errors: { body: 'must be an object' } };
  }
  return validateFields(input, rules, { partial });
}

export function toPublic(book) {
  return {
    id: book.id,
    title: book.title,
    author: book.author,
    year: book.year,
    tags: [...book.tags],
    status: book.status,
    rating: book.rating,
    notes: book.notes,
    createdAt: book.createdAt,
    updatedAt: book.updatedAt,
  };
}
