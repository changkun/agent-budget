import { config } from '../config.js';
import { badRequest } from './errors.js';

function parsePositive(raw, name, fallback) {
  if (raw === undefined || raw === '') return fallback;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 1) {
    throw badRequest(`${name} must be a positive integer`, { [name]: 'must be a positive integer' });
  }
  return n;
}

export function parsePageQuery(query) {
  const page = parsePositive(query.page, 'page', 1);
  const pageSize = Math.min(
    parsePositive(query.pageSize, 'pageSize', config.pageSizeDefault),
    config.pageSizeMax,
  );
  return { page, pageSize };
}

export function paginate(items, { page, pageSize }) {
  const total = items.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const start = (page - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    total,
    page,
    pageSize,
    pages,
  };
}
