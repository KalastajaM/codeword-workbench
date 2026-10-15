'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {HANDLE_NAMES, defaultHandles, moveHandle, outlinePath} = require('../static/straighten.js');

test('default handles inset the image with midpoints on straight edges', () => {
 const handles = defaultHandles();
 assert.deepEqual(Object.keys(handles), HANDLE_NAMES);
 assert.deepEqual(handles.topLeft, {x: .08, y: .08});
 assert.deepEqual(handles.right, {x: .92, y: .5});
});

test('moving a corner drags its edge midpoints halfway and stays inside the image', () => {
 const handles = defaultHandles();
 const moved = moveHandle(handles, 'topLeft', .02, -.5);
 assert.deepEqual(moved.topLeft, {x: .02, y: 0});
 assert.ok(Math.abs(moved.top.y - .04) < 1e-9);
 assert.ok(Math.abs(moved.left.x - .05) < 1e-9);
 assert.deepEqual(moved.right, handles.right);
 const bent = moveHandle(handles, 'top', .5, .15);
 assert.deepEqual(bent.topLeft, handles.topLeft);
});

test('outline curves pass through edge midpoints', () => {
 const handles = moveHandle(defaultHandles(), 'top', .5, .04);
 // Quadratic control point = 2*mid - (start+end)/2 = 2*4 - 8 = 0.
 assert.match(outlinePath(handles), /^M8 8 Q50 0 92 8 /);
});
