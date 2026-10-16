// Device detail by capability blocks, and the aircon control screen that fits one phone screen.

import { actions, control, devicesReady, inventory, now, state } from '../context.js';
import { DeviceText } from '../logic/device.js';
import * as Attention from '../logic/attention.js';
import * as Timeline from '../logic/timeline.js';
import * as U from '../logic/aircon.js';
import { createDial } from '../dial.js';
import { icon } from '../icons.js';
import { button, card, h, section } from '../ui.js';
import { loadingLine } from './home.js';

const KNOWN_STATE = new Set(['contact', 'battery_percent', 'battery_low', 'temperature_c', 'humidity_percent', 'power', 'brightness_percent',
  'color_temp_k', 'power_w', 'motion', 'leak', 'smoke', 'mode', 'setpoint_c', 'fan', 'inferred']);
const KNOWN_CAPABILITIES = new Set(['contact', 'battery', 'temperature', 'humidity', 'power', 'brightness', 'color_temp', 'power_meter',
  'motion', 'leak', 'smoke', 'setpoint', 'mode', 'fan', 'actions']);

export function renderDevice(page, id) {
  if (!devicesReady()) { page.appendChild(loadingLine('기기를 확인하고 있어요…')); return; }
  const list = inventory(), device = list.find(id);
  if (!device) { page.appendChild(loadingLine('이 기기를 찾을 수 없어요')); return; }
  const time = now(), stale = device.stale(time);
  let status = stale ? DeviceText.NO_RESPONSE + ' · ' + DeviceText.duration(time - device.reportedAt)
    : device.reportedAt !== null ? DeviceText.ago(time - device.reportedAt) + ' 보고' : '';
  if (list.hubProblem(time)) status = 'Pi 연결 끊김' + (status ? ' · ' + status : '');
  if (status) page.appendChild(h('p', { class: 'status-line' + (stale ? ' warning' : '') }, status));

  const values = [];
  const contact = device.contact();
  if (contact !== null) {
    let changed = Attention.changedAt(device, state.events);
    if (changed === null) changed = device.reportedAt;
    values.push([contact === 'open' ? '열림' : '닫힘', '문' + (changed === null ? '' : ' · ' + DeviceText.ago(time - changed)), contact === 'open' ? 'danger' : '']);
  }
  const temperature = device.number('temperature_c'), humidity = device.number('humidity_percent');
  if (temperature !== null) values.push([DeviceText.number(temperature) + '°', '온도', '']);
  if (humidity !== null) values.push([DeviceText.number(humidity) + '%', '습도', '']);
  if (device.has('power') || device.capabilities.includes('power')) {
    const power = device.power();
    values.push([power === null ? '—' : power ? '켜짐' : '꺼짐', '전원', power === true ? 'accent' : '']);
  }
  const brightness = device.number('brightness_percent'), colour = device.number('color_temp_k'), watts = device.number('power_w');
  if (brightness !== null) values.push([DeviceText.number(brightness) + '%', '밝기', '']);
  if (colour !== null) values.push([DeviceText.number(colour) + 'K', '색온도', '']);
  if (watts !== null) values.push([DeviceText.number(watts) + 'W', '소비 전력', '']);
  const motion = device.flag('motion'), leak = device.flag('leak'), smoke = device.flag('smoke');
  if (motion !== null) values.push([motion ? '감지' : '없음', '움직임', motion ? 'accent' : '']);
  if (leak !== null) values.push([leak ? '감지' : '정상', '누수', leak ? 'danger' : '']);
  if (smoke !== null) values.push([smoke ? '감지' : '정상', '연기', smoke ? 'danger' : '']);
  for (let start = 0; start < values.length; start += 3) {
    page.appendChild(h('div', { class: 'card metrics' }, values.slice(start, start + 3).map(([big, label, tone]) =>
      h('div', { class: 'metric' }, h('span', { class: 'metric-value ' + tone }, big), h('span', { class: 'metric-label' }, label)))));
  }
  if (device.hasBattery()) {
    const percent = device.batteryPercent(), low = device.batteryLow();
    page.appendChild(h('div', { class: 'card battery-card' + (low ? ' low' : '') }, icon('battery', { size: 22 }),
      h('span', { class: 'battery-label' }, '배터리'),
      h('span', { class: 'battery-value' }, percent !== null ? percent + '%' + (low ? ' · 부족' : '') : low ? '부족' : '—')));
  }
  // Blocks this app does not know yet: plain name/value rows.
  const rows = [];
  for (const [key, value] of Object.entries(device.state)) if (!KNOWN_STATE.has(key)) rows.push([key, DeviceText.value(value)]);
  for (const capability of device.capabilities) if (!KNOWN_CAPABILITIES.has(capability) && !device.has(capability)) rows.push([capability, '지원']);
  if (rows.length) {
    page.appendChild(h('div', { class: 'card list-card plain-rows' }, rows.map(([key, value]) =>
      h('div', { class: 'plain-row' }, h('span', { class: 'plain-key' }, key), h('span', { class: 'plain-value' }, value)))));
  }
  page.appendChild(section('최근 기록'));
  const list2 = h('div', { class: 'card list-card records' });
  page.appendChild(list2);
  if (!state.eventsLoaded) { list2.appendChild(loadingLine(state.eventsError || '기록을 확인하고 있어요…')); return; }
  let shown = 0;
  for (const event of state.events) {
    if (shown >= 10 || !Timeline.belongsTo(event, device)) continue;
    list2.appendChild(h('div', { class: 'record' }, h('span', { class: 'record-title' }, Timeline.title(event, device.name)),
      h('span', { class: 'record-time' }, Timeline.dayLabel(event.receivedAt, time) + ' ' + Timeline.clock(event.receivedAt))));
    shown++;
  }
  if (!shown) list2.appendChild(loadingLine('아직 기록이 없어요'));
}

