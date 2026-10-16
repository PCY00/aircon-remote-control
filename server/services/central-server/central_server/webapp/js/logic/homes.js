// Home list rules: role names, the last-used home per account and per-home favorites keys.

export const WEB_VERSION = '0.8.0';

export function roleLabel(role) { return role === 'owner' ? '소유자' : role === 'member' ? '가족' : '조회 전용'; }

/** Valid {id, name, role} entries of GET /v1/homes, in the server's order. */
export function homeList(raw) {
  const homes = raw && Array.isArray(raw.homes) ? raw.homes : [];
  return homes.filter((home) => home && typeof home.id === 'string' && home.id !== '' && typeof home.name === 'string')
    .map((home) => ({ id: home.id, name: home.name, role: typeof home.role === 'string' ? home.role : 'viewer' }));
}
/** The last-used home when it is still listed, else the first one, else null (onboarding). */
export function chooseHome(homes, last) {
  if (!homes.length) return null;
  return homes.some((home) => home.id === last) ? last : homes[0].id;
}
export function lastHomeKey(account) { return 'family-web.last-home:' + (account || ''); }
export function favoritesKey(home) { return 'family-web.favorites:' + (home || ''); }
export function toggled(ids, id) {
  const set = new Set(ids);
  const added = !set.delete(id);
  if (added) set.add(id);
  return { ids: [...set], added };
}
