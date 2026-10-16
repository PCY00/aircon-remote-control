// Line icons of the Android app (FamilyIcon.java) as SVG: 24-unit grid, 1.7 stroke, round caps.
// Built with createElementNS so no markup strings or style attributes are needed (CSP).

const NS = 'http://www.w3.org/2000/svg';

function line(...points) {
  let d = `M${points[0]} ${points[1]}`;
  for (let i = 2; i < points.length; i += 2) d += ` L${points[i]} ${points[i + 1]}`;
  return ['path', { d }];
}
/** Android Canvas.drawArc(left, top, right, bottom, start, sweep): degrees clockwise from 3 o'clock. */
function arc(l, t, r, b, start, sweep) {
  const cx = (l + r) / 2, cy = (t + b) / 2, rx = (r - l) / 2, ry = (b - t) / 2;
  const at = (deg) => [cx + rx * Math.cos(deg * Math.PI / 180), cy + ry * Math.sin(deg * Math.PI / 180)];
  const [x1, y1] = at(start), [x2, y2] = at(start + sweep);
  const f = (n) => Math.round(n * 100) / 100;
  return ['path', { d: `M${f(x1)} ${f(y1)} A${f(rx)} ${f(ry)} 0 ${Math.abs(sweep) > 180 ? 1 : 0} ${sweep > 0 ? 1 : 0} ${f(x2)} ${f(y2)}` }];
}
const circle = (cx, cy, r) => ['circle', { cx, cy, r }];
const rect = (x, y, width, height, rx) => ['rect', { x, y, width, height, rx }];
const group = (transform, ...children) => ['g', { transform }, children];

function star() {
  const points = [];
  for (let point = 0; point < 10; point++) {
    const angle = (-90 + point * 36) * Math.PI / 180, radius = point % 2 === 0 ? 9 : 4;
    points.push((12 + radius * Math.cos(angle)).toFixed(2) + ',' + (12.5 + radius * Math.sin(angle)).toFixed(2));
  }
  return ['polygon', { points: points.join(' ') }];
}

