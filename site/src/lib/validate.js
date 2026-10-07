// Small field validators. Each returns { value } or { error }.

export function requiredString(input, { max = Infinity } = {}) {
  if (typeof input !== 'string') return { error: 'is required' };
  const value = input.trim();
  if (value === '') return { error: 'is required' };
  if (value.length > max) return { error: `must be at most ${max} characters` };
  return { value };
}

export function optionalString(input, { max = Infinity } = {}) {
  if (input === undefined || input === null) return { value: '' };
  if (typeof input !== 'string') return { error: 'must be a string' };
  const value = input.trim();
  if (value.length > max) return { error: `must be at most ${max} characters` };
  return { value };
}

export function optionalInteger(input, { min = -Infinity, max = Infinity } = {}) {
  if (input === undefined || input === null || input === '') return { value: null };
  const value = typeof input === 'string' ? Number(input.trim()) : input;
  if (!Number.isInteger(value)) return { error: 'must be an integer' };
  if (value < min || value > max) return { error: `must be between ${min} and ${max}` };
  return { value };
}

export function oneOf(input, allowed, fallback) {
  if (input === undefined || input === null || input === '') return { value: fallback };
  if (!allowed.includes(input)) return { error: `must be one of ${allowed.join(', ')}` };
  return { value: input };
}

export function stringList(input, { max = Infinity, normalize = (s) => s } = {}) {
  if (input === undefined || input === null || input === '') return { value: [] };
  const raw = typeof input === 'string' ? input.split(',') : input;
  if (!Array.isArray(raw)) return { error: 'must be a list of strings' };
  const out = [];
  for (const item of raw) {
    if (typeof item !== 'string') return { error: 'must be a list of strings' };
    const value = normalize(item);
    if (value !== '' && !out.includes(value)) out.push(value);
  }
  if (out.length > max) return { error: `must have at most ${max} entries` };
  return { value: out };
}

// Runs a map of field validators against an input object.
// Fields missing from the input are skipped when partial is true.
export function validateFields(input, rules, { partial = false } = {}) {
  const value = {};
  const errors = {};
  for (const [field, rule] of Object.entries(rules)) {
    if (partial && !(field in input)) continue;
    const result = rule(input[field]);
    if (result.error) errors[field] = result.error;
    else value[field] = result.value;
  }
  return { value, errors };
}
