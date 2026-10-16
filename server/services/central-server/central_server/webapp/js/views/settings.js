// 설정 tab: this phone's notifications, levels per category, report interval, quiet hours, home, account.

import { actions, owner, state } from '../context.js';
import { api, path } from '../api.js';
import * as A from '../logic/alerts.js';
import { describe } from '../logic/errors.js';
import { WEB_VERSION, roleLabel } from '../logic/homes.js';
import { INSTALL_STEPS, switchVisible, testBlocker } from '../logic/pushstate.js';
import * as auth from '../auth.js';
import * as push from '../push.js';
import { icon } from '../icons.js';
import { button, card, h, infoDialog, row, section, sheet, toast, toggle } from '../ui.js';

const STEP_ICONS = ['share', 'add_box', 'home'];

export function renderSettings(page) {
  page.append(section('이 휴대폰 알림'), phoneCard());

  const levels = push.levels();
  page.append(section('알림 종류별 중요도'), h('div', { class: 'card list-card' }, A.CATEGORIES.map((category) =>
    row({ label: A.label(category), caption: A.caption(category), value: A.levelLabel(levels[category]), onClick: () => levelSheet(category) }))));

  if (A.reportIntervalVisible(levels[A.REPORT])) {
    const selected = push.reportInterval();
    page.append(section('정기 보고 간격'), h('div', { class: 'card interval-card', role: 'radiogroup', 'aria-label': '정기 보고 간격' },
      A.INTERVALS.map((minutes) => h('button', {
        type: 'button', class: 'chip' + (minutes === selected ? ' active' : ''), role: 'radio', 'aria-checked': String(minutes === selected),
        'aria-label': '정기 보고 간격 ' + minutes + '분',
        on: { click: () => { if (minutes !== selected) { push.setReportInterval(minutes).then(actions.render); actions.render(); } } },
      }, minutes + '분'))));
  }

  const quiet = push.quiet();
  const quietCard = h('div', { class: 'card quiet-card' },
    toggle('정한 시간에는 조용히 받기', quiet.enabled, (checked) => { push.setQuiet({ ...quiet, enabled: checked }).then(actions.render); actions.render(); }));
  if (quiet.enabled) quietCard.append(timeRow('시작', quiet.start, (minutes) => ({ ...quiet, start: minutes })), timeRow('끝', quiet.end, (minutes) => ({ ...quiet, end: minutes })));
  quietCard.appendChild(h('p', { class: 'card-note' }, '긴급 알림은 울려요'));
  page.append(section('방해 금지 시간'), quietCard);

  if (state.house) {
    page.append(section('집'), h('div', { class: 'card list-card' },
      h('div', { class: 'house-head' }, h('span', { class: 'badge raised' }, icon('home', { size: 20 })),
        h('span', { class: 'house-texts' }, h('span', { class: 'house-name' }, state.house.name), h('span', { class: 'house-role' }, roleLabel(state.house.role)))),
      row({ iconName: 'home', label: '집 바꾸기', onClick: () => actions.switcher() }),
      h('p', { class: 'card-note inset' }, owner() ? '가족 초대·허브 연결·집 삭제는 Android 앱에서 해요' : '가족 초대와 기기 등록은 소유자가 관리해요.')));
  }
  page.append(section('계정'), h('div', { class: 'card list-card' }, row({ iconName: 'logout', label: '로그아웃', chevron: false, onClick: () => actions.logout() })));
  const server = auth.serverVersion();
  page.appendChild(h('p', { class: 'version' }, '가족 스마트홈 웹 · ' + WEB_VERSION + (server ? ' · 서버 ' + server : '')));
}

