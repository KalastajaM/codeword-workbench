/* Handle geometry for straightening a photographed grid. Positions are image fractions. */
(function (root) {
 'use strict';
 const HANDLE_NAMES = ['topLeft', 'top', 'topRight', 'right', 'bottomRight', 'bottom', 'bottomLeft', 'left'];
 const EDGES = [['topLeft', 'top', 'topRight'], ['topRight', 'right', 'bottomRight'], ['bottomRight', 'bottom', 'bottomLeft'], ['bottomLeft', 'left', 'topLeft']];
 const clamp = value => Math.min(1, Math.max(0, value));

 // A slightly inset rectangle; earlier automatic alignment of a skewed photo is unreliable.
 function defaultHandles() {
  const [x0, y0, x1, y1] = [.08, .08, .92, .92], xm = .5, ym = .5;
  const points = [[x0, y0], [xm, y0], [x1, y0], [x1, ym], [x1, y1], [xm, y1], [x0, y1], [x0, ym]];
  return Object.fromEntries(HANDLE_NAMES.map((name, i) => [name, {x: points[i][0], y: points[i][1]}]));
 }

 // Moving a corner carries the adjacent edge midpoints halfway, so straight edges stay straight.
 function moveHandle(handles, name, x, y) {
  const next = {...handles}, old = handles[name], point = {x: clamp(x), y: clamp(y)};
  next[name] = point;
  for (const [start, middle, end] of EDGES) {
   if (name !== start && name !== end) continue;
   const m = handles[middle];
   next[middle] = {x: clamp(m.x + (point.x - old.x) / 2), y: clamp(m.y + (point.y - old.y) / 2)};
  }
  return next;
 }

 // The outline the server flattens: each edge is a curve through its midpoint (in percent units).
 function outlinePath(handles) {
  const p = name => [handles[name].x * 100, handles[name].y * 100];
  let path = `M${p('topLeft').join(' ')}`;
  for (const [start, middle, end] of EDGES) {
   const [sx, sy] = p(start), [mx, my] = p(middle), [ex, ey] = p(end);
   path += ` Q${2 * mx - (sx + ex) / 2} ${2 * my - (sy + ey) / 2} ${ex} ${ey}`;
  }
  return path + ' Z';
 }

 const helpers = {HANDLE_NAMES, defaultHandles, moveHandle, outlinePath};
 if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
 else root.Straighten = helpers;
})(typeof window !== 'undefined' ? window : globalThis);
