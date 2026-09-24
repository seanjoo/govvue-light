import { idToken } from '../auth/cognito';
import { runtimeConfig } from '../runtimeConfig';

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await idToken();
  if (!token) throw new ApiError('Your session has expired. Sign in again.', 401);

  const response = await fetch(`${runtimeConfig.apiBaseUrl.replace(/\/$/, '')}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...init.headers,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(body.message ?? `Request failed (${response.status})`, response.status);
  }
  return body as T;
}
