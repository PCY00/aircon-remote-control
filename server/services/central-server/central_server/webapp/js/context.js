// Shared screen state and derived values. app.js fills `actions` (navigation and loading) so the view
// modules can call them without importing app.js.

import { ControlStatus, Inventory } from './logic/device.js';
import * as Attention from './logic/attention.js';
import { favoritesKey, toggled } from './logic/homes.js';
import { readJson, writeJson } from './store.js';

export const state = {
  dev: false,
  account: '',
  homes: null, homesError: null,
  homeId: null,
  house: null, houseError: null,
  serverInventory: null, devicesLoaded: false,
  events: [], eventsLoaded: false, eventsError: null,
  control: null, controlLoaded: false, controlError: null,
  drafts: new Map(),
  eventFilter: 'all',
  expanded: new Set(),
  /** Bumped whenever the account or home changes: older answers are dropped. */
  generation: 0,
  lastSync: 0,
};

export const actions = {};

export function now() { return Date.now() / 1000; }
export function control() { return state.control ? ControlStatus.from(state.control) : null; }
/** The fallback list needs the aircon control list, so it waits for that answer. */
export function devicesReady() {
  if (!state.devicesLoaded) return false;
  if (state.serverInventory && !state.serverInventory.neverReported()) return true;
  return state.controlLoaded;
}
export function inventory() { return Inventory.effective(state.serverInventory, control(), state.events); }
export function attention() { return devicesReady() ? Attention.compute(inventory(), state.events, control(), now()) : []; }
export function owner() { return !!state.house && state.house.role === 'owner'; }
export function role() { return state.house ? state.house.role : ''; }

export function clearHomeData() {
  Object.assign(state, {
    house: null, houseError: null, serverInventory: null, devicesLoaded: false, events: [], eventsLoaded: false, eventsError: null,
    control: null, controlLoaded: false, controlError: null, eventFilter: 'all', lastSync: 0,
  });
  state.drafts.clear();
  state.expanded.clear();
}

export function favoriteIds() {
  const ids = readJson(favoritesKey(state.homeId), []);
  return Array.isArray(ids) ? ids.filter((id) => typeof id === 'string') : [];
}
export function isFavorite(id) { return favoriteIds().includes(id); }
/** Toggles a favorite on this phone only; returns true when it was added. */
export function toggleFavorite(id) {
  const result = toggled(favoriteIds(), id);
  writeJson(favoritesKey(state.homeId), result.ids);
  return result.added;
}
