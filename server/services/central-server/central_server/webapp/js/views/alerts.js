// 알림 tab: category chips, 해결 안 됨, and the day-grouped record list with collapsed repeats.

import { actions, attention, devicesReady, inventory, now, state } from '../context.js';
import * as A from '../logic/alerts.js';
import * as Attention from '../logic/attention.js';
import * as Timeline from '../logic/timeline.js';
import * as push from '../push.js';
import { icon } from '../icons.js';
import { button, card, h, section } from '../ui.js';
import { attentionList, homeLoading, loadingLine } from './home.js';

export function renderAlerts(page) {
  if (!state.house && state.houseError) { page.appendChild(homeLoading()); return; }
  const time = now(), ready = devicesReady();
  const list = ready ? inventory() : null;
  const items = attention();
  const names = list ? list.names() : new Map();
  const levels = push.levels();
  const present = new Set([...state.events.map((event) => event.alertCategory()), ...items.map((item) => item.category)]);
  if (state.eventFilter !== 'all' && !present.has(state.eventFilter)) state.eventFilter = 'all';

  const chips = h('div', { class: 'chip-strip filter-strip', role: 'toolbar', 'aria-label': '알림 종류' });
  const chip = (label, key) => h('button', {
    type: 'button', class: 'chip' + (state.eventFilter === key ? ' active' : ''), 'aria-pressed': String(state.eventFilter === key),
    on: { click: () => { state.eventFilter = key; state.expanded.clear(); actions.render(); } },
  }, label);
  chips.appendChild(chip('전체', 'all'));
  for (const category of A.FILTERS) if (present.has(category)) chips.appendChild(chip(A.label(category), category));
  page.appendChild(chips);

  const open = Attention.filter(items, state.eventFilter);
  if (open.length) page.append(section('해결 안 됨'), attentionList(open));
  if (!state.eventsLoaded) {
    if (state.eventsError) page.appendChild(card(h('p', { class: 'card-note' }, state.eventsError), button('다시 확인', () => actions.refresh())));
    else page.appendChild(loadingLine('기록을 확인하고 있어요…'));
    return;
  }
  const visible = [];
  let hidden = 0;
  for (const event of state.events) {
    const category = event.alertCategory();
    if (state.eventFilter === 'all') { if (A.showsInAll(category, levels[category])) visible.push(event); else hidden++; }
    else if (category === state.eventFilter) visible.push(event);
  }
  if (!visible.length) {
    page.appendChild(card(h('p', { class: 'card-title' }, state.eventFilter === 'all' ? '아직 도착한 기록이 없어요' : '이 종류의 기록은 아직 없어요')));
  }
  for (const day of Timeline.build(visible, names, undefined, time)) {
    page.append(section(day.label), h('div', { class: 'card list-card timeline' }, day.rows.map((row) => timelineRow(row, names, list))));
  }
  if (hidden) page.appendChild(h('p', { class: 'footnote' }, '끔으로 둔 종류의 기록 ' + hidden + '개는 숨겼어요'));
}

function timelineRow(row, names, list) {
  const first = row.newest(), category = first.alertCategory();
  const tint = category === A.SAFETY || category === A.AUTOMATION ? 'warning' : category === A.OTHER ? 'muted' : 'accent';
  const collapsible = row.count() > 1, key = row.key(), expanded = collapsible && state.expanded.has(key);
  const head = [
    h('span', { class: 'timeline-icon ' + tint }, icon(Timeline.icon(category), { size: 21 })),
    h('span', { class: 'timeline-texts' }, h('span', { class: 'timeline-title' }, Timeline.rowTitle(row, names)),
      h('span', { class: 'timeline-time' }, Timeline.rowTime(row))),
    collapsible ? h('span', { class: 'row-chevron' }, icon(expanded ? 'collapse' : 'expand', { size: 18 })) : null,
  ];
  const device = !collapsible && list ? list.find(first.deviceId) : null;
  if (collapsible) {
    const entry = h('div', { class: 'timeline-entry' },
      h('button', { type: 'button', class: 'timeline-row', 'aria-expanded': String(expanded),
        on: { click: () => { if (!state.expanded.delete(key)) state.expanded.add(key); actions.render(); } } }, head));
    if (expanded) {
      entry.appendChild(h('ul', { class: 'timeline-items' }, row.events.map((event) =>
        h('li', null, h('span', { class: 'timeline-clock' }, Timeline.clock(event.receivedAt)), Timeline.title(event, Timeline.nameOf(event, names))))));
    }
    return entry;
  }
  if (device) {
    return h('button', { type: 'button', class: 'timeline-row', on: { click: () => actions.open(device.aircon() ? 'aircon' : 'device', device.id) } }, head);
  }
  return h('div', { class: 'timeline-row' }, head);
}
