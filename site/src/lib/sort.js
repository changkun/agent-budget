// Comparators used by list endpoints and pages.

export function compareText(a, b) {
  return String(a ?? '').localeCompare(String(b ?? ''), 'en', { sensitivity: 'base' });
}

export function compareNumber(a, b) {
  if (a === b) return 0;
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  return a - b;
}

export function byField(field, kind = 'text') {
  const cmp = kind === 'number' ? compareNumber : compareText;
  return (x, y) => cmp(x[field], y[field]);
}

// Stable sort that does not mutate the input.
export function sortedBy(items, comparator) {
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => comparator(a.item, b.item) || a.index - b.index)
    .map(({ item }) => item);
}

export function byInsertion(a, b) {
  return a.id - b.id;
}
