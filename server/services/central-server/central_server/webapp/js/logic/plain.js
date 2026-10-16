// Typed reads from parsed server JSON. No DOM: shared by the app and the Node tests.
// Mirrors Plain.java of the Android family app.

export function isMap(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
export function map(value) { return isMap(value) ? value : {}; }
export function list(value) { return Array.isArray(value) ? value : []; }
/** A string, or the fallback (null) for anything else. */
export function text(value, fallback = null) { return typeof value === 'string' ? value : fallback; }
/** A finite number (booleans are not numbers), or null. */
export function number(value) { return typeof value === 'number' && Number.isFinite(value) ? value : null; }
export function flag(value) { return value === true; }

const HIDDEN = /[\p{Cc}\p{Cf}]/gu;
/** Drops control and format characters (Unicode Cc/Cf), trims and cuts to `maximum` UTF-16 units. */
export function clean(value, maximum) {
  if (typeof value !== 'string') return '';
  const result = value.replace(HIDDEN, '').trim();
  return result.length > maximum ? result.slice(0, maximum) : result;
}
