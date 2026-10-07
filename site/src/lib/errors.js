// HTTP errors with a stable JSON shape: { error: { code, message, fields? } }.

export class HttpError extends Error {
  constructor(status, code, message, fields) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

export function notFound(what) {
  return new HttpError(404, 'not_found', `${what} not found`);
}

export function badRequest(message, fields) {
  return new HttpError(400, 'bad_request', message, fields);
}

export function errorBody(err) {
  const body = { error: { code: err.code || 'internal', message: err.message } };
  if (err.fields && Object.keys(err.fields).length > 0) {
    body.error.fields = err.fields;
  }
  return body;
}

export function toHttpError(err) {
  if (err instanceof HttpError) return err;
  if (err && err.type === 'entity.parse.failed') {
    return badRequest('request body is not valid JSON');
  }
  return new HttpError(500, 'internal', 'internal server error');
}
