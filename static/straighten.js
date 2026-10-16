/* Handle geometry for straightening a photographed grid. Positions are image fractions.
   Mirrors app/straighten.py so the outline shows exactly what the server flattens. */
(function (root) {
 'use strict';
 const CORNERS = ['topLeft', 'topRight', 'bottomRight', 'bottomLeft'];
 // Each edge runs between two corners; `along` is its unit-square coordinate.
 const EDGES = {top: ['topLeft', 'topRight', 0], right: ['topRight', 'bottomRight', 1], bottom: ['bottomLeft', 'bottomRight', 0], left: ['topLeft', 'bottomLeft', 1]};
 const EDGE_NAMES = Object.keys(EDGES);
 const EDGE_AT = {top: t => [t, 0], right: t => [1, t], bottom: t => [t, 1], left: t => [0, t]};
 const MAX_EDGE_POINTS = 8, MIN_GAP = .02;
 const clamp = value => Math.min(1, Math.max(0, value));

 // A slightly inset rectangle with one bend point per edge; earlier automatic alignment of a skewed photo is unreliable.
 function defaultHandles() {
  const [x0, y0, x1, y1] = [.08, .08, .92, .92];
  return {topLeft: {x: x0, y: y0}, topRight: {x: x1, y: y0}, bottomRight: {x: x1, y: y1}, bottomLeft: {x: x0, y: y1},
   top: [{x: .5, y: y0}], right: [{x: x1, y: .5}], bottom: [{x: .5, y: y1}], left: [{x: x0, y: .5}]};
 }

 // Moving a corner carries each edge point by how near it lies to that corner, so straight edges stay straight.
 function moveCorner(handles, name, x, y) {
  const next = {...handles}, old = handles[name], point = {x: clamp(x), y: clamp(y)};
  next[name] = point;
  for (const [edge, [start, end]] of Object.entries(EDGES)) {
   if (name !== start && name !== end) continue;
   const a = handles[start], b = handles[end], cx = b.x - a.x, cy = b.y - a.y, length = cx * cx + cy * cy || 1;
   next[edge] = handles[edge].map(p => {
    const s = clamp(((p.x - a.x) * cx + (p.y - a.y) * cy) / length), weight = name === start ? 1 - s : s;
    return {x: clamp(p.x + (point.x - old.x) * weight), y: clamp(p.y + (point.y - old.y) * weight)};
   });
  }
  return next;
 }

 function moveEdgePoint(handles, edge, index, x, y) {
  const points = handles[edge].slice();
  points[index] = {x: clamp(x), y: clamp(y)};
  return {...handles, [edge]: points};
 }

 function removeEdgePoint(handles, edge, index) {
  return {...handles, [edge]: handles[edge].filter((_, i) => i !== index)};
 }

 function projective([x0, y0], [x1, y1], [x2, y2], [x3, y3]) {
  const dx1 = x1 - x2, dx2 = x3 - x2, dx3 = x0 - x1 + x2 - x3, dy1 = y1 - y2, dy2 = y3 - y2, dy3 = y0 - y1 + y2 - y3;
  const det = dx1 * dy2 - dx2 * dy1, g = (dx3 * dy2 - dx2 * dy3) / det, h = (dx1 * dy3 - dx3 * dy1) / det;
  return [[x1 - x0 + g * x1, x3 - x0 + h * x3, x0], [y1 - y0 + g * y1, y3 - y0 + h * y3, y0], [g, h, 1]];
 }
 const apply = ([[a, b, c], [d, e, f], [g, h, i]], x, y) => { const w = g * x + h * y + i; return [(a * x + b * y + c) / w, (d * x + e * y + f) / w]; };
 const inverse = ([[a, b, c], [d, e, f], [g, h, i]]) => [[e * i - f * h, c * h - b * i, b * f - c * e], [f * g - d * i, a * i - c * g, c * d - a * f], [d * h - e * g, b * g - a * h, a * e - b * d]];

 // Parabola or cubic through three or four knots, a not-a-knot cubic spline through more.
 function spline(knots) {
  const ts = knots.map(k => k[0]), ys = knots.map(k => k[1]);
  if (knots.length <= 4) return t => knots.reduce((sum, [ti, yi], i) => sum + ts.reduce((term, tj, j) => j === i ? term : term * (t - tj) / (ti - tj), yi), 0);
  const n = knots.length - 1, hs = ts.slice(1).map((t, i) => t - ts[i]);
  const rows = Array.from({length: n + 1}, () => new Array(n + 2).fill(0));
  [rows[0][0], rows[0][1], rows[0][2]] = [hs[1], -(hs[0] + hs[1]), hs[0]];
  [rows[n][n - 2], rows[n][n - 1], rows[n][n]] = [hs[n - 1], -(hs[n - 2] + hs[n - 1]), hs[n - 2]];
  for (let i = 1; i < n; i++) {
   [rows[i][i - 1], rows[i][i], rows[i][i + 1]] = [hs[i - 1], 2 * (hs[i - 1] + hs[i]), hs[i]];
   rows[i][n + 1] = 6 * ((ys[i + 1] - ys[i]) / hs[i] - (ys[i] - ys[i - 1]) / hs[i - 1]);
  }
  for (let col = 0; col <= n; col++) {
   let pivot = col;
   for (let r = col + 1; r <= n; r++) if (Math.abs(rows[r][col]) > Math.abs(rows[pivot][col])) pivot = r;
   [rows[col], rows[pivot]] = [rows[pivot], rows[col]];
   for (let r = 0; r <= n; r++) if (r !== col && rows[r][col]) { const f = rows[r][col] / rows[col][col]; rows[r] = rows[r].map((v, k) => v - f * rows[col][k]); }
  }
  const ms = rows.map((row, i) => row[n + 1] / row[i]);
  return t => {
   let i = ts.findIndex((_, k) => k < n && t < ts[k + 1]);
   if (i < 0) i = n - 1;
   const h = hs[i], a = ts[i + 1] - t, b = t - ts[i];
   return ms[i] * a ** 3 / (6 * h) + ms[i + 1] * b ** 3 / (6 * h) + (ys[i] / h - ms[i] * h / 6) * a + (ys[i + 1] / h - ms[i + 1] * h / 6) * b;
  };
 }

 // Knots (edge parameter, offset across the chord) in pixels of a width x height image.
 function edgeKnots(handles, edge, plane, width, height) {
  const [start, end, along] = EDGES[edge], px = p => [p.x * width, p.y * height];
  const [sx, sy] = px(handles[start]), [ex, ey] = px(handles[end]), length = Math.hypot(ex - sx, ey - sy) || 1;
  const normal = [-(ey - sy) / length, (ex - sx) / length], back = inverse(plane);
  const knots = handles[edge].map(p => {
   const [x, y] = px(p), t = apply(back, x, y)[along], [bx, by] = apply(plane, ...EDGE_AT[edge](t));
   return [t, (x - bx) * normal[0] + (y - by) * normal[1]];
  });
  return {knots: [[0, 0], ...knots, [1, 0]].sort((a, b) => a[0] - b[0]), normal};
 }

 // Unit-square position -> image fraction; null while the outline cannot be flattened.
 function surface(handles, width = 1, height = 1) {
  const plane = projective(...CORNERS.map(name => [handles[name].x * width, handles[name].y * height]));
  if (!plane.flat().every(Number.isFinite)) return null;
  const bends = {};
  for (const edge of EDGE_NAMES) {
   const {knots, normal} = edgeKnots(handles, edge, plane, width, height);
   if (knots.some(([t], i) => !Number.isFinite(t) || i && t - knots[i - 1][0] < MIN_GAP / 4)) return null;
   const amount = spline(knots);
   bends[edge] = t => [amount(t) * normal[0], amount(t) * normal[1]];
  }
  return (u, v) => {
   let [x, y] = apply(plane, u, v);
   for (const [edge, weight, t] of [['top', 1 - v, u], ['bottom', v, u], ['left', 1 - u, v], ['right', u, v]]) {
    const [dx, dy] = bends[edge](t);
    x += weight * dx; y += weight * dy;
   }
   return [x / width, y / height];
  };
 }

 // Each edge as an SVG polyline in percent units, as the server will flatten it.
 function edgePaths(handles, width = 1, height = 1, steps = 32) {
  const at = surface(handles, width, height), paths = {};
  for (const edge of EDGE_NAMES) {
   const [start, end] = EDGES[edge], points = at
    ? Array.from({length: steps + 1}, (_, i) => at(...EDGE_AT[edge](i / steps)))
    : [[handles[start].x, handles[start].y], ...handles[edge].map(p => [p.x, p.y]), [handles[end].x, handles[end].y]];
   paths[edge] = 'M' + points.map(([x, y]) => `${+(x * 100).toFixed(3)} ${+(y * 100).toFixed(3)}`).join(' L');
  }
  return paths;
 }

 // The closed outline, clockwise from the top left corner.
 function outlinePath(handles, width = 1, height = 1) {
  const paths = edgePaths(handles, width, height), reverse = path => 'M' + path.slice(1).split(' L').reverse().join(' L');
  const parts = [paths.top, paths.right, reverse(paths.bottom), reverse(paths.left)].map(path => path.slice(1));
  return 'M' + parts.join(' L') + ' Z';
 }

 // A new bend point on the given edge at (x, y), kept in order along the edge.
 // Returns null with a reason when the edge is full or the point is outside or crowded.
 function addEdgePoint(handles, edge, x, y, width = 1, height = 1) {
  if (handles[edge].length >= MAX_EDGE_POINTS) return {error: `An edge takes at most ${MAX_EDGE_POINTS} points.`};
  const point = {x: clamp(x), y: clamp(y)}, plane = projective(...CORNERS.map(name => [handles[name].x * width, handles[name].y * height]));
  const t = apply(inverse(plane), point.x * width, point.y * height)[EDGES[edge][2]];
  const taken = edgeKnots(handles, edge, plane, width, height).knots.map(k => k[0]);
  if (!(t > MIN_GAP && t < 1 - MIN_GAP) || taken.some(k => Math.abs(k - t) < 2 * MIN_GAP)) return {error: 'Too close to a corner or another point on this edge.'};
  const order = p => apply(inverse(plane), p.x * width, p.y * height)[EDGES[edge][2]];
  const points = [...handles[edge], point].sort((a, b) => order(a) - order(b));
  return {handles: {...handles, [edge]: points}, index: points.indexOf(point)};
 }

 const helpers = {CORNERS, EDGE_NAMES, MAX_EDGE_POINTS, defaultHandles, moveCorner, moveEdgePoint, removeEdgePoint, addEdgePoint, surface, edgePaths, outlinePath};
 if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
 else root.Straighten = helpers;
})(typeof window !== 'undefined' ? window : globalThis);
