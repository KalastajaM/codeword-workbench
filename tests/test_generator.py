"""Filling a drawn grid with dictionary words and numbering it as a codeword."""
import unittest

from app.generator import generate, layout, options

WORDS = ('CAT ACE TEA ATE EAT TAN NET TEN ANT ONE TOE NOT TON CAN CONE CANE ACNE NOTE TONE '
         'COAT TACO ONCE OCEAN CANOE TENON').split()


def grid(rows, **extra):
    """Rows of '#' (black), '.' (open), a digit (number) or a letter (given letter)."""
    cells = []
    for ch in ''.join(rows):
        cells.append(dict(black=ch == '#', number=ch if ch.isdigit() else '', letter=ch if ch.isalpha() else ''))
    return dict(rows=len(rows), cols=len(rows[0]), language='en', cells=cells, rules=extra.pop('rules', {}), **extra)


def words_in(puzzle, answer):
    return [''.join(answer[i] for i in slot) for slot in layout(puzzle)]


class LayoutTests(unittest.TestCase):
    def test_slots_cover_every_letter_cell(self):
        p = grid(['...', '.#.', '...'])
        self.assertEqual(len(layout(p)), 4)

    def test_cell_outside_any_word_is_reported_with_its_position(self):
        with self.assertRaisesRegex(ValueError, 'row 1, column 1'):
            layout(grid(['.#.', '#..', '...']))

    def test_open_word_ends_and_variant_rules_are_rejected(self):
        p = grid(['...'])
        p['cells'][0]['openBeforeAcross'] = True
        with self.assertRaisesRegex(ValueError, 'closed word ends'):
            layout(p)
        with self.assertRaisesRegex(ValueError, 'standard rules'):
            layout(grid(['...'], rules={'maxLettersPerNumber': 2}))
        with self.assertRaisesRegex(ValueError, 'standard rules'):
            layout(grid(['...'], rules={'uniqueLetters': False}))

    def test_contradicting_given_numbers_and_letters_are_rejected(self):
        p = grid(['...'])
        p['cells'][0].update(number='1', letter='C'); p['cells'][2].update(number='1', letter='T')
        with self.assertRaisesRegex(ValueError, 'Number 1 has two different letters'):
            layout(p)
        p['cells'][2].update(number='2', letter='C')
        with self.assertRaisesRegex(ValueError, 'Letter C is given to two numbers'):
            layout(p)

    def test_empty_grid_and_bad_options(self):
        with self.assertRaisesRegex(ValueError, 'at least one word'):
            layout(grid(['#.#']))
        for bad in [dict(starters=11), dict(starters=True), dict(seconds=0), dict(seconds=True), dict(seed='1'), dict(unique=1), []]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                options(bad)


