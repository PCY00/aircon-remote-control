// 홈 tab and the 종류별 page: 지금 확인할 것, category chips, favorites and room sections of 3-column tiles.

import { actions, attention, control, devicesReady, favoriteIds, inventory, now, owner, state, toggleFavorite } from '../context.js';
import { DeviceCategory, DeviceText } from '../logic/device.js';
import * as Attention from '../logic/attention.js';
import { canSend } from '../logic/aircon.js';
import { icon } from '../icons.js';
import { button, card, h, section, toast } from '../ui.js';

export function loadingLine(text) { return h('p', { class: 'muted-line' }, text); }

export function renderHome(page) {
  if (!state.house) { page.appendChild(homeLoading()); return; }
  if (!devicesReady()) { page.appendChild(loadingLine('기기를 확인하고 있어요…')); return; }
  const time = now(), devices = inventory().devices;
  const items = attention();
  if (items.length) page.append(section('지금 확인할 것'), attentionList(items));
  if (!devices.length) {
    page.appendChild(card(h('p', { class: 'card-title' }, '아직 연결된 기기가 없어요'),
      owner() ? h('p', { class: 'card-note' }, 'Pi 허브 연결은 Android 앱에서 해요.') : null));
    return;
  }
  page.append(section('종류별 모아보기'), categoryChips(devices));
  const favorites = favoriteIds();
  const favoriteDevices = devices.filter((device) => favorites.includes(device.id));
  if (favoriteDevices.length) page.append(section('즐겨찾기'), grid(favoriteDevices, time));
  for (const [room, members] of DeviceText.rooms(devices)) page.append(roomHeader(room, members), grid(members, time));
}

export function renderCategory(page, key) {
  if (!devicesReady()) { page.appendChild(loadingLine('기기를 확인하고 있어요…')); return; }
  const members = DeviceCategory.members(inventory().devices, key);
  if (!members.length) { page.appendChild(loadingLine('이 종류의 기기가 없어요')); return; }
  const time = now();
  for (const [room, devices] of DeviceText.rooms(members)) page.append(roomHeader(room, devices), grid(devices, time));
}

export function homeLoading() {
  if (!state.houseError) return loadingLine('우리 집을 확인하고 있어요…');
  return card(h('p', { class: 'card-title' }, '우리 집을 불러오지 못했어요'), h('p', { class: 'card-note' }, state.houseError),
    button('다시 연결', () => actions.refresh(), { kind: 'primary' }));
}

const TONE = { danger: 'tone-danger', warning: 'tone-warning', neutral: 'tone-neutral' };

export function attentionList(items) {
  const box = h('div', { class: 'card list-card' });
  for (const item of items) {
    box.appendChild(h('button', { type: 'button', class: 'attention ' + TONE[item.tone], on: { click: () => openAttention(item) } },
      h('span', { class: 'badge' }, icon(Attention.iconOf(item), { size: 18 })),
      h('span', { class: 'attention-texts' }, h('span', { class: 'attention-title' }, item.title),
        item.detail ? h('span', { class: 'attention-detail' }, item.detail) : null),
      h('span', { class: 'row-chevron' }, icon('chevron', { size: 18 }))));
  }
  return box;
}
function openAttention(item) {
  if (item.deviceId) {
    const device = devicesReady() ? inventory().find(item.deviceId) : null;
    if (device) { actions.open(device.aircon() ? 'aircon' : 'device', device.id); return; }
    const status = control();
    if (status && status.has(item.deviceId)) { actions.open('aircon', item.deviceId); return; }
  }
  actions.tab('alerts');
}

function categoryChips(devices) {
  const strip = h('div', { class: 'chip-strip category-strip' });
  for (const key of DeviceCategory.present(devices)) {
    strip.appendChild(h('button', { type: 'button', class: 'category-chip', on: { click: () => actions.open('category', key) } },
      h('span', { class: 'category-head' }, icon(DeviceCategory.icon(key), { size: 20, className: 'accent' }), h('span', { class: 'category-label' }, DeviceCategory.label(key))),
      h('span', { class: 'category-summary' }, DeviceText.category(key, devices))));
  }
  return strip;
}

