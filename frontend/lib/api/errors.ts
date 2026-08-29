export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function isNotFound(error: unknown) {
  return error instanceof ApiError && error.status === 404;
}

export function isConflict(error: unknown) {
  return error instanceof ApiError && error.status === 409;
}
