// Same-origin API calls with a fresh Firebase ID token (or the local dev token) per request.
// Answers are never cached, and a failed POST is never sent again automatically.

import { ApiError } from './logic/errors.js';

let tokenProvider = async () => { throw new ApiError(401, 'signed_out'); };
export function setTokenProvider(provider) { tokenProvider = provider; }

export async function api(method, path, body) {
  const token = await tokenProvider();
  const headers = { Authorization: 'Bearer ' + token, Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let response;
  try {
    response = await fetch(path, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store', credentials: 'omit', redirect: 'error',
    });
  } catch {
    throw new ApiError(0, '');
  }
  let data = null;
  if ((response.headers.get('Content-Type') || '').includes('application/json')) {
    try { data = await response.json(); } catch { data = null; }
  }
  if (!response.ok) throw new ApiError(response.status, data && typeof data.error === 'string' ? data.error : '');
  if (data === null || typeof data !== 'object' || Array.isArray(data)) throw new ApiError(response.status, 'invalid_response');
  return data;
}

export const path = (...pieces) => '/v1/' + pieces.map((piece) => encodeURIComponent(piece)).join('/');