function phoneCard() {
  const view = push.view();
  const box = h('div', { class: 'card phone-card' },
    h('p', { class: 'phone-status' }, icon('bell', { size: 22, className: 'accent' }), h('span', null, view.title)),
    view.detail ? h('p', { class: 'card-note' }, view.detail) : null);
  if (view.mode === 'install' && push.environment().ios) {
    box.appendChild(h('ol', { class: 'install-steps' }, INSTALL_STEPS.map((step, index) =>
      h('li', null, h('span', { class: 'step-number' }, String(index + 1)), icon(STEP_ICONS[index], { size: 20, className: 'accent' }), h('span', null, step)))));
  }
  if (switchVisible(view)) box.appendChild(toggle('이 휴대폰에서 받기', push.enabled(), onPushSwitch, { event: 'click' }));
  if (push.enabled() && ['ready', 'preparing', 'error'].includes(view.mode)) {
    box.appendChild(row({ iconName: 'refresh', label: '알림 연결 확인', chevron: false, onClick: () => {
      toast('연결 상태를 확인하고 있어요.');
      push.sync(state.account).then(actions.render);
    } }));
  }
  if (owner() && view.mode !== 'dev') box.appendChild(row({ iconName: 'bell', label: '시험 알림 보내기', chevron: false, onClick: sendTest }));
  return box;
}

/** Runs inside the switch's click: the permission prompt must be the first thing the click does (iOS). */
function onPushSwitch(checked, input) {
  if (!checked) { push.disable().then(actions.render); return; }
  if (!('Notification' in window)) { input.checked = false; return; }
  let asked;
  try { asked = Notification.requestPermission(); } catch { asked = Promise.resolve(Notification.permission); }
  Promise.resolve(asked).then(async (permission) => {
    if (permission !== 'granted') {
      input.checked = false;
      actions.render();
      if (permission === 'denied') infoDialog('휴대폰에서 알림을 허용해 주세요', '설정 앱 → 알림 → 스마트홈에서 알림을 허용해 주세요.');
      return;
    }
    const pending = push.enable(state.account);
    actions.render();
    await pending;
    actions.render();
  });
}

async function sendTest() {
  const blocker = testBlocker(push.view());
  if (blocker) {
    if ((await infoDialog(blocker.title, blocker.detail, push.enabled() ? '알림 연결 확인' : null)) === 'extra') push.sync(state.account).then(actions.render);
    return;
  }
  try {
    await api('POST', path('homes', state.homeId, 'notifications', 'test'), { installation_id: push.installationId() });
    toast('알림 전송을 요청했어요. 휴대폰에 도착하는지 확인해 주세요.');
  } catch (failure) {
    if (failure.status === 409 && failure.code === 'installation_not_registered') {
      push.sync(state.account).then(actions.render);
      infoDialog('이 휴대폰의 알림을 연결해 주세요', describe(failure));
      return;
    }
    toast(describe(failure));
  }
}

/** One choice per level with its meaning; 안전 only offers 긴급 and 알림. Saved at once for this phone only. */
function levelSheet(category) {
  const current = push.levels()[category];
  sheet(A.label(category) + ' · ' + A.caption(category), (panel, close) => {
    panel.appendChild(h('div', { class: 'options', role: 'radiogroup' }, A.allowed(category).map((level) => h('button', {
      type: 'button', class: 'option' + (level === current ? ' selected' : ''), role: 'radio', 'aria-checked': String(level === current),
      on: { click: () => { close(); if (level !== current) { push.setLevel(category, level).then(actions.render); actions.render(); } } },
    }, h('span', { class: 'option-texts' }, h('span', { class: 'option-label' }, A.levelLabel(level)), h('span', { class: 'option-meaning' }, A.levelMeaning(level))),
      level === current ? icon('check', { size: 20, className: 'accent' }) : null))));
    panel.appendChild(h('div', { class: 'sheet-actions' }, button('취소', () => close(), { kind: 'text' })));
  });
}

function timeRow(label, minutes, next) {
  const input = h('input', { type: 'time', class: 'time-input', value: A.formatClock(minutes), 'aria-label': '방해 금지 ' + label + ' 시각', step: '60' });
  input.addEventListener('change', () => {
    const value = A.parseClock(input.value);
    if (value === null) { input.value = A.formatClock(minutes); return; }
    push.setQuiet(next(value)).then(actions.render);
  });
  return h('label', { class: 'time-row' }, h('span', { class: 'time-label' }, label), input);
}
