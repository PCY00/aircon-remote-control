// Installation proof for this phone: a uuid4 id and a 64-hex secret from crypto.getRandomValues.
// Pure helpers take the random bytes so they can be tested; neither value is ever shown on screen.

export const INSTALLATION_ID = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
export const SECRET = /^[a-f0-9]{64}$/;

export function hex(bytes) {
  let result = '';
  for (const byte of bytes) result += byte.toString(16).padStart(2, '0');
  return result;
}
/** RFC 4122 version 4 from 16 random bytes. */
export function uuid4(bytes) {
  if (!bytes || bytes.length !== 16) throw new RangeError('uuid4 needs 16 bytes');
  const b = Uint8Array.from(bytes);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = hex(b);
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
/** `fill` is crypto.getRandomValues (bound) or a test double. */
export function newInstallation(fill) {
  const id = new Uint8Array(16), secret = new Uint8Array(32);
  fill(id); fill(secret);
  return { installation: uuid4(id), secret: hex(secret) };
}
export function validInstallation(value) {
  return !!value && typeof value === 'object' && INSTALLATION_ID.test(value.installation || '') && SECRET.test(value.secret || '');
}
/** A new uuid4 request id for one aircon command (never reused for a different command). */
export function requestId(fill) { const bytes = new Uint8Array(16); fill(bytes); return uuid4(bytes); }
