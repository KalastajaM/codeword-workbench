'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const {weakLetters} = require('../static/state.js');

test('Weak letters follow the selected alternative and skip confirmed, black and unnumbered cells', () => {
  const puzzle = {cells: [{number: '07', letter: ''}, {number: '7', letter: 'B'}, {black: true}, {number: '', letter: ''}, {number: '3', letter: ''}],
    suggestions: {solutions: [{letters: ['A', 'B', '', 'C', 'D'], weakNumbers: {'7': {alternative: 'E', margin: 0.5}}},
      {letters: ['A', 'B', '', 'C', 'F'], weakNumbers: {'3': {alternative: 'D', margin: 1}}}]}};
  assert.deepEqual(weakLetters(puzzle, 0), [{number: '7', alternative: 'E', margin: 0.5}, null, null, null, null]);
  assert.deepEqual(weakLetters(puzzle, 1), [null, null, null, null, {number: '3', alternative: 'D', margin: 1}]);
  assert.deepEqual(weakLetters({cells: puzzle.cells}), [null, null, null, null, null], 'No result, nothing marked');
});
