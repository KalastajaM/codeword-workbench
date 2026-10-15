import unittest
from types import SimpleNamespace

from app.candidates import find_candidates
from app.eliminations import check, suggest
from app.lookup import pattern_search
from app.solver import solve, suggested_eliminations, validate, _rules, _slots
from test_solver import puzzle


def letters(result):
    return {''.join(s['letters']) for s in result['solutions']}


class RuledOutLetterTests(unittest.TestCase):
    def test_solver_never_assigns_a_ruled_out_letter(self):
        p = puzzle(1, 3, [1, 2, 1], {0: 'D'})
        self.assertEqual(letters(solve(p, ['DAD', 'DID'])), {'DAD', 'DID'})
        p['eliminations'] = {'2': ['A']}
        self.assertEqual(letters(solve(p, ['DAD', 'DID'])), {'DID'})

    def test_missing_word_search_respects_ruled_out_letters(self):
        p = puzzle(2, 2, [1, 2, 3, 4], allowUnknownWords=True, eliminations={'2': ['T']})
        result = solve(p, ['AT', 'TO', 'AN', 'NO'])
        self.assertTrue(result['solutions'])
        self.assertTrue(all(s['letters'][1] != 'T' for s in result['solutions']))

    def test_dictionary_free_search_respects_ruled_out_letters(self):
        p = puzzle(1, 3, [1, 2, 3], useDictionary=False, eliminations={'2': list('AEIOU')})
        result = solve(p, [])
        self.assertTrue(result['solutions'])
        self.assertTrue(all(s['letters'][1] not in 'AEIOU' for s in result['solutions']))

    def test_selected_word_candidates_and_patterns_respect_ruled_out_letters(self):
        p = puzzle(1, 3, [1, 2, 1], {0: 'D'}, eliminations={'2': ['A']})
        found = find_candidates(p, ['DAD', 'DID'], [0])['words'][0]['candidates']
        self.assertEqual(found, ['DID'])
        self.assertEqual(pattern_search(p, 'D 2 D', ['DAD', 'DID'])['candidates'], ['DID'])
        self.assertIn('DAD', pattern_search(p, 'D 2 D', ['DAD', 'DID'], use_mappings=False)['candidates'])
        # Stand-in numbers for typed letters must not pick up another number's rules.
        self.assertCountEqual(pattern_search(p, 'D ? D', ['DAD', 'DID'])['candidates'], ['DAD', 'DID'])

    def test_confirmed_ruled_out_letter_is_a_conflict(self):
        p = puzzle(1, 2, [1, 2], {0: 'A'}, eliminations={'1': ['A']})
        result = validate(p)
        self.assertFalse(result['valid'])
        self.assertIn('ruled out', result['conflicts'][0])

    def test_check_normalizes_and_rejects_bad_values(self):
        p = puzzle(1, 2, [1, 2], eliminations={'01': ['w', 'W'], '2': []})
        check(p, 'en')
        self.assertEqual(p['eliminations'], {'1': ['W']})
        for bad in ({'0': ['A']}, {'1': 'A'}, {'1': ['AB']}, {'1': ['Ä']}, ['A']):
            with self.assertRaises(ValueError):
                check(puzzle(1, 2, [1, 2], eliminations=bad), 'en')


