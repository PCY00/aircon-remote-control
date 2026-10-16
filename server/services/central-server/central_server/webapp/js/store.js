// Phone-local storage. Small preferences (last home, favorites, levels, quiet hours) use localStorage;
// the push installation record (id and secret) uses IndexedDB and falls back to localStorage.
// Every access is wrapped: private browsing or blocked storage must not break the screens.

export function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch { return fallback; }
}
export function writeJson(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; }
}
export function remove(key) { try { localStorage.removeItem(key); } catch { /* storage unavailable */ } }

const DB = 'family-web', STORE = 'kv', FALLBACK = 'family-web.kv.';
let dbPromise = null;
function database() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve) => {
      try {
        const request = indexedDB.open(DB, 1);
        request.onupgradeneeded = () => request.result.createObjectStore(STORE);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => resolve(null);
        request.onblocked = () => resolve(null);
      } catch { resolve(null); }
    });
  }
  return dbPromise;
}
function transaction(db, mode, run) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const result = run(tx.objectStore(STORE));
    tx.oncomplete = () => resolve(result.result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}
export async function kvGet(key) {
  const db = await database();
  if (db) { try { const value = await transaction(db, 'readonly', (store) => store.get(key)); if (value !== undefined) return value; } catch { /* fall back */ } }
  return readJson(FALLBACK + key, undefined);
}
export async function kvSet(key, value) {
  const db = await database();
  if (db) {
    try { await transaction(db, 'readwrite', (store) => store.put(value, key)); remove(FALLBACK + key); return; } catch { /* fall back */ }
  }
  writeJson(FALLBACK + key, value);
}