const SHAPES = {
  home: [line(3, 10, 12, 3, 21, 10), line(5, 9, 5, 21, 10, 21, 10, 14, 14, 14, 14, 21, 19, 21, 19, 9)],
  settings: [line(4, 6, 20, 6), line(4, 12, 20, 12), line(4, 18, 20, 18), circle(9, 6, 2), circle(16, 12, 2), circle(8, 18, 2)],
  bell: [arc(6, 4, 18, 16, 180, 180), line(6, 10, 6, 15, 4, 18, 20, 18, 18, 15, 18, 10), arc(10, 18, 14, 22, 0, 180)],
  door: [line(5, 21, 5, 3, 17, 3, 17, 21, 5, 21), circle(13, 12, 0.7), line(17, 21, 21, 21)],
  family: [circle(9, 7, 3), circle(18, 9, 2), arc(3, 13, 15, 25, 180, 180), arc(15, 14, 22, 23, 180, 170)],
  hub: [rect(4, 6, 16, 14, 3), line(8, 3, 8, 6), line(16, 3, 16, 6), circle(9, 13, 1), line(13, 13, 16, 13)],
  warning: [line(12, 3, 22, 21, 2, 21, 12, 3), line(12, 9, 12, 14), circle(12, 18, 0.5)],
  back: [line(14, 5, 7, 12, 14, 19), line(7, 12, 21, 12)],
  chevron: [line(9, 6, 15, 12, 9, 18)],
  refresh: [arc(4, 4, 20, 20, 40, 300), line(20, 4, 20, 10, 14, 10)],
  add: [line(12, 5, 12, 19), line(5, 12, 19, 12)],
  minus: [line(5, 12, 19, 12)],
  logout: [line(10, 4, 4, 4, 4, 20, 10, 20), line(9, 12, 21, 12, 17, 8), line(21, 12, 17, 16)],
  network: [arc(2, 3, 22, 23, 220, 100), arc(6, 8, 18, 20, 220, 100), circle(12, 18, 1)],
  trash: [line(4, 6, 20, 6), line(9, 3, 15, 3, 15, 6), line(6, 6, 7, 21, 17, 21, 18, 6), line(10, 10, 10, 17), line(14, 10, 14, 17)],
  snowflake: [0, 60, 120, 180, 240, 300].map((angle) => group(`rotate(${angle} 12 12)`, line(12, 12, 12, 3), line(9.8, 5, 12, 7.2, 14.2, 5))),
  auto: [arc(5, 5, 19, 19, 200, 140), line(19.6, 6.8, 18.6, 9.6, 16, 8.1), arc(5, 5, 19, 19, 20, 140), line(4.4, 17.2, 5.4, 14.4, 8, 15.9)],
  droplet: [['path', { d: 'M12 3 C9 7 5 10.5 5 14.5 A7 7 0 0 0 19 14.5 C19 10.5 15 7 12 3' }]],
  wind: [line(3, 9, 15, 9), arc(12.5, 4, 17.5, 9, 90, -270), line(3, 13, 19, 13), line(3, 17, 13, 17), arc(10.5, 17, 15.5, 22, 270, 270)],
  power: [arc(5, 5, 19, 19, -60, 300), line(12, 3, 12, 11)],
  aircon: [rect(3, 5, 18, 8, 2), line(6, 10, 18, 10), line(8, 16, 7, 20), line(12, 16, 12, 20), line(16, 16, 17, 20)],
  shield: [line(12, 3, 19, 6, 19, 12, 12, 21, 5, 12, 5, 6, 12, 3), line(9, 12, 11, 14, 15, 10)],
  expand: [line(6, 9, 12, 15, 18, 9)],
  collapse: [line(6, 15, 12, 9, 18, 15)],
  thermometer: [rect(9.5, 3, 5, 12, 2.5), circle(12, 18, 3.5), line(12, 8, 12, 18)],
  bulb: [arc(6, 3, 18, 15, 150, 240), line(7.6, 12, 9.5, 15.5, 9.5, 17, 14.5, 17, 14.5, 15.5, 16.4, 12), line(10, 20, 14, 20)],
  plug: [line(9, 3, 9, 8), line(15, 3, 15, 8), line(6, 8, 18, 8, 18, 12), arc(6, 6, 18, 18, 0, 180), line(6, 12, 6, 8), line(12, 18, 12, 21)],
  motion: [circle(13, 4.5, 1.8), line(9, 10, 12, 8, 15, 10, 17, 12), line(12, 8, 11, 14, 14, 17, 14, 21), line(11, 14, 8, 17, 6, 17)],
  wifi_off: [arc(2, 4, 22, 24, 220, 100), arc(6, 9, 18, 21, 220, 100), circle(12, 18, 1), line(4, 4, 20, 20)],
  battery: [rect(3, 8, 16, 8, 2), line(21, 11, 21, 13), line(6, 11, 6, 13)],
  star: [star()],
  check: [line(5, 12, 10, 17, 19, 7)],
  share: [line(8, 7, 12, 3, 16, 7), line(12, 3, 12, 15), line(8, 10, 5, 10, 5, 21, 19, 21, 19, 10, 16, 10)],
  add_box: [rect(4, 4, 16, 16, 4), line(12, 8, 12, 16), line(8, 12, 16, 12)],
};

function build(spec) {
  const [tag, attributes, children] = spec;
  const element = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  if (children) for (const child of children) element.appendChild(build(child));
  return element;
}

/** An inline SVG icon; `filled` fills the shape (the filled star). Decorative unless labelled by its button. */
export function icon(name, { size = 24, filled = false, className = '' } = {}) {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', String(size));
  svg.setAttribute('height', String(size));
  svg.setAttribute('fill', filled ? 'currentColor' : 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.7');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.setAttribute('class', ('icon ' + className).trim());
  for (const spec of SHAPES[name] || [circle(12, 12, 8)]) svg.appendChild(build(spec));
  return svg;
}
export const ICON_NAMES = Object.freeze(Object.keys(SHAPES));