class SuggestedEliminationTests(unittest.TestCase):
    def dutch(self):
        p = puzzle(1, 6, [1, 1, 7, 20, 7, 6], {2: 'K', 4: 'K'})
        p['language'] = 'nl'
        return p

    def test_runs_absent_from_the_language_are_suggested(self):
        suggestions = suggested_eliminations(self.dutch())
        twenty = {s['letter']: s['run'] for s in suggestions if s['number'] == '20'}
        self.assertEqual(twenty['W'], 'KWK')
        self.assertNotIn('E', twenty)
        self.assertNotIn('A', twenty)
        # Confirmed numbers and their letters are not suggested.
        self.assertFalse(any(s['number'] == '7' or s['letter'] == 'K' for s in suggestions))

    def test_ruled_out_letters_and_variant_mappings_are_skipped(self):
        p = self.dutch()
        p['eliminations'] = {'20': ['W']}
        self.assertFalse(any(s['number'] == '20' and s['letter'] == 'W' for s in suggested_eliminations(p)))
        p['rules']['maxLettersPerNumber'] = 2
        self.assertEqual(suggested_eliminations(p), [])

    def test_a_context_that_excludes_every_letter_is_ignored(self):
        # Pairs KA, AK, KE, EK exist but no triple: K?K would rule out every
        # letter, so only the pair runs count.
        p = puzzle(1, 3, [1, 2, 1], {0: 'K'})
        p['cells'][0]['openBeforeAcross'] = p['cells'][2]['openAfterAcross'] = True
        rules = _rules(p)
        model = SimpleNamespace(counts={'KA': 1, 'AK': 1, 'KE': 1, 'EK': 1})
        found = {s['letter']: s['run'] for s in suggest(p, _slots(p), ['K', '', 'K'], rules, model)}
        self.assertNotIn('A', found)
        self.assertNotIn('E', found)
        self.assertEqual(found['B'], 'KB')


class RejectedWordTests(unittest.TestCase):
    def test_solver_skips_a_rejected_word_in_its_slot_only(self):
        p = puzzle(1, 3, [1, 2, 1], {0: 'D'})
        p['rejectedWords'] = [dict(start=0, direction='Across', word='DAD')]
        self.assertEqual(letters(solve(p, ['DAD', 'DID'])), {'DID'})
        p['rejectedWords'] = [dict(start=0, direction='Down', word='DAD')]
        self.assertEqual(letters(solve(p, ['DAD', 'DID'])), {'DAD', 'DID'})

    def test_rejected_word_formed_by_crossings_is_excluded(self):
        p = puzzle(2, 2, [1, 2, 3, 4], allowUnknownWords=True,
                   rejectedWords=[dict(start=2, direction='Across', word='TO')])
        result = solve(p, ['AT', 'TO', 'AN', 'NO'])
        for s in result['solutions']:
            self.assertNotEqual(''.join(s['letters'][2:]), 'TO')

    def test_dictionary_free_search_skips_rejected_words(self):
        p = puzzle(1, 2, [1, 2], {0: 'O'}, useDictionary=False)
        first = solve(p, [])['solutions'][0]['letters']
        p['rejectedWords'] = [dict(start=0, direction='Across', word=''.join(first))]
        self.assertTrue(all(s['letters'] != first for s in solve(p, [])['solutions']))

    def test_selected_word_candidates_skip_rejected_words(self):
        p = puzzle(1, 3, [1, 2, 1], {0: 'D'}, rejectedWords=[dict(start=0, direction='Across', word='DID')])
        self.assertEqual(find_candidates(p, ['DAD', 'DID'], [0])['words'][0]['candidates'], ['DAD'])

    def test_confirmed_rejected_word_is_a_conflict(self):
        p = puzzle(1, 2, [1, 2], {0: 'A', 1: 'T'}, rejectedWords=[dict(start=0, direction='Across', word='AT')])
        self.assertFalse(validate(p)['valid'])
        p['rejectedWords'] = [dict(start=0, direction='Across', word='TO')]
        self.assertTrue(validate(p)['valid'])

    def test_check_validates_entries(self):
        p = puzzle(1, 2, [1, 2], rejectedWords=[dict(start=0, direction='Across', word='at'),
                                                 dict(start=0, direction='Across', word='AT')])
        check(p, 'en')
        self.assertEqual(p['rejectedWords'], [dict(start=0, direction='Across', word='AT')])
        stale = puzzle(1, 2, [1, 2], rejectedWords=[dict(start=5, direction='Across', word='AT')])
        check(stale, 'en')
        self.assertEqual(stale['rejectedWords'], [])
        for bad in ([dict(start=-1, direction='Across', word='AT')], [dict(start=0, direction='Diagonal', word='AT')],
                    [dict(start=0, direction='Across', word='A')], [dict(start=0, direction='Across', word='A1')], {}):
            with self.assertRaises(ValueError):
                check(puzzle(1, 2, [1, 2], rejectedWords=bad), 'en')


if __name__ == '__main__':
    unittest.main()
