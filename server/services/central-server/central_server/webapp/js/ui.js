// DOM helpers, sheets, dialogs and the toast. Text always goes in as text nodes (never HTML), and
// nothing sets a style attribute, so the page works under the strict /app/ content security policy.

import { icon } from './icons.js';

export function h(tag, props, ...children) {
  const element = document.createElement(tag);
  if (props) {
    for (const [key, value] of Object.entries(props)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') element.className = value;
      else if (key === 'on') for (const [name, handler] of Object.entries(value)) element.addEventListener(name, handler);
      else if (key === 'dataset') Object.assign(element.dataset, value);
      else if (key === 'text') element.textContent = value;
      else if (key === 'disabled' || key === 'checked' || key === 'value' || key === 'hidden') element[key] = value;
      else element.setAttribute(key, value === true ? '' : String(value));
    }
  }
  append(element, children);
  return element;
}
export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    parent.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}
export function clear(element) { while (element.firstChild) element.removeChild(element.firstChild); return element; }

/** Icon-only button; the label is read by VoiceOver. */
export function iconButton(name, label, onClick, { className = '', size = 22 } = {}) {
  return h('button', { type: 'button', class: ('icon-button ' + className).trim(), 'aria-label': label, on: { click: onClick } }, icon(name, { size }));
}
export function button(label, onClick, { kind = 'secondary', disabled = false, className = '' } = {}) {
  return h('button', { type: 'button', class: `button ${kind} ${className}`.trim(), disabled, on: { click: onClick } }, label);
}
export function section(label) { return h('h2', { class: 'section' }, label); }
export function card(...children) { return h('div', { class: 'card' }, ...children); }
/** A tappable list row: icon, label (and caption), value, chevron. */
export function row({ iconName, label, caption, value, onClick, danger = false, chevron = true, current = false }) {
  return h('button', { type: 'button', class: 'row' + (danger ? ' danger' : '') + (current ? ' current' : ''), on: { click: onClick }, 'aria-current': current ? 'true' : null },
    iconName ? h('span', { class: 'row-icon' }, icon(iconName, { size: 22 })) : null,
    h('span', { class: 'row-texts' }, h('span', { class: 'row-label' }, label), caption ? h('span', { class: 'row-caption' }, caption) : null),
    value ? h('span', { class: 'row-value' }, value) : null,
    current ? h('span', { class: 'row-check' }, icon('check', { size: 20 })) : null,
    chevron ? h('span', { class: 'row-chevron' }, icon('chevron', { size: 18 })) : null);
}
/**
 * iOS-style switch built on a checkbox, so VoiceOver reads it as a switch. `event: 'click'` runs the
 * handler inside the click itself (needed when it asks for notification permission).
 */
export function toggle(label, checked, onChange, { disabled = false, event = 'change' } = {}) {
  const input = h('input', { type: 'checkbox', role: 'switch', class: 'switch', checked, disabled });
  input.addEventListener(event, () => onChange(input.checked, input));
  return h('label', { class: 'switch-row' + (disabled ? ' disabled' : '') }, h('span', { class: 'switch-label' }, label), input);
}

// ---- Toast ----

let toastTimer = 0;
export function toast(message) {
  let element = document.getElementById('toast');
  if (!element) {
    element = h('div', { id: 'toast', class: 'toast', role: 'status', 'aria-live': 'polite' });
    document.body.appendChild(element);
  }
  element.textContent = message;
  element.classList.add('shown');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove('shown'), 3200);
}

// ---- Overlays (sheet at the bottom, dialog in the middle) ----

const openOverlays = [];
export function overlayOpen() { return openOverlays.length > 0; }

function overlay(kind, build, { onClose } = {}) {
  const backdrop = h('div', { class: 'backdrop ' + kind + '-backdrop' });
  const panel = h('div', { class: kind, role: 'dialog', 'aria-modal': 'true' });
  backdrop.appendChild(panel);
  let closed = false;
  const close = (result) => {
    if (closed) return;
    closed = true;
    backdrop.classList.remove('shown');
    const index = openOverlays.indexOf(backdrop);
    if (index >= 0) openOverlays.splice(index, 1);
    setTimeout(() => backdrop.remove(), 180);
    document.removeEventListener('keydown', onKey);
    if (onClose) onClose(result);
  };
  const onKey = (event) => { if (event.key === 'Escape' && openOverlays[openOverlays.length - 1] === backdrop) close(null); };
  backdrop.addEventListener('click', (event) => { if (event.target === backdrop) close(null); });
  document.addEventListener('keydown', onKey);
  build(panel, close);
  document.body.appendChild(backdrop);
  openOverlays.push(backdrop);
  requestAnimationFrame(() => backdrop.classList.add('shown'));
  const first = panel.querySelector('input, button.primary, button');
  if (first && first.tagName === 'INPUT') setTimeout(() => first.focus(), 60);
  return close;
}

/** Bottom sheet with a title and rows; build(panel, close) adds the content. */
export function sheet(title, build, options) {
  return overlay('sheet', (panel, close) => {
    panel.setAttribute('aria-label', title);
    panel.appendChild(h('div', { class: 'sheet-grip', 'aria-hidden': 'true' }));
    if (title) panel.appendChild(h('h2', { class: 'sheet-title' }, title));
    build(panel, close);
  }, options);
}

/** Centered dialog; resolves with the pressed button's value (null when dismissed). */
export function dialog({ title, message, buttons }) {
  return new Promise((resolve) => {
    overlay('dialog', (panel, close) => {
      panel.setAttribute('aria-label', title);
      panel.appendChild(h('h2', { class: 'dialog-title' }, title));
      if (message) panel.appendChild(h('p', { class: 'dialog-message' }, message));
      const actions = h('div', { class: 'dialog-actions' });
      for (const item of buttons) {
        actions.appendChild(h('button', { type: 'button', class: 'button ' + (item.kind || 'text'), on: { click: () => close(item.value) } }, item.label));
      }
      panel.appendChild(actions);
    }, { onClose: resolve });
  });
}
export function confirmDialog(title, message, confirmLabel) {
  return dialog({ title, message, buttons: [{ label: '취소', value: false }, { label: confirmLabel, value: true, kind: 'primary' }] })
    .then((value) => value === true);
}
export function infoDialog(title, message, extra) {
  const buttons = [{ label: '닫기', value: null }];
  if (extra) buttons.push({ label: extra, value: 'extra', kind: 'primary' });
  return dialog({ title, message, buttons });
}

/** One text input in a sheet; resolves with the trimmed value or null. */
export function inputSheet({ title, placeholder, maxLength, confirmLabel = '확인', autocomplete = 'off' }) {
  return new Promise((resolve) => {
    sheet(title, (panel, close) => {
      const input = h('input', { type: 'text', class: 'text-input', placeholder, maxlength: maxLength, autocomplete, autocapitalize: 'off', spellcheck: 'false', enterkeyhint: 'done' });
      const error = h('p', { class: 'input-error', role: 'alert' });
      const submit = () => {
        const value = input.value.trim();
        if (!value) { error.textContent = '내용을 입력해 주세요.'; input.focus(); return; }
        close(value);
      };
      input.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); submit(); } });
      panel.append(input, error, h('div', { class: 'sheet-actions' },
        button('취소', () => close(null), { kind: 'text' }), button(confirmLabel, submit, { kind: 'primary' })));
    }, { onClose: resolve });
  });
}
