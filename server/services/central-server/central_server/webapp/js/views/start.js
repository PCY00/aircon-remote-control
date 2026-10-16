// Screens before a home is open: loading, missing web settings, sign-in, home list failure, onboarding.

import { actions, state } from '../context.js';
import { icon } from '../icons.js';
import { button, card, h, row } from '../ui.js';

/** Nodes only: the DOM's own append() would print a null as the text "null". */
function hero(iconName, title, text, tone = '') {
  return [
    h('span', { class: 'badge hero-badge ' + tone }, icon(iconName, { size: 34 })),
    h('h1', { class: 'hero-title' }, title),
    text ? h('p', { class: 'hero-text' }, text) : null,
  ].filter(Boolean);
}

export function renderLoading(page) {
  page.append(...hero('home', '가족 스마트홈', null), h('p', { class: 'muted-line center' }, '불러오고 있어요…'));
}

export function renderConfigError(page, kind) {
  if (kind === 'network') {
    page.append(...hero('wifi_off', '서버에 연결할 수 없어요', '인터넷 연결을 확인해 주세요.', 'warning'));
  } else {
    page.append(...hero('warning', '아직 웹앱 설정이 준비되지 않았어요', '집 소유자에게 알려 주세요.', 'warning'));
  }
  page.appendChild(button('다시 확인', () => location.reload(), { kind: 'primary' }));
}

export function renderLogin(page, { error, signingIn }) {
  page.append(...hero('home', '우리 집을 함께', null),
    h('p', { class: 'hero-accent' }, '가족만 연결되는 나의 스마트홈'),
    h('div', { class: 'card login-card' },
      button(signingIn ? 'Google로 이동하고 있어요…' : 'Google로 계속하기', () => actions.signIn(), { kind: 'primary', disabled: signingIn }),
      error ? h('p', { class: 'card-note danger', role: 'alert' }, error) : null),
    h('p', { class: 'footnote center' }, '집 소유자가 초대한 가족만 참여할 수 있어요.'));
}

export function renderStart(page) {
  if (!state.homesError) { page.appendChild(card(h('p', { class: 'card-title' }, '우리 집을 불러오고 있어요…'))); return; }
  page.append(card(
    h('p', { class: 'card-title with-icon' }, icon('warning', { size: 20, className: 'warning' }), '집 목록을 불러오지 못했어요'),
    h('p', { class: 'card-note' }, state.homesError),
    button('다시 연결', () => actions.start(), { kind: 'primary' })),
  h('div', { class: 'card list-card' }, row({ iconName: 'logout', label: '로그아웃', chevron: false, onClick: () => actions.logout() })));
}

export function renderOnboarding(page) {
  page.append(...hero('home', '아직 연결된 집이 없어요', '새 집을 만들거나 가족이 보낸 초대를 수락해 주세요.'),
    button('새 집 만들기', () => actions.createHome(), { kind: 'primary' }),
    h('div', { class: 'card list-card' },
      row({ iconName: 'family', label: '초대 코드로 참여', onClick: () => actions.acceptInvitation() }),
      row({ iconName: 'logout', label: '로그아웃', chevron: false, onClick: () => actions.logout() })));
}