// ---- Aircon ----

export function airconName(id) {
  const device = devicesReady() ? inventory().find(id) : null;
  if (device) return device.name;
  const status = control(), name = status ? status.deviceName(id) : null;
  return name === null ? '에어컨' : name;
}
export function draftFor(id) {
  if (!state.drafts.has(id)) {
    let saved = null;
    try { saved = JSON.parse(sessionStorage.getItem('family-web.draft:' + id) || 'null'); } catch { saved = null; }
    state.drafts.set(id, U.Draft.restore(saved, 0));
  }
  return state.drafts.get(id);
}
function keepDraft(id, draft) {
  try { sessionStorage.setItem('family-web.draft:' + id, JSON.stringify(draft.save())); } catch { /* reload loses the draft */ }
}

/** Status line, dial with −/+, modes, fan, wrapping extras, and the pinned power/send footer. */
export function renderAircon(page, footer, id, { sending, onDragging }) {
  if (state.controlError) {
    page.appendChild(card(h('p', { class: 'card-note danger' }, state.controlError),
      button('연결 다시 확인', () => actions.loadControl(false), { kind: 'primary' })));
    return;
  }
  if (!state.controlLoaded || !state.control) { page.appendChild(loadingLine('에어컨 연결을 확인하고 있어요…')); return; }
  const status = control();
  if (!status.has(id)) {
    page.append(loadingLine('이 에어컨은 지금 조작할 수 없어요.'), button('뒤로', () => actions.back()));
    return;
  }
  const name = airconName(id), draft = draftFor(id);
  const latest = status.latestFor(id);
  const stateNow = status.latest ? status.latest.state : '';
  const enabled = U.canSend(status.canControl, status.online, stateNow) && !sending;

  // One status line: Pi connection, then this aircon's last command ("1분 전 · 냉방 24° · 전달됨").
  const parts = [];
  if (!status.canControl) parts.push('조회 전용');
  if (latest) {
    const label = U.stateLabel(latest.state);
    parts.push(DeviceText.ago(now() - latest.time()) + ' · ' + U.shortLabel(latest.action) + (label ? ' · ' + label : ''));
  }
  const problem = !!latest && U.problem(latest.state);
  const box = h('div', { class: 'aircon' });
  box.appendChild(h('div', { class: 'aircon-status' },
    h('span', { class: 'status-chip ' + (status.online ? 'online' : 'offline'), 'aria-label': status.online ? 'Pi 연결됨' : 'Pi 연결 끊김' },
      status.online ? '● 온라인' : '● 연결 끊김'),
    h('span', { class: 'aircon-summary' + (problem ? ' danger' : '') }, parts.join(' · '))));
  if (problem) box.appendChild(h('p', { class: 'aircon-why' }, U.description(latest.state, latest.action)));

  // Dial between −/+ steps. Values only change the unsent draft.
  const sync = [];
  const update = () => { keepDraft(id, draft); for (const fn of sync) fn(); };
  const down = h('button', { type: 'button', class: 'round-button', 'aria-label': '1도 내리기', on: { click: () => { draft.temperature = Math.max(U.DIAL_MIN, draft.temperature - 1); update(); } } }, icon('minus', { size: 22 }));
  const up = h('button', { type: 'button', class: 'round-button', 'aria-label': '1도 올리기', on: { click: () => { draft.temperature = Math.min(U.DIAL_MAX, draft.temperature + 1); update(); } } }, icon('add', { size: 22 }));
  const dial = createDial({ onChange: (value) => { draft.temperature = value; update(); }, onDragging });
  box.appendChild(h('div', { class: 'dial-row' }, down, h('div', { class: 'dial-box' }, dial.element), up));

  // Operating modes as round icon buttons.
  const modeButtons = U.MODES.map((label, index) => h('button', {
    type: 'button', class: 'mode', 'aria-label': label + ' 모드',
    on: { click: () => { draft.mode = index; update(); } },
  }, h('span', { class: 'mode-circle' }, icon(U.MODE_ICONS[index], { size: 22 })), h('span', { class: 'mode-label' }, label)));
  box.appendChild(h('div', { class: 'modes' }, modeButtons));

  // Cooling fan: 자동 pill plus three bars of growing height for 약·중·강.
  const auto = h('button', { type: 'button', class: 'chip fan-auto', 'aria-label': '바람 자동', on: { click: () => { draft.fan = 0; update(); } } }, '자동');
  const bars = [];
  for (let level = 1; level <= U.FAN_BARS; level++) {
    const fill = h('span', { class: 'fan-bar q' + U.fanHeightQuarters(level) });
    bars.push([level, fill, h('button', { type: 'button', class: 'fan-level', 'aria-label': '바람 ' + U.FANS[level], on: { click: () => { draft.fan = level; update(); } } },
      fill, h('span', { class: 'fan-label' }, U.FAN_SHORT[level]))]);
  }
  const fan = h('div', { class: 'fan' }, h('span', { class: 'fan-title' }, '바람'), auto, bars.map(([, , element]) => element));
  box.appendChild(fan);

  // One-shot extras: each opens the same confirmation dialog; they wrap instead of scrolling sideways.
  box.appendChild(h('div', { class: 'extras' }, U.EXTRAS.map(([label, action]) =>
    h('button', { type: 'button', class: 'chip', disabled: !enabled, on: { click: () => actions.confirmAircon(id, name, action) } }, label))));
  page.appendChild(box);

  // Pinned footer: power off and send stay reachable without scrolling.
  footer.append(
    h('button', { type: 'button', class: 'round-button power-off', 'aria-label': '에어컨 끄기', disabled: !enabled, on: { click: () => actions.confirmAircon(id, name, 'power_off') } }, icon('power', { size: 24 })),
    h('button', { type: 'button', class: 'button primary send', disabled: !enabled, on: { click: () => actions.confirmAircon(id, name, draft.action()) } }, '설정 보내기'));

  sync.push(() => {
    const cool = draft.mode === 0;
    dial.bind(cool, draft.temperature, U.MODES[draft.mode], U.dialCaption(draft.mode, draft.fan));
    down.disabled = !(cool && draft.temperature > U.DIAL_MIN);
    up.disabled = !(cool && draft.temperature < U.DIAL_MAX);
    modeButtons.forEach((element, index) => { element.classList.toggle('active', draft.mode === index); element.setAttribute('aria-pressed', String(draft.mode === index)); });
    fan.hidden = !cool;
    auto.classList.toggle('active', draft.fan === 0); auto.setAttribute('aria-pressed', String(draft.fan === 0));
    for (const [level, fill, element] of bars) {
      fill.classList.toggle('filled', U.fanFilled(level, draft.fan));
      element.classList.toggle('active', draft.fan === level); element.setAttribute('aria-pressed', String(draft.fan === level));
    }
  });
  update();
}
