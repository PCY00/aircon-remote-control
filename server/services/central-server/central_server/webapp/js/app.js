// Family smart-home web app (home-screen PWA). Same API and screen rules as the Android family app 0.6.2:
// sign-in, homes, 홈/알림/설정 tabs, device and aircon screens with hash routing so back gestures work.

import { actions, attention, clearHomeData, control, devicesReady, inventory, isFavorite, state, toggleFavorite } from './context.js';
import { api, path, setTokenProvider } from './api.js';
import * as auth from './auth.js';
import * as push from './push.js';
import { AppEvent, DeviceCategory, DeviceText, Inventory } from './logic/device.js';
import { ApiError, describe, homeGone } from './logic/errors.js';
import { chooseHome, homeList, lastHomeKey, roleLabel } from './logic/homes.js';
import { CommandPoll, LOST_RESULT, NOT_RESENT, NOT_SENDABLE, canSend, confirmation, pending } from './logic/aircon.js';
import { requestId } from './logic/ids.js';
import { isDevHost, withoutDevToken } from './logic/dev.js';
import { readJson, remove, writeJson } from './store.js';
import { icon } from './icons.js';
import { clear, confirmDialog, h, iconButton, inputSheet, sheet, toast } from './ui.js';
import { renderCategory, renderHome } from './views/home.js';
import { airconName, renderAircon, renderDevice } from './views/device.js';
import { renderAlerts } from './views/alerts.js';
import { renderSettings } from './views/settings.js';
import { renderConfigError, renderLoading, renderLogin, renderOnboarding, renderStart } from './views/start.js';

const root = document.getElementById('app');
/** loading | config | login | start | onboarding | ready */
let boot = 'loading';
let configError = '', loginError = '', signingIn = false;
let screenEpoch = 0, routeKey = '';
let sending = false, dialDragging = false, deferred = false, confirmOpen = false, resumePoll = false;
const scrollPositions = new Map();
const poll = new CommandPoll();

// ---- Routing (hash) ----

