const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

// The walkthrough page carries a port of the strict search; keep it in step with app/solver.py.
const html = fs.readFileSync(path.join(__dirname, '..', 'docs', 'solver-visualization.html'), 'utf8');
const engine = { exports: {} };
new Function('module', html.match(/<script id="engine">([\s\S]*?)<\/script>/)[1])(engine);
const { solve } = engine.exports;
const words = html.match(/const WORDS='([^']*)'/)[1].split(' ');
const score = JSON.parse(html.match(/const SCORE=(\{.*?\});/)[1].replace(/(\w+):/g, '"$1":'));
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