export function roomHeader(room, devices) {
  const climate = DeviceText.roomClimate(devices);
  return h('div', { class: 'room-head' }, h('h2', { class: 'room-name' }, DeviceText.roomLabel(room)),
    climate ? h('span', { class: 'room-climate' }, icon('thermometer', { size: 16 }), climate) : null);
}

export function grid(devices, time) {
  const box = h('div', { class: 'grid' });
  for (const device of devices) box.appendChild(tile(device, time));
  return box;
}

function tile(device, time) {
  const stale = device.stale(time), open = device.contact() === 'open', on = device.on();
  const summary = DeviceText.tile(device, time, Attention.changedAt(device, state.events));
  const element = h('div', {
    class: 'tile' + (stale ? ' stale' : ''), role: 'button', tabindex: '0',
    'aria-label': device.shortName() + ', ' + summary,
  });
  const head = h('div', { class: 'tile-head' },
    icon(DeviceCategory.typeIcon(device.type), { size: 24, className: open ? 'danger' : on ? 'accent' : '' }),
    h('span', { class: 'spacer' }),
    device.batteryLow() ? h('span', { class: 'tile-battery', role: 'img', 'aria-label': '배터리 부족' }, icon('battery', { size: 18 })) : null);
  if (device.aircon()) {
    head.appendChild(h('button', {
      type: 'button', class: 'tile-power' + (on ? ' on' : ''), 'aria-label': on ? '에어컨 끄기' : '에어컨 조작 열기',
      on: { click: (event) => { event.stopPropagation(); airconPower(device); } },
    }, icon('power', { size: 18 })));
  }
  element.append(head, h('span', { class: 'tile-name' }, device.shortName()),
    h('span', { class: 'tile-value' + (open && !stale ? ' danger' : '') }, summary));
  const openIt = () => actions.open(device.aircon() ? 'aircon' : 'device', device.id);
  longPress(element, () => {
    const added = toggleFavorite(device.id);
    toast(added ? '즐겨찾기에 추가했어요.' : '즐겨찾기에서 뺐어요.');
    actions.render();
  }, openIt);
  element.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openIt(); } });
  return element;
}

/** Long press (0.55 s) toggles the favorite; a short tap opens the device. */
function longPress(element, onLong, onTap) {
  let timer = 0, fired = false, startX = 0, startY = 0, active = false;
  const cancel = () => { clearTimeout(timer); active = false; };
  element.addEventListener('pointerdown', (event) => {
    if (event.target.closest('.tile-power')) return;
    fired = false; active = true; startX = event.clientX; startY = event.clientY;
    timer = setTimeout(() => { if (active) { fired = true; active = false; onLong(); } }, 550);
  });
  element.addEventListener('pointermove', (event) => { if (active && Math.hypot(event.clientX - startX, event.clientY - startY) > 10) cancel(); });
  element.addEventListener('pointerup', cancel);
  element.addEventListener('pointercancel', cancel);
  element.addEventListener('pointerleave', cancel);
  element.addEventListener('contextmenu', (event) => event.preventDefault());
  element.addEventListener('click', (event) => {
    if (event.target.closest('.tile-power')) return;
    if (fired) { fired = false; return; }
    onTap();
  });
}

/** On (as far as the last command tells): confirm and send power_off. Off or unknown: open the control screen. */
function airconPower(device) {
  const status = control();
  const latest = status && status.latest ? status.latest.state : '';
  if (device.on() && status && status.has(device.id) && canSend(status.canControl, status.online, latest))
    actions.confirmAircon(device.id, device.name, 'power_off');
  else actions.open('aircon', device.id);
}
