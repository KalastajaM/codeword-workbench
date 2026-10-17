'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const {letterCertainty} = require('../static/state.js');

test('Certainty bands follow the selected alternative and skip confirmed, black and unnumbered cells', () => {
  const cells = [{number: '07', letter: ''}, {number: '7', letter: 'B'}, {black: true}, {number: '', letter: ''}, {number: '3', letter: ''}, {number: '4', letter: ''}];
  const puzzle = {cells, suggestions: {stats: {closeMargin: 5, clearMargin: 15}, solutions: [
    {letters: ['A', 'B', '', 'C', 'D', 'E'], numberMargins: {'7': {alternative: 'E', margin: 0.5}, '3': {alternative: 'F', margin: 5}, '4': {alternative: 'G', margin: 15}}},
    {letters: ['A', 'B', '', 'C', 'F', 'E'], numberMargins: {'3': {alternative: 'D', margin: 14.99}}}]}};
  assert.deepEqual(letterCertainty(puzzle, 0), [{number: '7', alternative: 'E', margin: 0.5, level: 'close'}, null, null, null,
    {number: '3', alternative: 'F', margin: 5, level: 'moderate'}, {number: '4', alternative: 'G', margin: 15, level: 'clear'}]);
  assert.equal(letterCertainty(puzzle, 1)[4].level, 'moderate');
  assert.equal(letterCertainty(puzzle, 1)[5], null, 'A number without a margin is not shaded');
  assert.deepEqual(letterCertainty({cells}), cells.map(() => null), 'No result, nothing shaded');
});
