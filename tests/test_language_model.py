import unittest
from unittest.mock import patch

from app import language_model as lm
from app.candidates import find_candidates
from app.solver import solve, _score, default_rules
from test_solver import puzzle


class LanguageModelTests(unittest.TestCase):
    def test_bundled_models_prefer_real_words(self):
        for language, real, junk in (('en', 'HOUSE', 'XKCDQ'), ('fi', 'TALOSSA', 'STRKV'), ('sv', 'BILARNA', 'QXZKV')):
            self.assertIsNotNone(lm.bundled(language))
            self.assertEqual(lm.plausibility(real, language)['label'], 'typical')
            self.assertEqual(lm.plausibility(junk, language)['label'], 'implausible')
            rules = default_rules(language)
            self.assertGreater(_score(real, language, rules), _score(junk, language, rules))

    def test_rules_explain_findings_without_rejecting(self):
        self.assertIn('Q not followed by U', lm.plausibility('QAT', 'en')['reasons'])
        self.assertIn('no vowel', lm.plausibility('PFFT', 'en')['reasons'])
        harmony = lm.plausibility('TALOSSÄ', 'fi')
        self.assertIn('ending does not follow vowel harmony', harmony['reasons'])
        self.assertNotEqual(harmony['label'], 'typical')
        # Compounds may mix vowel groups; only a soft reason is recorded.
        self.assertEqual(lm.plausibility('TYÖPAIKKA', 'fi')['label'], 'typical')

    def test_open_boundaries_do_not_penalize_missing_word_ends(self):
        model = lm.bundled('en')
        self.assertGreater(model.score('THR', after=True), model.score('THR'))
        self.assertNotIn('no vowel', lm.plausibility('STR', 'en', before=True, after=True)['reasons'])

    def test_dutch_model_and_ee_umlaut_spelling(self):
        self.assertIsNotNone(lm.bundled('nl'))
        for word in ('FIETSEN', 'GEZELLIGHEID', 'IJSBEER', 'IDEEEN'):
            self.assertEqual(lm.plausibility(word, 'nl')['label'], 'typical', word)
        self.assertEqual(lm.plausibility('QXZKV', 'nl')['label'], 'implausible')
        self.assertIn('three or more identical letters in a row', lm.plausibility('EEEE', 'nl')['reasons'])

    def test_language_without_bundled_model_trains_from_word_list(self):
        stems = ('FIETS', 'HUIS', 'BOOM', 'KAT', 'HOND', 'WATER', 'BOEK', 'STRAAT', 'SCHOOL', 'DIJK')
        suffixes = ('', 'EN', 'JE', 'JES', 'ER', 'S', 'ING', 'DE', 'TE', 'LIJK', 'BAAR', 'IG', 'IGE')
        words = [stem + suffix for stem in stems for suffix in suffixes]
        with patch.dict(lm._bundled, {'nl': None}), patch.object(lm, 'ADAPT_MIN_WORDS', 50):
            self.assertEqual(lm.plausibility('FIETS', 'nl')['label'], 'unassessed')
            model = lm.adapted('nl', words)
            self.assertIsNotNone(model)
            with lm.use({'nl': model}):
                self.assertEqual(lm.plausibility('HUISJE', 'nl')['label'], 'typical')
                self.assertEqual(lm.plausibility('QXZKV', 'nl')['label'], 'implausible')
        lm._adapted.clear()

    def test_small_lists_keep_bundled_model(self):
        self.assertIs(lm.adapted('en', ['CAT', 'DOG']), lm.bundled('en'))

    def test_solutions_carry_plausibility_and_stay_unverified(self):
        p = puzzle(1, 5, [1, 2, 3, 4, 5], useDictionary=False)
        r = solve(p, [])
        self.assertTrue(r['solutions'])
        word = r['solutions'][0]['words'][0]
        self.assertFalse(word['verified'])
        self.assertIn(word['plausibility']['label'], ('typical', 'unusual', 'implausible'))
        self.assertTrue(any('not a verified word' in d for d in r['diagnostics']))

    def test_dictionary_mode_flags_implausible_unsupported_words(self):
        p = puzzle(1, 4, [1, 2, 3, 4], allowUnknownWords=True)
        for cell, letter in zip(p['cells'], 'XQZK'):
            cell['letter'] = letter
        r = solve(p, ['CAT'])
        word = r['solutions'][0]['words'][0]
        self.assertFalse(word['verified'])
        self.assertEqual(word['plausibility']['label'], 'implausible')
        self.assertTrue(any('implausible English letter patterns' in d and 'XQZK' in d for d in r['diagnostics']))

    def test_selected_word_candidates_include_plausibility(self):
        p = puzzle(1, 3, [1, 2, 3])
        r = find_candidates(p, ['CAT', 'TAC', 'XQZ'], [0])
        details = r['words'][0]['candidatePlausibility']
        self.assertEqual(set(details), set(r['words'][0]['candidates']))
        self.assertEqual(r['words'][0]['candidates'][0], 'CAT')
        self.assertEqual(details['XQZ']['label'], 'implausible')


if __name__ == '__main__':
    unittest.main()
