// 270° cooling temperature dial in SVG. It only edits the unsent draft; sending stays behind the
// confirmation dialog. Outside cooling the arc is greyed, shows the mode name and ignores touches.

import {
  DIAL_MAX, DIAL_MIN, DIAL_START, DIAL_SWEEP, angleOf, arcPath, clampTemperature, inGap, pointOnCircle, sweepFor,
  temperatureForAngle, temperatureForDrag,
} from './logic/aircon.js';

const NS = 'http://www.w3.org/2000/svg';
const SIZE = 228, C = SIZE / 2, R = 97;

function el(tag, attributes) {
  const element = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  return element;
}

export function createDial({ onChange, onDragging }) {
  const svg = el('svg', { viewBox: `0 0 ${SIZE} ${SIZE}`, class: 'dial', role: 'slider', tabindex: '0', 'aria-valuemin': DIAL_MIN, 'aria-valuemax': DIAL_MAX });
  const track = el('path', { class: 'dial-track', d: arcPath(C, C, R, DIAL_START, DIAL_SWEEP) });
  const progress = el('path', { class: 'dial-progress' });
  const thumb = el('circle', { class: 'dial-thumb', r: 13 });
  const ring = el('circle', { class: 'dial-thumb-ring', r: 11.5 });
  const value = el('text', { class: 'dial-value', x: C, 'text-anchor': 'middle' });
  const caption = el('text', { class: 'dial-caption', x: C, 'text-anchor': 'middle' });
  const [lx, ly] = pointOnCircle(C, C, R, DIAL_START), [rx, ry] = pointOnCircle(C, C, R, DIAL_START + DIAL_SWEEP);
  const low = el('text', { class: 'dial-end', x: lx.toFixed(1), y: (ly + 26).toFixed(1), 'text-anchor': 'middle' });
  const high = el('text', { class: 'dial-end', x: rx.toFixed(1), y: (ry + 26).toFixed(1), 'text-anchor': 'middle' });
  low.textContent = DIAL_MIN + '°'; high.textContent = DIAL_MAX + '°';
  svg.append(track, progress, low, high, value, caption, thumb, ring);

  let temperature = 24, adjustable = true, dragging = false;

  function draw(mode, note) {
    svg.classList.toggle('disabled', !adjustable);
    const sweep = sweepFor(temperature);
    progress.setAttribute('d', adjustable ? arcPath(C, C, R, DIAL_START, sweep) : '');
    const [tx, ty] = pointOnCircle(C, C, R, DIAL_START + sweep);
    for (const circle of [thumb, ring]) { circle.setAttribute('cx', tx.toFixed(2)); circle.setAttribute('cy', ty.toFixed(2)); circle.setAttribute('visibility', adjustable ? 'visible' : 'hidden'); }
    const big = adjustable ? temperature + '°' : mode;
    value.textContent = big;
    value.setAttribute('font-size', adjustable ? '52' : big.length > 3 ? '30' : '36');
    value.setAttribute('y', String(C + (adjustable ? 12 : 10)));
    caption.textContent = note;
    caption.setAttribute('y', String(C + (adjustable ? 42 : 38)));
    svg.setAttribute('aria-valuenow', String(temperature));
    svg.setAttribute('aria-valuetext', adjustable ? '희망 온도 ' + temperature + '도' : mode + ' 모드. ' + note);
    svg.setAttribute('aria-disabled', adjustable ? 'false' : 'true');
  }
  let lastMode = '', lastNote = '';
  function change(next) {
    next = clampTemperature(next);
    if (next === temperature) return;
    temperature = next;
    draw(lastMode, lastNote);
    onChange(temperature);
  }
  function local(event) {
    const box = svg.getBoundingClientRect();
    const scale = SIZE / Math.min(box.width, box.height);
    const offsetX = (box.width - Math.min(box.width, box.height)) / 2, offsetY = (box.height - Math.min(box.width, box.height)) / 2;
    return [(event.clientX - box.left - offsetX) * scale - C, (event.clientY - box.top - offsetY) * scale - C];
  }
  svg.addEventListener('pointerdown', (event) => {
    if (!adjustable) return;
    const [dx, dy] = local(event), distance = Math.hypot(dx, dy), angle = angleOf(dx, dy);
    // Only the ring itself starts a drag; the centre and the opening do nothing.
    if (distance < R - 44 || distance > R + 30 || inGap(angle)) return;
    dragging = true;
    svg.setPointerCapture(event.pointerId);
    event.preventDefault();
    if (onDragging) onDragging(true);
    change(temperatureForAngle(angle));
  });
  svg.addEventListener('pointermove', (event) => {
    if (!dragging) return;
    const [dx, dy] = local(event);
    change(temperatureForDrag(angleOf(dx, dy), temperature));
  });
  const end = () => { if (!dragging) return; dragging = false; if (onDragging) onDragging(false); };
  svg.addEventListener('pointerup', end);
  svg.addEventListener('pointercancel', end);
  svg.addEventListener('lostpointercapture', end);
  svg.addEventListener('keydown', (event) => {
    if (!adjustable) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') { change(temperature - 1); event.preventDefault(); }
    if (event.key === 'ArrowRight' || event.key === 'ArrowUp') { change(temperature + 1); event.preventDefault(); }
  });

  return {
    element: svg,
    /** Shows the draft without notifying the listener. */
    bind(canAdjust, value, mode, note) {
      adjustable = canAdjust; temperature = clampTemperature(value); lastMode = mode; lastNote = note;
      if (!adjustable) dragging = false;
      draw(mode, note);
    },
  };
}
