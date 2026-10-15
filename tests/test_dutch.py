import tempfile
import unittest

from app.dictionaries import ALPHABETS, get_dictionary, save_dictionary
from app.solver import default_rules, solve, validate, _score


def dutch_puzzle(word):
    return dict(rows=1, cols=len(word), language='nl', useDictionary=True,
                cells=[dict(black=False, number='', letter=letter) for letter in word])


class DutchTests(unittest.TestCase):
    def test_dutch_dictionary_is_separate_and_has_demo(self):
        with tempfile.TemporaryDirectory() as folder:
            demo = get_dictionary('nl', folder)
            self.assertIn('HUIS', demo['words'])
            self.assertIn('demonstration', demo['source'])
            save_dictionary('nl', ['huis', 'dijk', 'fiets'], folder)
            self.assertEqual(get_dictionary('nl', folder)['words'], ['DIJK', 'FIETS', 'HUIS'])
            self.assertIn('CAT', get_dictionary('en', folder)['words'])

    def test_ij_uses_two_cells(self):
        p = dutch_puzzle('DIJK')
        self.assertTrue(validate(p)['valid'])
        result = solve(p, ['DIJK'])
        self.assertEqual(result['solutions'][0]['letters'], list('DIJK'))
        self.assertTrue(result['solutions'][0]['words'][0]['verified'])
        p['cells'][1]['letter'] = 'IJ'
        self.assertFalse(validate(p)['valid'])
        p['cells'][1]['letter'] = 'Ĳ'
        self.assertFalse(validate(p)['valid'])

    def test_dutch_uses_a_to_z_and_its_own_preferences(self):
        self.assertEqual(ALPHABETS['nl'], 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        rules = default_rules('nl')
        self.assertGreater(_score('FIETS', 'nl', rules), _score('FFFFF', 'nl', rules))
        self.assertNotEqual(_score('DIJK', 'nl', rules), _score('DIJK', 'en', rules))
        p = dutch_puzzle('Ö')
        self.assertFalse(validate(p)['valid'])

    def test_dutch_generated_results_are_unverified_without_finnish_diagnostics(self):
        p = dutch_puzzle('DIJK'); p['useDictionary'] = False
        p['cells'][0]['letter'] = ''
        result = solve(p, [])
        self.assertTrue(result['solutions'])
        self.assertFalse(result['solutions'][0]['words'][0]['verified'])
        self.assertFalse(any('Finnish' in d for d in result['diagnostics']))

    def test_dutch_variant_heuristic_path(self):
        p = dutch_puzzle('FIETS'); p['useDictionary'] = False
        p['cells'][0]['letter'] = ''
        p['rules'] = dict(maxLettersPerNumber=2)
        result = solve(p, [])
        self.assertTrue(result['solutions'])
        self.assertFalse(result['solutions'][0]['words'][0]['verified'])

    def test_english_generated_diagnostics_do_not_reference_finnish(self):
        p = dutch_puzzle('CAT'); p.update(language='en', useDictionary=False)
        result = solve(p, [])
        self.assertFalse(any('Finnish' in d for d in result['diagnostics']))
