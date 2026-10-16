'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {OUTSIDE, CORNERS, EDGE_NAMES, MAX_EDGE_POINTS, defaultHandles, moveCorner, moveEdgePoint, removeEdgePoint, addEdgePoint, surface, edgePaths, outlinePath} = require('../static/straighten.js');

const near = (a, b, tolerance = 1e-9) => assert.ok(Math.abs(a - b) < tolerance, `${a} is not near ${b}`);

test('default handles inset the image with one point on each straight edge', () => {
 const handles = defaultHandles();
 assert.deepEqual(Object.keys(handles).sort(), [...CORNERS, ...EDGE_NAMES].sort());
 assert.deepEqual(handles.topLeft, {x: .08, y: .08});
 assert.deepEqual(handles.right, [{x: .92, y: .5}]);
});

test('moving a corner carries edge points by their nearness and stays near the image', () => {
 const handles = {...defaultHandles(), top: [{x: .29, y: .08}, {x: .5, y: .08}]};
 const moved = moveCorner(handles, 'topLeft', .02, 0);
 assert.deepEqual(moved.topLeft, {x: .02, y: 0});
 // A quarter of the way along the top edge moves three quarters as far as the corner.
 near(moved.top[0].y, .08 - .08 * .75);
 near(moved.top[1].y, .04);
 // A corner cut off by the photo may sit just outside it, but no further.
 assert.deepEqual(moveCorner(handles, 'bottomRight', 1.5, .9).bottomRight, {x: 1 + OUTSIDE, y: .9});
 near(moved.left[0].x, .05);
 assert.deepEqual(moved.right, handles.right);
 const bent = moveEdgePoint(handles, 'top', 1, .5, .15);
 assert.deepEqual(bent.topLeft, handles.topLeft);
 assert.deepEqual(bent.top[1], {x: .5, y: .15});
});

test('the outline passes through every edge point and closes at the corners', () => {
 let handles = moveEdgePoint(defaultHandles(), 'top', 0, .5, .04);
 handles = addEdgePoint(handles, 'top', .25, .03).handles;
 handles = addEdgePoint(handles, 'top', .8, .07).handles;
 assert.deepEqual(handles.top.map(p => p.x), [.25, .5, .8]);
 const at = surface(handles);
 near(at(0, 0)[0], .08); near(at(1, 1)[1], .92);
 const top = edgePaths(handles, 1, 1, 400).top.slice(1).split(' L').map(pair => pair.split(' ').map(Number));
 for (const point of handles.top) assert.ok(top.some(([x, y]) => Math.hypot(x / 100 - point.x, y / 100 - point.y) < .002));
 assert.match(outlinePath(handles), /^M8 8 L.* Z$/);
});

test('straight edges stay straight without any points', () => {
 const handles = {...defaultHandles(), top: [], right: [], bottom: [], left: []};
 assert.match(edgePaths(handles, 1, 1, 4).top, /^M8 8 L29 8 L50 8 L71 8 L92 8$/);
});

test('edge points can be removed, and crowded or surplus points are refused', () => {
 const handles = defaultHandles();
 assert.deepEqual(removeEdgePoint(handles, 'left', 0).left, []);
 assert.ok(addEdgePoint(handles, 'top', .505, .08).error);
 assert.ok(addEdgePoint(handles, 'top', .081, .08).error);
 let full = {...handles, top: []};
 for (let i = 1; i <= MAX_EDGE_POINTS; i++) full = addEdgePoint(full, 'top', .08 + .84 * i / (MAX_EDGE_POINTS + 1), .08).handles;
 assert.equal(full.top.length, MAX_EDGE_POINTS);
 assert.ok(addEdgePoint(full, 'top', .1, .08).error);
});
