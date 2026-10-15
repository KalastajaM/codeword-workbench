'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const {canonicalPuzzle, slots, ruledOutLetters, setRuledOut, rejectedWordsFor, setWordRejected,
  eliminationSuggestionGroups, resetProgress} = require('../static/state.js');

const grid = extra => canonicalPuzzle({rows:1, cols:3, language:'en',
  cells:[{number:'1', letter:'K'}, {number:'20'}, {number:'1', letter:'K'}], ...extra});

test('Canonical puzzles normalize ruled-out letters and rejected words', () => {
  const puzzle = grid({eliminations:{'020':['w','W'], x:['A'], 3:[]}, rejectedWords:[{start:0, direction:'Across', word:'kak'}, {start:'0', direction:'Across', word:'X'}]});
  assert.deepEqual(puzzle.eliminations, {'20':['W']});
  assert.deepEqual(puzzle.rejectedWords, [{start:0, direction:'Across', word:'KAK'}]);
  assert.deepEqual(grid({}).eliminations, {});
  assert.deepEqual(grid({}).rejectedWords, []);
});

test('Rule out and allow letters for one number', () => {
  const puzzle = grid({});
  assert.equal(setRuledOut(puzzle, '20', ['w', 'Q']), true);
  assert.deepEqual(ruledOutLetters(puzzle, '20'), ['Q', 'W']);
  assert.equal(setRuledOut(puzzle, '20', ['W']), false, 'Ruling out twice changes nothing');
  assert.equal(setRuledOut(puzzle, '20', ['Q', 'W'], false), true);
  assert.deepEqual(puzzle.eliminations, {}, 'An empty list is removed');
  assert.equal(setRuledOut(puzzle, '20', ['W'], false), false);
});

test('Reject and restore a word for one slot only', () => {
  const puzzle = canonicalPuzzle({rows:2, cols:2, language:'en', cells:[{}, {}, {}, {}]});
  const [across, , down] = slots(puzzle);
  assert.equal(setWordRejected(puzzle, across, 'at'), true);
  assert.deepEqual(rejectedWordsFor(puzzle, across), ['AT']);
  assert.deepEqual(rejectedWordsFor(puzzle, down), [], 'Another slot is unaffected');
  assert.equal(setWordRejected(puzzle, across, 'AT'), false);
  assert.equal(setWordRejected(puzzle, across, 'AT', false), true);
  assert.deepEqual(puzzle.rejectedWords, []);
});

test('Suggestion groups skip confirmed numbers and letters already ruled out', () => {
  const puzzle = grid({eliminations:{'20':['W']}});
  const groups = eliminationSuggestionGroups(puzzle, [
    {number:'20', letter:'W', run:'KWK'}, {number:'20', letter:'X', run:'KXK'},
    {number:'1', letter:'Q', run:'QQ'}, {number:'99', letter:'Z', run:'ZZ'}]);
  assert.deepEqual(groups, [{number:'20', letters:[{letter:'X', run:'KXK'}]}]);
  assert.deepEqual(eliminationSuggestionGroups(puzzle, null), []);
});

test('Reset puzzle clears both lists', () => {
  const puzzle = grid({eliminations:{'20':['W']}, rejectedWords:[{start:0, direction:'Across', word:'KAK'}]});
  resetProgress(puzzle);
  assert.deepEqual(puzzle.eliminations, {});
  assert.deepEqual(puzzle.rejectedWords, []);
});

test('Ruled-out letters are shown only for numbers without a confirmed letter', () => {
  const {visibleRuledOut} = require('../static/state.js');
  const puzzle = canonicalPuzzle({rows:1, cols:3, language:'en',
    cells:[{number:'3', letter:'Z'}, {number:'20'}, {number:'4', letter:'A'}],
    eliminations:{'3':['A','B'], '20':['W'], '4':['A','Q'], '99':['X']}});
  assert.deepEqual(visibleRuledOut(puzzle), [
    {number:'4', confirmed:true, letters:['A']},
    {number:'20', confirmed:false, letters:['W']}],
    'Confirmed 3 is hidden, confirmed 4 shows only its conflicting A, absent 99 is hidden');
  assert.deepEqual(puzzle.eliminations['3'], ['A','B'], 'Hidden entries stay stored');
});

test('Numbers showing a suggested or mapped letter are not open for ruling out', () => {
  const {visibleRuledOut, numberIsOpen} = require('../static/state.js');
  const puzzle = canonicalPuzzle({rows:1, cols:4, language:'en',
    cells:[{number:'3', letter:'Z'}, {number:'3'}, {number:'20'}, {number:'6'}],
    eliminations:{'20':['W'], '6':['Q']}});
  puzzle.suggestions = {forcedLetters:['Z', 'Z', '', ''], solutions:[{letters:['Z', 'Z', 'E', '']}]};
  assert.deepEqual(visibleRuledOut(puzzle).map(entry => entry.number), ['6'], 'Suggested 20 is hidden');
  assert.equal(numberIsOpen(puzzle, '20'), false);
  assert.equal(numberIsOpen(puzzle, '6'), true);
  const groups = eliminationSuggestionGroups(puzzle, [
    {number:'20', letter:'X', run:'XX'}, {number:'6', letter:'E', run:'EE'}, {number:'6', letter:'B', run:'BB'}]);
  assert.deepEqual(groups, [{number:'6', letters:[{letter:'B', run:'BB'}]}],
    'Suggested numbers and letters shown on another number are left out');
  puzzle.rules.uniqueLetters = false;
  assert.deepEqual(eliminationSuggestionGroups(puzzle, [{number:'6', letter:'E', run:'EE'}])[0].letters, [{letter:'E', run:'EE'}]);
  delete puzzle.suggestions;
  assert.deepEqual(visibleRuledOut(puzzle).map(entry => entry.number), ['6', '20'], 'Without suggestions 20 is open again');
});
