import tempfile
import unittest

from app import language_model as lm
from app.dictionaries import ALPHABETS, get_dictionary, save_dictionary
from app.solver import default_rules, solve, validate, _score


def swedish_puzzle(word):
    return dict(rows=1, cols=len(word), language='sv', useDictionary=True,
                cells=[dict(black=False, number='', letter=letter) for letter in word])


class SwedishTests(unittest.TestCase):
    def test_swedish_alphabet_includes_aring_adiaeresis_odiaeresis(self):
        self.assertEqual(ALPHABETS['sv'], 'ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ')
        self.assertTrue(validate(swedish_puzzle('BÅT'))['valid'])
        self.assertTrue(validate(swedish_puzzle('ÖGA'))['valid'])
        p = swedish_puzzle('ÜBER')
        self.assertFalse(validate(p)['valid'])

    def test_swedish_dictionary_is_separate_and_has_demo(self):
        with tempfile.TemporaryDirectory() as folder:
            demo = get_dictionary('sv', folder)
            self.assertIn('HUS', demo['words'])
            self.assertIn('demonstration', demo['source'])
            save_dictionary('sv', ['hus', 'båt', 'öga'], folder)
            self.assertEqual(get_dictionary('sv', folder)['words'], ['BÅT', 'HUS', 'ÖGA'])
            self.assertNotIn('BÅT', get_dictionary('fi', folder)['words'])

    def test_dictionary_solve_marks_swedish_words_verified(self):
        p = swedish_puzzle('BÅT')
        p['cells'][1]['letter'] = ''
        p['cells'][1]['number'] = '1'
        result = solve(p, ['BÅT', 'BIT'])
        texts = {s['words'][0]['text'] for s in result['solutions']}
        self.assertEqual(texts, {'BÅT', 'BIT'})
        self.assertTrue(all(s['words'][0]['verified'] for s in result['solutions']))

    def test_generated_swedish_results_are_unverified_and_not_finnish(self):
        p = swedish_puzzle('KATT'); p['useDictionary'] = False
        p['cells'][0]['letter'] = ''
        result = solve(p, [])
        self.assertTrue(result['solutions'])
        self.assertFalse(result['solutions'][0]['words'][0]['verified'])
        self.assertFalse(any('Finnish' in d for d in result['diagnostics']))
        self.assertTrue(any('Swedish' in d for d in result['diagnostics']))

    def test_swedish_rules_and_scores(self):
        rules = default_rules('sv')
        self.assertGreater(_score('STJÄRNA', 'sv', rules), _score('ÅÅÅÅÅ', 'sv', rules))
        # No vowel harmony in Swedish: mixed vowels are not a finding.
        reasons = lm.plausibility('FÅGELSÅNG', 'sv')['reasons']
        self.assertFalse(any('harmony' in r or 'back' in r for r in reasons))
        self.assertIn('no vowel', lm.plausibility('SKTRP', 'sv')['reasons'])


if __name__ == '__main__':
    unittest.main()
