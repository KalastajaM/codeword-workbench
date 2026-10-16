"""The how-it-works page must describe the solver as it is.

Every figure the page states about the solver is tagged with data-fact and
checked here against app/solver.py. The page's JavaScript search port is run
against the real solver on its example puzzle. When one of these tests fails
after a solver change, update static/how-it-works.html (and its scripts) to
match, then this test.
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from app import language_model, solver, word_index
from app.dictionaries import DEMO

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / 'static' / 'how-it-works.html').read_text(encoding='utf-8')
SCRIPT = (ROOT / 'static' / 'how-it-works.js').read_text(encoding='utf-8')
SOURCE = (ROOT / 'app' / 'solver.py').read_text(encoding='utf-8')

ANSWER = 'SEAEARART'
NUMBERS = [1, 2, 3, 2, 3, 4, 3, 4, 5]


def source_numbers(pattern):
    """Numbers captured from a solver.py literal; fails when the code changed shape."""
    match = re.search(pattern, SOURCE)
    if not match:
        raise AssertionError(f'app/solver.py no longer matches {pattern!r}. The solver changed: '
                             'update static/how-it-works.html and this test.')
    return [float(x) for x in match.groups()]


def max_cell_number():
    def valid(n):
        cells = [dict(number=str(n), letter='')]
        return solver.validate(dict(rows=1, cols=1, cells=cells, language='en'))['valid']
    n = 1
    while valid(n + 1):
        n += 1
        if n > 10000: raise AssertionError('No upper limit on cell numbers.')
    return n


def expected_facts():
    temp_min, temp_span, temp_steps = source_numbers(r'temperature=([\d.]+)\+([\d.]+)\*\(1-step/(\d+)\)')
    (steps,) = source_numbers(r'for step in range\((\d+)\)')
    (penalty,) = source_numbers(r'delta=next_total-total-(\d+)\*\(next_violations')
    (strict_share,) = source_numbers(r'control\.node_limit = max\(1, full_nodes//(\d+)\)')
    (strict_time,) = source_numbers(r'max\(0, full_deadline-time\.monotonic\(\)\)\*([\d.]+)')
    growth_num, growth_den = source_numbers(r'next_cap = max\(best_cost \+ 1, best_cost \* (\d+) // (\d+)\)')
    (dive,) = source_numbers(r'dive_nodes = control\.node_limit - \(control\.node_limit - began\) // (\d+)')
    source_numbers(r'rng=random\.Random\((\d+)\)')  # the page says the seed is fixed
    assert temp_steps == steps, 'Annealing cooling length and run length differ.'
    assert 100 / strict_share == strict_time * 100, 'Strict search time and node shares differ.'
    words = DEMO['en'].split()
    return {
        'maxCellNumber': max_cell_number(),
        'MAX_CANDIDATES': solver.MAX_CANDIDATES,
        'MAX_SOLUTIONS': solver.MAX_SOLUTIONS,
        'MISSING_WORD_CANDIDATES': solver.MISSING_WORD_CANDIDATES,
        'MAX_FRAGMENTS': word_index.MAX_FRAGMENTS,
        'MAX_FRONTIER_CELLS': solver.MAX_FRONTIER_CELLS,
        'frontier9x9': max(4, solver.MAX_FRONTIER_CELLS // 81),
        'MAX_SECONDS': solver.MAX_SECONDS,
        'DEEP_SECONDS': solver.DEEP_SECONDS,
        'EXTENDED_SECONDS': solver.EXTENDED_SECONDS,
        'MAX_NODES': solver.MAX_NODES,
        'DEEP_NODES': solver.DEEP_NODES,
        'EXTENDED_NODES': solver.EXTENDED_NODES,
        'strictSharePercent': 100 / strict_share,
        'capGrowth': growth_num / growth_den,
        'diveShare': {2: 'half', 3: 'third', 4: 'quarter', 5: 'fifth'}.get(int(dive), f'1/{int(dive)}'),
        'tempStart': temp_min + temp_span,
        'tempEnd': temp_min,
        'annealSteps': steps,
        'violationPenalty': penalty,
        'demoThreeLetterWords': len({w for w in words if len(w) == 3}),
    }


def page_value(text):
    text = text.replace(',', '').strip()
    try: return float(text)
    except ValueError: return text


class HowItWorksFactsTests(unittest.TestCase):
    def test_every_stated_figure_matches_the_solver(self):
        facts = expected_facts()
        stated = re.findall(r'<span data-fact="([^"]+)">([^<]*)</span>', PAGE)
        self.assertTrue(stated)
        for key, text in stated:
            with self.subTest(fact=key):
                self.assertIn(key, facts, f'Unknown data-fact {key}; add it to expected_facts().')
                expected = facts[key]
                expected = float(expected) if isinstance(expected, (int, float)) else expected
                self.assertEqual(page_value(text), expected,
                                 f'how-it-works.html says {text!r} for {key}; the solver now gives {facts[key]!r}.')
        self.assertEqual(set(facts), {key for key, _ in stated}, 'Every checked fact should appear on the page.')

    def test_script_limits_match_the_solver(self):
        self.assertEqual(int(re.search(r'const SOLUTION_LIMIT=(\d+);', SCRIPT).group(1)), solver.MAX_SOLUTIONS)

    def test_example_words_and_scores_match_the_app(self):
        words = re.search(r"const WORDS='([^']*)'", SCRIPT).group(1).split(' ')
        self.assertEqual(words, DEMO['en'].split())
        scores = json.loads(re.sub(r'(\w+):', r'"\1":', re.search(r'const SCORE=(\{.*?\});', SCRIPT).group(1)))
        rules = {**solver.default_rules('en'), 'excludedLetters': {}, 'rejectedWords': {}}
        with language_model.use(solver.language_models_for(dict(language='en', useDictionary=True), words)):
            actual = {w: round(solver._score(w, 'en', rules), 2) for w in words if len(w) == 3}
        self.assertEqual(scores, actual)


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed to run the page script.')
class HowItWorksSearchTests(unittest.TestCase):
    def test_page_search_matches_solver_for_every_confirmed_set(self):
        runner = r"""
