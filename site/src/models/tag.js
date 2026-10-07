import { compareText } from '../lib/sort.js';

// Tags are lowercase, trimmed, with inner whitespace collapsed to single dashes.
export function normalizeTag(raw) {
  return String(raw).trim().toLowerCase().replace(/\s+/g, '-');
}

export function tagCounts(books) {
  const counts = new Map();
  for (const book of books) {
    for (const tag of book.tags) {
      counts.set(tag, (counts.get(tag) || 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || compareText(a.name, b.name));
}
