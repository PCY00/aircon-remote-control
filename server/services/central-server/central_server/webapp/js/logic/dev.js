// Local screenshot hook: on 127.0.0.1 or localhost only, `#dev-token=<jwt>` replaces Firebase sign-in.
// Every reader goes through isDevHost, so the path cannot exist on any other host name.

const DEV_HOSTS = Object.freeze(['127.0.0.1', 'localhost']);
const TOKEN = /^[A-Za-z0-9._~+/=-]{1,8192}$/;
export const DEV_TOKEN_KEY = 'family-web.dev-token';

export function isDevHost(hostname) { return typeof hostname === 'string' && DEV_HOSTS.includes(hostname); }

/** The token in `#…dev-token=<jwt>…`, or null (always null off the two loopback names). */
export function devTokenFrom(hostname, hash) {
  if (!isDevHost(hostname) || typeof hash !== 'string') return null;
  for (const piece of hash.replace(/^#/, '').split('&')) {
    if (!piece.startsWith('dev-token=')) continue;
    const value = piece.slice('dev-token='.length);
    return TOKEN.test(value) ? value : null;
  }
  return null;
}
/** A token remembered for this tab; ignored off the loopback names even if one was stored. */
export function storedDevToken(hostname, stored) {
  return isDevHost(hostname) && typeof stored === 'string' && TOKEN.test(stored) ? stored : null;
}
/** The hash without the dev-token piece, so the token does not stay in the address bar. */
export function withoutDevToken(hash) {
  const rest = (typeof hash === 'string' ? hash.replace(/^#/, '') : '').split('&').filter((piece) => piece && !piece.startsWith('dev-token='));
  return rest.length ? '#' + rest.join('&') : '';
}