const fs = require('fs');
const {solve} = require(process.argv[1] + '/static/how-it-works-engine.js');
const page = fs.readFileSync(process.argv[1] + '/static/how-it-works.js', 'utf8');
const words = page.match(/const WORDS='([^']*)'/)[1].split(' ');
const score = JSON.parse(page.match(/const SCORE=(\{.*?\});/)[1].replace(/(\w+):/g, '"$1":'));
const puzzles = JSON.parse(fs.readFileSync(0, 'utf8'));
console.log(JSON.stringify(puzzles.map(p => {
  const run = solve(p, words, score);
  return {nodes: run.nodes, rounds: run.rounds, solutions: run.sols.map(s => s.join('')).sort()};
})));
"""
        puzzles = []
        for mask in range(1 << max(NUMBERS)):
            cells = [dict(number=n, letter=ANSWER[i] if mask >> (n - 1) & 1 and NUMBERS.index(n) == i else '')
                     for i, n in enumerate(NUMBERS)]
            puzzles.append(dict(rows=3, cols=3, cells=cells))
        output = subprocess.run(['node', '-e', runner, str(ROOT)], input=json.dumps(puzzles),
                                capture_output=True, text=True, check=True, timeout=60).stdout
        for puzzle, page in zip(puzzles, json.loads(output)):
            cells = [dict(number=str(c['number']), letter=c['letter']) for c in puzzle['cells']]
            result = solver.solve(dict(language='en', rows=3, cols=3, useDictionary=True, cells=cells), DEMO['en'].split())
            real = dict(nodes=result['stats']['nodes'], rounds=result['stats']['propagationRounds'],
                        solutions=sorted(''.join(s['letters']) for s in result['solutions']))
            with self.subTest(confirmed=''.join(c['letter'] or '.' for c in cells)):
                self.assertEqual(page, real, 'The page search port no longer matches app/solver.py; '
                                             'update static/how-it-works-engine.js.')


if __name__ == '__main__':
    unittest.main()