const TABS = ['home', 'alerts', 'settings'];
function route() {
  const [name, ...rest] = location.hash.replace(/^#/, '').split('/');
  let arg = '';
  try { arg = decodeURIComponent(rest.join('/')); } catch { arg = ''; }
  if (TABS.includes(name)) return { name, arg: '' };
  if (['device', 'aircon', 'category'].includes(name) && arg) return { name, arg };
  return { name: 'home', arg: '' };
}
function depth() { return history.state && Number.isInteger(history.state.depth) ? history.state.depth : 0; }
function onRoute() {
  // A token pasted into the address bar of an open app never stays visible there.
  if (location.hash.includes('dev-token=')) history.replaceState(history.state, '', location.pathname + location.search + withoutDevToken(location.hash));
  screenEpoch++;
  render();
  if (boot === 'ready') syncHome({ quiet: true });
}
actions.open = (name, arg) => { history.pushState({ depth: depth() + 1 }, '', '#' + name + '/' + encodeURIComponent(arg)); onRoute(); };
actions.tab = (name) => { history.replaceState({ depth: 0 }, '', '#' + name); onRoute(); };
actions.back = () => {
  if (depth() > 0) history.back();
  else { history.replaceState({ depth: 0 }, '', '#home'); onRoute(); }
};

// ---- Rendering ----

function focusedInput() {
  const active = document.activeElement;
  if (!active || !root.contains(active)) return false;
  // Redrawing would close the open time picker or keyboard; switches and buttons redraw at once.
  if (active.tagName === 'INPUT') return !['checkbox', 'radio', 'button', 'submit'].includes(active.type);
  return active.tagName === 'SELECT' || active.tagName === 'TEXTAREA';
}
function render() {
  if (dialDragging || focusedInput()) { deferred = true; return; }
  deferred = false;
  const oldPage = root.querySelector('.page');
  if (oldPage && routeKey) scrollPositions.set(routeKey, oldPage.scrollTop);
  const view = currentView();
  routeKey = view.key;
  const page = h('main', { class: 'page', id: 'page' });
  const footer = view.footer ? h('div', { class: 'pinned' }) : null;
  if (state.dev && !view.bare) page.appendChild(h('p', { class: 'dev-badge' }, '개발 모드'));
  view.fill(page, footer);
  const screen = h('div', { class: 'screen' + (view.bare ? ' bare' : '') + (view.tabs ? ' with-tabs' : '') + (footer ? ' with-footer' : '') },
    view.bare ? null : header(view), page, footer, view.tabs ? tabBar(view.tab) : null);
  clear(root).appendChild(screen);
  page.scrollTop = scrollPositions.get(view.key) || 0;
  document.title = view.documentTitle || '가족 스마트홈';
}
actions.render = render;
document.addEventListener('focusout', () => setTimeout(() => { if (deferred && !focusedInput()) render(); }, 0));

function currentView() {
  switch (boot) {
    case 'loading': return { key: 'loading', bare: true, fill: renderLoading };
    case 'config': return { key: 'config', bare: true, fill: (page) => renderConfigError(page, configError) };
    case 'login': return { key: 'login', bare: true, fill: (page) => renderLogin(page, { error: loginError, signingIn }) };
    case 'start': return { key: 'start', bare: true, fill: renderStart };
    case 'onboarding': return { key: 'onboarding', bare: true, fill: renderOnboarding };
    default: break;
  }
  const { name, arg } = route();
  const key = name + ':' + state.homeId + ':' + arg;
  if (name === 'alerts') return { key, tabs: true, tab: name, title: '알림', actions: [iconButton('refresh', '알림 새로고침', () => actions.refresh())], fill: renderAlerts };
  if (name === 'settings') return { key, tabs: true, tab: name, title: '설정', fill: renderSettings };
  if (name === 'category') {
    return { key, back: true, title: DeviceCategory.label(arg), subtitle: devicesReady() ? DeviceText.category(arg, inventory().devices) : '', fill: (page) => renderCategory(page, arg) };
  }
  if (name === 'device' || name === 'aircon') {
    const device = devicesReady() ? inventory().find(arg) : null;
    const aircon = name === 'aircon' || (device && device.aircon());
    const title = device ? device.name : aircon ? airconName(arg) : '기기';
    return {
      key: (aircon ? 'aircon:' : 'device:') + state.homeId + ':' + arg, back: true, title, subtitle: device ? device.room : '',
      actions: [favoriteButton(arg)], documentTitle: title, footer: aircon,
      fill: aircon ? (page, footer) => renderAircon(page, footer, arg, { sending, onDragging }) : (page) => renderDevice(page, arg),
    };
  }
  const count = attention().length;
  return {
    key, tabs: true, tab: 'home', homeSwitch: true, title: state.house ? state.house.name : '우리 집',
    actions: [iconButton('refresh', '집 새로고침', () => actions.refresh()), bell(count)], fill: renderHome,
  };
}
function onDragging(value) {
  dialDragging = value;
  if (!value && deferred) setTimeout(render, 0);
}
function header(view) {
  const title = view.homeSwitch
    ? h('button', { type: 'button', class: 'home-switch', 'aria-label': view.title + ', 집 바꾸기', on: { click: () => actions.switcher() } },
      h('span', { class: 'home-name' }, view.title), icon('expand', { size: 20 }))
    : h('div', { class: 'titles' + (view.back ? ' detail' : '') }, h('h1', { class: 'title' }, view.title), view.subtitle ? h('p', { class: 'subtitle' }, view.subtitle) : null);
  return h('header', { class: 'bar' }, view.back ? iconButton('back', '뒤로', () => actions.back()) : null, title,
    h('div', { class: 'bar-actions' }, view.actions || []));
}
function bell(count) {
  return h('button', { type: 'button', class: 'icon-button bell', 'aria-label': count ? '알림, 확인할 것 ' + count + '개' : '알림', on: { click: () => actions.tab('alerts') } },
    icon('bell', { size: 22 }), count ? h('span', { class: 'bell-count', 'aria-hidden': 'true' }, count > 99 ? '99+' : String(count)) : null);
}
function favoriteButton(id) {
  const on = isFavorite(id);
  return h('button', {
    type: 'button', class: 'icon-button star' + (on ? ' on' : ''), 'aria-label': on ? '즐겨찾기에서 빼기' : '즐겨찾기에 추가', 'aria-pressed': String(on),
    on: { click: () => { const added = toggleFavorite(id); toast(added ? '즐겨찾기에 추가했어요.' : '즐겨찾기에서 뺐어요.'); render(); } },
  }, icon('star', { size: 22, filled: on }));
}
function tabBar(active) {
  const items = [['home', '홈', 'home'], ['alerts', '알림', 'bell'], ['settings', '설정', 'settings']];
  return h('nav', { class: 'tabs', 'aria-label': '탭' }, items.map(([name, label, iconName]) => h('button', {
    type: 'button', class: 'tab' + (name === active ? ' active' : ''), 'aria-current': name === active ? 'page' : null,
    on: { click: () => { if (name !== active) actions.tab(name); } },
  }, h('span', { class: 'tab-pill' }, icon(iconName, { size: 22 })), h('span', { class: 'tab-label' }, label))));
}

// ---- Homes ----

actions.start = async function start() {
  boot = 'start';
  state.generation++;
  state.homes = null; state.homesError = null; state.homeId = null;
  clearHomeData();
  render();
  const generation = state.generation;
  try {
    const homes = homeList(await api('GET', '/v1/homes'));
    if (generation !== state.generation) return;
    state.homes = homes;
    const chosen = chooseHome(homes, readJson(lastHomeKey(state.account), null));
    if (!chosen) { boot = 'onboarding'; render(); return; }
    enterHome(chosen, { keepRoute: true });
  } catch (failure) {
    if (generation !== state.generation) return;
    state.homesError = describe(failure);
    render();
  }
};
function enterHome(id, { keepRoute = false } = {}) {
  if (id !== state.homeId) { clearHomeData(); state.generation++; }
  state.homeId = id;
  writeJson(lastHomeKey(state.account), id);
  boot = 'ready';
  if (!keepRoute) history.replaceState({ depth: 0 }, '', '#home');
  onRoute();
}
function leaveHome(message) {
  if (readJson(lastHomeKey(state.account), null) === state.homeId) remove(lastHomeKey(state.account));
  actions.start();
  if (message) toast(message);
}
actions.switcher = async function switcher() {
  let homes = state.homes || [];
  try {
    homes = homeList(await api('GET', '/v1/homes'));
    state.homes = homes;
  } catch (failure) {
    if (!homes.length) { toast(describe(failure)); return; }
  }
  sheet('집 바꾸기', (panel, close) => {
    const list = h('div', { class: 'options' });
    for (const home of homes) {
      const current = home.id === state.homeId;
      list.appendChild(h('button', { type: 'button', class: 'option' + (current ? ' selected' : ''), 'aria-current': current ? 'true' : null,
        on: { click: () => { close(); if (!current) enterHome(home.id); } } },
      h('span', { class: 'option-icon' }, icon('home', { size: 22 })),
      h('span', { class: 'option-texts' }, h('span', { class: 'option-label' }, home.name), h('span', { class: 'option-meaning' }, roleLabel(home.role))),
      current ? icon('check', { size: 20, className: 'accent' }) : null));
    }
    list.appendChild(h('hr', { class: 'divider' }));
    list.appendChild(h('button', { type: 'button', class: 'option', on: { click: () => { close(); actions.createHome(); } } },
      h('span', { class: 'option-icon' }, icon('add', { size: 22 })), h('span', { class: 'option-texts' }, h('span', { class: 'option-label' }, '새 집 만들기'))));
    list.appendChild(h('button', { type: 'button', class: 'option', on: { click: () => { close(); actions.acceptInvitation(); } } },
      h('span', { class: 'option-icon' }, icon('family', { size: 22 })), h('span', { class: 'option-texts' }, h('span', { class: 'option-label' }, '초대 코드로 참여'))));
    panel.appendChild(list);
  });
};
actions.createHome = async function createHome() {
  const name = await inputSheet({ title: '새 집 만들기', placeholder: '예: 우리 집', maxLength: 80 });
  if (!name) return;
  try {
    const reply = await api('POST', '/v1/homes', { name });
    if (typeof reply.id === 'string') enterHome(reply.id);
  } catch (failure) { toast(describe(failure)); }
};
actions.acceptInvitation = async function acceptInvitation() {
  const token = await inputSheet({ title: '초대 코드로 참여', placeholder: '가족에게 받은 초대 코드', maxLength: 128 });
  if (!token) return;
  try {
    const reply = await api('POST', '/v1/invitations/accept', { invitation_token: token });
    if (typeof reply.home_id === 'string') enterHome(reply.home_id);
  } catch (failure) { toast(describe(failure)); }
};

// ---- Home data: house, devices, records and aircon status (in parallel; each answer redraws) ----

async function syncHome({ quiet }) {
  const home = state.homeId, generation = state.generation;
  if (!home) return;
  state.lastSync = Date.now() / 1000;
  const alive = () => generation === state.generation && home === state.homeId;
  const failed = (failure) => {
    if (!alive()) return true;
    if (homeGone(failure)) { leaveHome(describe(failure)); return true; }
    return false;
  };
  await Promise.allSettled([
    api('GET', path('homes', home)).then((house) => {
      if (!alive()) return;
      state.house = { id: house.id, name: typeof house.name === 'string' ? house.name : '우리 집', role: house.role };
      state.houseError = null; render();
    }, (failure) => {
      if (failed(failure)) return;
      if (!quiet) toast(describe(failure));
      if (!state.house) { state.houseError = describe(failure); render(); }
    }),
    api('GET', path('homes', home, 'devices')).then((reply) => {
      if (!alive()) return;
      state.serverInventory = Inventory.from(reply); state.devicesLoaded = true; render();
    }, (failure) => {
      if (failed(failure)) return;
      // 404: a server older than 0.7 has no device list; the screens build one from control and records.
      state.serverInventory = null; state.devicesLoaded = true;
      if (!quiet && failure.status !== 404) toast(describe(failure));
      render();
    }),
    api('GET', path('homes', home, 'events')).then((reply) => {
      if (!alive()) return;
      state.events = AppEvent.list(reply.events); state.eventsLoaded = true; state.eventsError = null; render();
    }, (failure) => {
      if (failed(failure)) return;
      state.eventsError = describe(failure);
      if (!quiet) toast(describe(failure));
      render();
    }),
    loadControl(quiet),
  ]);
}
actions.refresh = () => syncHome({ quiet: false });

async function loadControl(quiet) {
  const home = state.homeId, generation = state.generation, epoch = screenEpoch;
  if (!home) return;
  try {
    const reply = await api('GET', path('homes', home, 'control'));
    if (generation !== state.generation || home !== state.homeId) return;
    state.control = reply; state.controlLoaded = true; state.controlError = null;
    render();
    const latest = reply.latest_command;
    if (latest && typeof latest.id === 'string' && pending(latest.state)) pollCommand(home, latest.id, epoch, 0);
  } catch (failure) {
    if (generation !== state.generation || home !== state.homeId) return;
    if (homeGone(failure)) { leaveHome(describe(failure)); return; }
    state.controlLoaded = true; state.controlError = describe(failure);
    if (!quiet) toast(describe(failure));
    render();
  }
}
actions.loadControl = loadControl;

// ---- Aircon commands ----

function sendable() {
  const status = control();
  return !!status && canSend(status.canControl, status.online, status.latest ? status.latest.state : '');
}
actions.confirmAircon = async function confirmAircon(device, name, action) {
  // A double tap must not stack two dialogs that each send their own command.
  if (confirmOpen) return;
  confirmOpen = true;
  const home = state.homeId;
  const ok = await confirmDialog('명령을 보낼까요?', name + '\n' + confirmation(action), '보내기');
  confirmOpen = false;
  if (!ok || home !== state.homeId || boot !== 'ready') return;
  if (sending || !sendable()) { toast(NOT_SENDABLE); return; }
  sending = true; render();
  const id = requestId((bytes) => crypto.getRandomValues(bytes));
  try {
    const reply = await api('POST', path('homes', home, 'control', 'commands'), { request_id: id, device_id: device, action });
    sending = false;
    if (home !== state.homeId) return;
    state.control = { ...state.control, latest_command: reply };
    render();
    pollCommand(home, typeof reply.id === 'string' ? reply.id : id, screenEpoch, 0);
  } catch (failure) {
    sending = false;
    toast(describe(failure) + NOT_RESENT);
    loadControl(true);
  }
};
function pollCommand(home, id, epoch, attempt) {
  if (attempt === 0 && !poll.start(id, epoch)) return;
  if (!poll.active(id, epoch)) return;
  if (document.hidden) { poll.cancel(); resumePoll = true; return; }
  if (attempt >= CommandPoll.MAX_ATTEMPTS) { poll.finish(id); state.controlError = LOST_RESULT; render(); return; }
  setTimeout(async () => {
    if (!poll.active(id, epoch)) return;
    if (epoch !== screenEpoch || home !== state.homeId || boot !== 'ready') { poll.finish(id); return; }
    try {
      const reply = await api('GET', path('homes', home, 'control', 'commands', id));
      if (!poll.active(id, epoch)) return;
      const latest = state.control ? state.control.latest_command : null;
      if (!state.control || !CommandPoll.current(latest && latest.id, id)) { poll.finish(id); return; }
      const changed = !latest || reply.state !== latest.state;
      state.control = { ...state.control, latest_command: reply };
      // Redraw only on a state change so a dial drag is not interrupted every tick.
      if (changed) render();
      if (pending(reply.state)) pollCommand(home, id, epoch, attempt + 1); else poll.finish(id);
    } catch (failure) {
      if (!poll.active(id, epoch)) return;
      if (failure instanceof ApiError && !CommandPoll.retryable(failure.status)) {
        poll.finish(id); state.controlError = describe(failure); render(); return;
      }
      pollCommand(home, id, epoch, attempt + 1);
    }
  }, CommandPoll.INTERVAL_MS);
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) { if (poll.cancel()) resumePoll = true; return; }
  if (boot !== 'ready') return;
  if (resumePoll) { resumePoll = false; loadControl(true); }
  if (Date.now() / 1000 - state.lastSync > 30) syncHome({ quiet: true });
});

