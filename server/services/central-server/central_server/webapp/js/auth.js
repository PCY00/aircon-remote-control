// Sign-in: Firebase Auth with Google by redirect (authDomain is this server, which forwards /__/auth/ to
// Firebase), or, on 127.0.0.1/localhost only, a `#dev-token=<jwt>` for local screenshots.

import { DEV_TOKEN_KEY, devTokenFrom, storedDevToken, withoutDevToken } from './logic/dev.js';
import { ApiError, signInMessage } from './logic/errors.js';

let devToken = null;
let firebase = null; // {app, auth, mod}
let config = null;

/** Reads (and removes from the address bar) a dev token; always false off the loopback names. */
export function detectDevToken() {
  const host = location.hostname;
  let token = devTokenFrom(host, location.hash);
  if (token) {
    try { sessionStorage.setItem(DEV_TOKEN_KEY, token); } catch { /* tab-only convenience */ }
    history.replaceState(history.state, '', location.pathname + location.search + withoutDevToken(location.hash));
  } else {
    let stored = null;
    try { stored = sessionStorage.getItem(DEV_TOKEN_KEY); } catch { stored = null; }
    token = storedDevToken(host, stored);
  }
  devToken = token;
  return token !== null;
}
export function isDev() { return devToken !== null; }

/** GET /app/config.json: {firebase, server_version} or {error}. */
export async function loadConfig() {
  let response;
  try {
    response = await fetch('config.json', { cache: 'no-store', credentials: 'omit', redirect: 'error' });
  } catch {
    return { error: 'network' };
  }
  let data = null;
  try { data = await response.json(); } catch { data = null; }
  if (!response.ok || !data || typeof data !== 'object') return { error: data && typeof data.error === 'string' ? data.error : 'unavailable' };
  const fb = data.firebase;
  if (!fb || typeof fb !== 'object' || ['apiKey', 'authDomain', 'projectId', 'appId', 'messagingSenderId'].some((key) => typeof fb[key] !== 'string' || !fb[key]))
    return { error: 'web_not_configured' };
  config = data;
  return data;
}
export function serverVersion() { return config && typeof config.server_version === 'string' ? config.server_version : ''; }
/** Optional server-provided VAPID key; without one the Firebase SDK's built-in default key is used. */
export function vapidKey() {
  const value = config && config.firebase && (config.firebase.vapidKey || config.vapid_key);
  return typeof value === 'string' && value ? value : undefined;
}

/**
 * Starts Firebase Auth and finishes a pending redirect. Resolves {user, error} where error is a Korean
 * message for a redirect that came back with a failure.
 */
export async function startFirebase(onSignedOut) {
  const appModule = await import('../vendor/firebase-app.js');
  const mod = await import('../vendor/firebase-auth.js');
  const app = appModule.initializeApp({
    apiKey: config.firebase.apiKey, authDomain: config.firebase.authDomain, projectId: config.firebase.projectId,
    appId: config.firebase.appId, messagingSenderId: config.firebase.messagingSenderId,
  });
  const auth = mod.initializeAuth(app, {
    persistence: [mod.indexedDBLocalPersistence, mod.browserLocalPersistence],
    popupRedirectResolver: mod.browserPopupRedirectResolver,
  });
  auth.languageCode = 'ko';
  firebase = { app, auth, mod };
  let error = null;
  try {
    await mod.getRedirectResult(auth);
  } catch (failure) {
    error = signInMessage(failure && failure.code);
  }
  await auth.authStateReady();
  let known = auth.currentUser ? auth.currentUser.uid : null;
  mod.onAuthStateChanged(auth, (user) => {
    const uid = user ? user.uid : null;
    if (known !== null && uid !== known) onSignedOut();
    known = uid;
  });
  return { user: auth.currentUser, error };
}
export function firebaseApp() { return firebase ? firebase.app : null; }

export async function signIn() {
  const { auth, mod } = firebase;
  const provider = new mod.GoogleAuthProvider();
  provider.setCustomParameters({ prompt: 'select_account' });
  await mod.signInWithRedirect(auth, provider); // navigates away; resolves only on failure paths
}
export async function signOut() {
  if (devToken !== null) {
    devToken = null;
    try { sessionStorage.removeItem(DEV_TOKEN_KEY); } catch { /* nothing stored */ }
    return;
  }
  if (firebase) await firebase.mod.signOut(firebase.auth);
}

/** The ID token for the next API call; Firebase refreshes it when it is close to expiring. */
export async function idToken() {
  if (devToken !== null) return devToken;
  const user = firebase && firebase.auth.currentUser;
  if (!user) throw new ApiError(401, 'signed_out');
  try {
    return await user.getIdToken();
  } catch {
    throw new ApiError(0, '');
  }
}
/** Key for per-account phone settings (last home): the Firebase uid, or the dev token's subject. */
export function accountKey() {
  if (devToken !== null) {
    try {
      const payload = JSON.parse(atob(devToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
      return 'dev:' + (typeof payload.sub === 'string' ? payload.sub : '');
    } catch { return 'dev:'; }
  }
  const user = firebase && firebase.auth.currentUser;
  return user ? user.uid : '';
}
