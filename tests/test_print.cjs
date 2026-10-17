'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const {sheetSvg, givenLetters} = require('../static/print.js');
const {canonicalPuzzle, generatedAnswer, answerCheck, answerCheckText} = require('../static/state.js');

// CAT / A#E / TEN with C and E given; the answer is kept as a generated puzzle.
function generated() {
  const answer = 'CATA#ETEN'.split('').map(ch => ch === '#' ? '' : ch);
  const key = {C: '3', A: '1', T: '2', E: '4', N: '5'};
  const cells = answer.map(letter => letter ? {number: key[letter], letter: ['C', 'E'].includes(letter) ? letter : '', prefilled: ['C', 'E'].includes(letter)} : {black: true});
  return canonicalPuzzle({name: 'Mine & <yours>', rows: 3, cols: 3, language: 'en', rules: {}, cells,
    generated: {answer, numbers: cells.map(c => c.number || ''), seed: 1}});
}

test('The puzzle sheet shows numbers and given letters but never the answer', () => {
  const puzzle = generated();
  const svg = sheetSvg(puzzle);
  assert.match(svg, /^<svg xmlns="http:\/\/www.w3.org\/2000\/svg"/);
  assert.match(svg, /Mine &amp; &lt;yours&gt;/, 'The name is escaped');
  const letters = [...svg.matchAll(/font-size="24"[^>]*>([^<]+)</g)].map(m => m[1]);
  assert.deepEqual(letters.sort(), ['C', 'E', 'E'], 'Only given letters fill grid cells');
  for (const n of ['1', '2', '3', '4', '5']) assert.match(svg, new RegExp(`>${n}</text>`));
  assert.match(svg, /fill="#aaa" text-decoration="line-through">C</, 'Given letters are crossed off the alphabet');
  assert.doesNotMatch(sheetSvg(puzzle, {key: false}), /line-through/, 'The key can be left out');
  assert.deepEqual([...givenLetters(puzzle)], [['3', 'C'], ['4', 'E']]);
});

test('The solution sheet fills every cell and its key', () => {
  const puzzle = generated();
  const svg = sheetSvg(puzzle, {solution: generatedAnswer(puzzle)});
  assert.match(svg, /· solution/);
  const letters = [...svg.matchAll(/font-size="24"[^>]*>([^<]+)</g)].map(m => m[1]);
  assert.equal(letters.join(''), 'CATAETEN');
  assert.doesNotMatch(svg, /line-through/, 'No alphabet strip on the solution');
});

test('Answer letters a player enters are not printed as givens', () => {
  const puzzle = generated();
  puzzle.cells[1].letter = 'A'; puzzle.cells[1].prefilled = false;
  const letters = [...sheetSvg(puzzle).matchAll(/font-size="24"[^>]*>([^<]+)</g)].map(m => m[1]);
  assert.ok(!letters.includes('A'));
});

test('Answer check counts confirmed letters only and stops when the grid changes', () => {
  const puzzle = generated();
  let check = answerCheck(puzzle);
  assert.deepEqual({...check, wrong: check.wrong.length}, {right: 3, wrong: 0, empty: 5, total: 8, solved: false});
  puzzle.cells[1].letter = 'O';
  puzzle.cells[2].letter = 'T';
  check = answerCheck(puzzle);
  assert.deepEqual(check.wrong, [1]);
  assert.equal(answerCheckText(check), '5 of 8 cells filled: 4 right, 1 wrong (outlined in red). 3 cells still empty.');
  puzzle.suggestions = {solutions: [{letters: generatedAnswer(puzzle)}]};
  assert.equal(answerCheck(puzzle).right, 4, 'Suggestions are not counted');
  generatedAnswer(puzzle).forEach((letter, i) => { if (letter) puzzle.cells[i].letter = letter; });
  assert.equal(answerCheckText(answerCheck(puzzle)), 'Solved: all 8 letters match the answer.');
  puzzle.cells[0].number = '9';
  assert.equal(generatedAnswer(puzzle), null, 'A renumbered grid no longer matches its answer');
  assert.equal(answerCheck(puzzle), null);
  assert.equal(answerCheck(canonicalPuzzle({rows: 1, cols: 1, language: 'en', cells: [{}]})), null);
});

test('Generator summary states the single-answer result without overclaiming', () => {
  const {generatedSummary} = require('../static/state.js');
  const base = {givens: ['A', 'K', 'T'], stats: {words: 28, distinctLetters: 21, extraGivens: 1}};
  assert.equal(generatedSummary({...base, uniqueness: 'unique'}),
    'Generated 28 words using 21 letters, 3 given (A, K, T). 1 of the given letters was added to rule out other answers. Only one answer fits with the current dictionary.');
  assert.match(generatedSummary({...base, uniqueness: 'unconfirmed'}), /A single answer is not confirmed: the check stopped at its time limit\.$/);
  assert.equal(generatedSummary({givens: [], stats: {words: 4, distinctLetters: 5}, uniqueness: 'unchecked'}),
    'Generated 4 words using 5 letters, 0 given (none). Not checked for other answers.');
  assert.equal(generatedSummary({...base, stats: {...base.stats, included: 2}, uniqueness: 'unique', difficulty: 'easy', grade: 'easy'}),
    'Generated 28 words using 21 letters, 3 given (A, K, T). Both words you listed are included. 1 of the given letters was added to reach the difficulty. Only one answer fits with the current dictionary. Difficulty: Easy; it can be solved word by word.');
  assert.match(generatedSummary({...base, uniqueness: 'unique', difficulty: 'hard', grade: 'medium'}),
    /Difficulty: Medium; .* You asked for Hard; this was the closest after trying other starter letters\.$/);
});

test('The sheet prints the difficulty only when it is given', () => {
  const puzzle = generated();
  assert.match(sheetSvg(puzzle, {grade: 'medium'}), />Difficulty: Medium</);
  assert.doesNotMatch(sheetSvg(puzzle), /Difficulty/);
});

test('Word layout summary counts words the way the generator does', () => {
  const {layoutSummary, layoutSummaryText, meetsLayout} = require('../static/state.js');
  const rows = ['.....', '.#.#.', '.....', '.#.#.', '.....'];
  const puzzle = canonicalPuzzle({rows: 5, cols: 5, language: 'en', rules: {}, cells: rows.join('').split('').map(ch => ({black: ch === '#'}))});
  const summary = layoutSummary(puzzle);
  assert.deepEqual(summary, {words: 6, shortest: 5, longest: 5, loose: 0});
  assert.equal(layoutSummaryText(summary), 'This grid has 6 words of 5 letters.');
  assert.equal(meetsLayout(summary, {words: 6, shortest: 3, longest: 5}), true);
  assert.equal(meetsLayout(summary, {words: 6, shortest: 3, longest: 4}), false);
  puzzle.cells[6].black = false; puzzle.cells[1].black = true; puzzle.cells[5].black = true;
  assert.match(layoutSummaryText(layoutSummary(puzzle)), /1 letter cell is in no word\.$/);
  assert.equal(layoutSummaryText(layoutSummary(canonicalPuzzle({rows: 1, cols: 1, language: 'en', cells: [{black: true}]}))),
    'No words yet: draw black cells, or set a target and place them.');
});
