"""The bundled original puzzles stay well formed and match the in-app showcase."""
import json
import re
import unittest
from pathlib import Path

from app.solver import _slots

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'scripts' / 'benchmark_puzzles.json').read_text(encoding='utf-8'))
SAMPLES = (ROOT / 'static' / 'samples.js').read_text(encoding='utf-8')


class BenchmarkPuzzleTests(unittest.TestCase):
    def test_showcase_is_the_first_benchmark_puzzle(self):
        answer = re.findall(r"'([A-Z#]{13})'", re.search(r'answer:\[(.*?)\]', SAMPLES, re.S).group(1))
        self.assertEqual(DATA['puzzles'][0]['name'], 'showcase')
        self.assertEqual(DATA['puzzles'][0]['rows'], answer)
        key = dict(re.findall(r'([A-Z]):(\d+)', re.search(r'key:\{(.*?)\}', SAMPLES).group(1)))
        self.assertEqual(set(key), set(''.join(answer)) - {'#'}, 'Every answer letter has a number')
        self.assertEqual(len(set(key.values())), len(key), 'Numbers are distinct')

    def test_every_open_cell_is_in_a_word_of_three_or_more(self):
        for puzzle in DATA['puzzles']:
            rows = puzzle['rows']
            with self.subTest(puzzle=puzzle['name']):
                self.assertTrue(all(len(row) == len(rows[0]) and set(row) <= set('ABCDEFGHIJKLMNOPQRSTUVWXYZ#') for row in rows))
                text = ''.join(rows)
                cells = [dict(black=ch == '#', number='', letter='') for ch in text]
                slots = _slots(dict(rows=len(rows), cols=len(rows[0]), cells=cells))
                self.assertTrue(all(len(s['cells']) >= 3 for s in slots))
                covered = {i for s in slots for i in s['cells']}
                self.assertEqual(covered, {i for i, ch in enumerate(text) if ch != '#'})


if __name__ == '__main__':
    unittest.main()