class FillTests(unittest.TestCase):
    def assert_codeword(self, puzzle, result):
        self.assertEqual(result['status'], 'generated')
        answer, cells = result['answer'], result['cells']
        found = words_in(puzzle, answer)
        self.assertTrue(set(found) <= set(WORDS), found)
        self.assertEqual(len(found), len(set(found)), 'No word is used twice')
        number_of = {}
        for cell, letter in zip(cells, answer):
            if cell['black']:
                self.assertEqual(letter, '')
                continue
            self.assertEqual(number_of.setdefault(letter, cell['number']), cell['number'], 'One number per letter')
        self.assertEqual(len(set(number_of.values())), len(number_of), 'One letter per number')
        self.assertEqual(sorted(int(n) for n in number_of.values()), list(range(1, len(number_of) + 1)))
        for cell, letter in zip(cells, answer):
            self.assertIn(cell['letter'], ('', letter))
            self.assertEqual(cell['letter'] != '', letter in result['givens'] if not cell['black'] else False)

    def test_fill_uses_dictionary_words_and_numbers_each_letter_once(self):
        p = grid(['....', '.#.#', '....'])
        result = generate(p, WORDS, seed=3, starters=1)
        self.assert_codeword(p, result)
        self.assertEqual(len(result['givens']), 1)
        self.assertEqual(result['stats']['seed'], 3)

    def test_same_seed_gives_same_puzzle(self):
        p = grid(['....', '.#.#', '....'])
        self.assertEqual(generate(p, WORDS, seed=7)['answer'], generate(p, WORDS, seed=7)['answer'])

    def test_given_letters_stay_and_count_as_givens(self):
        p = grid(['O..', '.#.', '...'])
        result = generate(p, WORDS + ['OAT', 'EON'], seed=1, starters=0)
        self.assertEqual(result['status'], 'generated', result)
        self.assertEqual(result['answer'][0], 'O')
        self.assertEqual(result['givens'], ['O'])
        self.assertTrue(all(c['letter'] == 'O' for c, a in zip(result['cells'], result['answer']) if a == 'O'),
                        'A given letter shows in every cell of its number')

    def test_fixed_numbers_are_kept_and_force_equal_or_distinct_letters(self):
        p = grid(['1..1', '#.#.', '2..2'])
        words = ['TENT', 'NOON', 'TOOT', 'EVE', 'TEN', 'NET', 'ONE', 'EON', 'NOT', 'TON', 'NEON', 'NOTE', 'TOTE']
        result = generate(p, words, seed=2, starters=0)
        self.assertEqual(result['status'], 'generated', result)
        cells, answer = result['cells'], result['answer']
        self.assertEqual([cells[i]['number'] for i in (0, 3, 8, 11)], ['1', '1', '2', '2'])
        self.assertEqual(answer[0], answer[3]); self.assertEqual(answer[8], answer[11])
        self.assertNotEqual(answer[0], answer[8])

    def test_two_numbers_in_one_word_never_share_a_letter(self):
        p = grid(['12.'])
        result = generate(p, ['TOO', 'EEL', 'CAT'], seed=0, starters=0)
        self.assertEqual(words_in(p, result['answer']), ['CAT'])

    def test_impossible_fill_is_reported_as_exhausted(self):
        result = generate(grid(['...', '.#.', '...']), ['CAT', 'DOG'], seed=0)
        self.assertEqual(result['status'], 'no_fill')
        self.assertTrue(result['stats']['exhaustive'])
        missing = generate(grid(['......']), WORDS, seed=0)
        self.assertEqual(missing['status'], 'no_fill')
        self.assertEqual(missing['diagnostics'], ['The dictionary has no words of length 6.'])

    def test_second_answer_is_ruled_out_with_an_extra_given_letter(self):
        p = grid(['...'])
        result = generate(p, ['CAT', 'COT'], seed=0, starters=0)
        self.assertEqual(result['uniqueness'], 'unique')
        self.assertEqual(result['stats']['extraGivens'], 1)
        self.assertEqual(result['givens'], [result['answer'][1]], 'The given letter is the one the answers differ in')
        unchecked = generate(p, ['CAT', 'COT'], seed=0, starters=0, unique=False)
        self.assertEqual((unchecked['uniqueness'], unchecked['givens']), ('unchecked', []))

    def test_answer_count_matches_the_solver(self):
        from app import solver
        from app.generator import _Filler, _numbered
        import random
        p = grid(['....', '.#.#', '....'])
        slots = layout(p)
        limit, solver.MAX_CANDIDATES = solver.MAX_CANDIDATES, 10 ** 6  # every candidate, as the benchmark script does
        try:
            for seed in range(6):
                result = generate(p, WORDS, seed=seed, starters=seed % 2, unique=False)
                numbered = dict(p, cells=result['cells'], rules=solver.default_rules('en'), useDictionary=True,
                                allowUnknownWords=False, searchMode='extended')
                found, reason = _Filler(numbered, slots, WORDS, random.Random(0), float('inf'), lambda: False,
                                        lambda update: None, distinct=False).count(50)
                solved = solver.solve(numbered, WORDS)
                with self.subTest(seed=seed):
                    self.assertEqual(reason, 'search_exhausted')
                    self.assertTrue(solved['stats']['exhaustive'])
                    self.assertEqual(sorted(''.join(f[i] for i in sorted(f)) for f in found),
                                     sorted(''.join(l for l in s['letters'] if l) for s in solved['solutions']))
        finally:
            solver.MAX_CANDIDATES = limit

    def test_cancel_stops_the_search(self):
        result = generate(grid(['....', '.#.#', '....']), WORDS, seed=0, cancel=lambda: True)
        self.assertEqual(result['status'], 'cancelled')
        self.assertFalse(result['stats']['exhaustive'])


