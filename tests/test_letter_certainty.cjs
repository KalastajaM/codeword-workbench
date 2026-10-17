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

test('Dictionary results compare the kept alternatives for each number', () => {
  const {certaintyMargins} = require('../static/state.js');
  const cells = [{number: '1', letter: ''}, {number: '2', letter: ''}, {number: '3', letter: ''}, {number: '03', letter: ''}, {number: '4', letter: 'Z'}];
  const solution = (letters, score, supportedWords) => ({letters, score, supportedWords});
  const puzzle = {cells, suggestions: {stats: {}, solutions: [
    solution(['A', 'B', 'C', 'C', 'Z'], 10, 3),
    solution(['A', 'B', 'D', 'D', 'Z'], 8, 3),
    solution(['A', 'E', 'C', 'C', 'Z'], 9.9, 2),
    solution(['X', 'B', 'C', 'C', 'Z'], 1, 4)]}};
  assert.deepEqual(letterCertainty(puzzle, 0), [
    {number: '1', alternative: 'X', margin: 0, level: 'close', alternativeIndex: 3, moreSupport: true},
    {number: '2', alternative: null, margin: null, level: 'clear'},
    {number: '3', alternative: 'D', margin: 2, level: 'close', alternativeIndex: 1, moreSupport: false},
    {number: '3', alternative: 'D', margin: 2, level: 'close', alternativeIndex: 1, moreSupport: false},
    null]);
  assert.equal(certaintyMargins(puzzle, 0)['2'].alternative, null, 'A rival with fewer dictionary words does not count');
  assert.deepEqual(letterCertainty(puzzle, 1)[2], {number: '3', alternative: 'C', margin: 0, level: 'close', alternativeIndex: 0, moreSupport: false}, 'A lower-ranked selection trails its rival');
  puzzle.suggestions.solutions[1].score = -10;
  assert.equal(letterCertainty(puzzle, 0)[2].level, 'clear', 'A gap of 15 points or more is a clear lead');
  puzzle.suggestions.solutions[1].score = 0;
  assert.equal(letterCertainty(puzzle, 0)[2].level, 'moderate');
  assert.equal(certaintyMargins({cells, suggestions: {solutions: []}}, 0), null, 'No alternatives, no margins');
});
