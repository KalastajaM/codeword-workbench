const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

// The how-it-works page carries a port of the strict search; keep it in step with app/solver.py.
const { solve } = require('../static/how-it-works-engine.js');
const page = fs.readFileSync(path.join(__dirname, '..', 'static', 'how-it-works.js'), 'utf8');
const words = page.match(/const WORDS='([^']*)'/)[1].split(' ');
const score = JSON.parse(page.match(/const SCORE=(\{.*?\});/)[1].replace(/(\w+):/g, '"$1":'));
const numbers = [1, 2, 3, 2, 3, 4, 3, 4, 5];

function puzzle(confirmed) {
  return { rows: 3, cols: 3, cells: numbers.map((number, i) => ({ number, letter: confirmed[i] || '' })) };
}

test('starting example matches the Python solver', () => {
  const run = solve(puzzle({ 2: 'A' }), words, score);
  assert.deepStrictEqual(run.sols.map(s => s.join('')), ['SEAEARART']);
  assert.strictEqual(run.nodes, 4);
  assert.strictEqual(run.rounds, 6);
  assert.deepStrictEqual(run.trace.filter(t => t.type === 'branch').map(t => t.word), ['TEA', 'SEA', 'ERA']);
});

test('without confirmed letters the search backtracks more', () => {
  const run = solve(puzzle({}), words, score);
  assert.ok(run.trace.filter(t => t.type === 'dead').length > 2);
  assert.ok(run.sols.some(s => s.join('') === 'SEAEARART'));
});

test('page loads its scripts as files, as the app CSP requires', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'static', 'how-it-works.html'), 'utf8');
  assert.ok(!/<script(?![^>]*\bsrc=)[^>]*>/.test(html));
  assert.ok(!/https?:\/\//.test(html.replace(/<p[\s\S]*?<\/p>/g, '')));
});