if __name__ == '__main__':
    unittest.main()


class GenerateHTTPTests(unittest.TestCase):
    def setUp(self):
        import tempfile, threading
        from app.dictionaries import save_dictionary
        from app.server import make_server
        self.temp = tempfile.TemporaryDirectory()
        save_dictionary('en', WORDS, self.temp.name)
        self.server = make_server(0, self.temp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def request(self, path, body=None, method=None):
        import http.client, json
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request(method or ('POST' if body is not None else 'GET'), path,
                     json.dumps(body) if body is not None else None, {'Content-Type': 'application/json'})
        response = conn.getresponse(); result = (response.status, json.loads(response.read())); conn.close()
        return result

    def test_job_fills_grid_from_the_saved_dictionary(self):
        import time
        p = dict(grid(['....', '.#.#', '....']), name='Drawn', useDictionary=True)
        code, job = self.request('/api/generate-jobs', dict(puzzle=p, options=dict(starters=0, seed=5, unique=False)))
        self.assertEqual(code, 202, job)
        until = time.monotonic() + 5
        while job['status'] == 'running' and time.monotonic() < until:
            time.sleep(.02)
            code, job = self.request('/api/generate-jobs/' + job['id'])
        result = job['result']
        self.assertEqual(result['status'], 'generated')
        self.assertEqual(result['givens'], [])
        self.assertEqual(result['uniqueness'], 'unchecked')
        self.assertEqual(result['diagnostics'], [], 'A saved dictionary needs no demonstration-list note')
        self.assertTrue(set(words_in(p, result['answer'])) <= set(WORDS))

    def test_unfillable_layout_and_bad_options_fail_before_a_job_starts(self):
        code, body = self.request('/api/generate-jobs', dict(puzzle=grid(['.#.', '#..', '...'])))
        self.assertEqual(code, 400)
        self.assertIn('not part of any word', body['error'])
        code, body = self.request('/api/generate-jobs', dict(puzzle=grid(['...']), options=dict(starters=-1)))
        self.assertEqual(code, 400)


class StoredAnswerTests(unittest.TestCase):
    def test_generated_answer_is_validated_and_kept_from_the_solver(self):
        from app.server import check_puzzle
        from app.solve_jobs import SolveJobs
        import threading
        p = grid(['...'])
        p['generated'] = dict(answer=['C', 'A', 'T'], numbers=['1', '2', '3'], seed=4)
        check_puzzle(p)
        for bad in [dict(answer=['C', 'A'], numbers=['1', '2', '3']), dict(answer=['C', 'A', 'TT'], numbers=['1', '2', '3']),
                    dict(answer=['C', 'A', 'T'], numbers=['1', '2', '100']), dict(answer=['C', 'A', 'T'], numbers=['1', '2', '3'], seed='x'), []]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                check_puzzle(dict(p, generated=bad))
        seen = []
        jobs = SolveJobs(lambda puzzle, **_: seen.append(puzzle) or dict(status='complete'), threading.BoundedSemaphore(1))
        job = jobs.start(p)
        jobs.jobs[job['id']]['thread'].join(2)
        self.assertNotIn('generated', seen[0])
