'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const {SHOWCASE, samplePuzzle, compareWithSample} = require('../static/samples.js');
const {canonicalPuzzle, slots} = require('../static/state.js');

test('Showcase puzzle gives numbers only and is set up for dictionary-free deep search', () => {
  const puzzle = canonicalPuzzle({...samplePuzzle(), rules: {}});
  assert.equal(puzzle.rows, 13); assert.equal(puzzle.cols, 13);
  assert.equal(puzzle.useDictionary, false);
  assert.equal(puzzle.searchMode, 'deep');
  assert.ok(puzzle.cells.every(c => !c.letter), 'No letters are given');
  const numbers = new Set(Object.values(SHOWCASE.key));
  assert.equal(numbers.size, Object.keys(SHOWCASE.key).length, 'Each letter has its own number');
  for (const slot of slots(puzzle)) assert.ok(slot.cells.length >= 3, 'Every word has at least three letters');
  const covered = new Set(slots(puzzle).flatMap(slot => slot.cells));
  puzzle.cells.forEach((c, i) => { if (!c.black) assert.ok(covered.has(i), 'Every open cell belongs to a word'); });
});

test('Showcase check counts matching cells and ignores edited grids', () => {
  const puzzle = samplePuzzle(), answer = SHOWCASE.answer.join('').split('').map(ch => ch === '#' ? '' : ch);
  const total = answer.filter(Boolean).length;
  assert.deepEqual(compareWithSample(puzzle, answer), {correct: total, total});
  const wrong = answer.slice(); wrong[0] = 'Q';
  assert.deepEqual(compareWithSample(puzzle, wrong), {correct: total - 1, total});
  assert.equal(compareWithSample({...puzzle, sample: undefined}, answer), null);
  const edited = {...puzzle, cells: puzzle.cells.map((c, i) => i === 0 ? {...c, number: '99'} : c)};
  assert.equal(compareWithSample(edited, answer), null, 'A changed grid is no longer the sample');
});