// ---- Account ----

actions.signIn = async function signIn() {
  if (signingIn) return;
  signingIn = true; loginError = ''; render();
  try {
    await auth.signIn();
  } catch (failure) {
    signingIn = false;
    loginError = '로그인을 시작하지 못했어요. 잠시 후 다시 시도해 주세요.';
    render();
  }
};
let loggingOut = false;
actions.logout = async function logout() {
  if (loggingOut) return;
  loggingOut = true;
  try {
    await push.signOutCleanup(); // needs the ID token, so before signing out
    const dev = state.dev;
    await auth.signOut();
    signedOut();
    if (dev) location.replace(location.pathname);
  } finally {
    loggingOut = false;
  }
};
function signedOut() {
  state.generation++;
  state.account = ''; state.homeId = null; state.homes = null; state.homesError = null; state.dev = false;
  clearHomeData();
  boot = 'login'; signingIn = false;
  history.replaceState({ depth: 0 }, '', location.pathname + location.search);
  render();
}

// ---- Start ----

async function init() {
  window.addEventListener('popstate', onRoute);
  // Coming back from the Google page with the back gesture restores this page from memory.
  window.addEventListener('pageshow', (event) => { if (event.persisted && signingIn) { signingIn = false; render(); } });
  push.onChange(() => { if (boot === 'ready' && route().name === 'settings') render(); });
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', (event) => {
      if (event.data && event.data.type === 'open' && event.data.route === 'alerts' && boot === 'ready') actions.tab('alerts');
    });
  }
  setTokenProvider(auth.idToken);
  render();
  if (auth.detectDevToken()) {
    state.dev = true;
    state.account = auth.accountKey();
    await push.ready();
    actions.start();
    return;
  }
  // The worker caches the app shell and receives pushes; not used for local development hosts.
  if ('serviceWorker' in navigator && !isDevHost(location.hostname)) push.registerWorker().catch(() => {});
  const config = await auth.loadConfig();
  if (config.error) { boot = 'config'; configError = config.error; render(); return; }
  let result;
  try {
    // Signed out elsewhere (revoked or expired session): back to the sign-in screen.
    result = await auth.startFirebase(() => { if (!loggingOut && boot !== 'login') { signedOut(); toast('로그인을 확인할 수 없어요. 다시 로그인해 주세요.'); } });
  } catch {
    boot = 'login'; loginError = '로그인 준비를 마치지 못했어요. 잠시 후 다시 시도해 주세요.'; render(); return;
  }
  await push.ready();
  if (!result.user) { boot = 'login'; loginError = result.error || ''; render(); return; }
  state.account = result.user.uid;
  actions.start();
  // The FCM token may have rotated since the last start; re-register quietly when this phone receives.
  push.sync(state.account).then(() => { if (boot === 'ready' && route().name === 'settings') render(); });
}

init();
