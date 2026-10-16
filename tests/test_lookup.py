import unittest

from app.candidates import find_candidates
from app.lookup import parse_pattern, pattern_search
from test_solver import puzzle

WORDS = ['KAKAO', 'KATT', 'AKKA', 'ALLA', 'ABBA', 'KAKA', 'ANNA', 'OTTO', 'AXXK', 'HOUSE']


class LookupTests(unittest.TestCase):
    def test_parse_letters_numbers_and_wildcards(self):
        self.assertEqual(parse_pattern('en', 'A 12 12 K 5'),
                         [('letter', 'A'), ('number', '12'), ('number', '12'), ('letter', 'K'), ('number', '5')])
        self.assertEqual(parse_pattern('en', 'a12?k'), [('letter', 'A'), ('number', '12'), ('any', None), ('letter', 'K')])
        self.assertEqual(parse_pattern('sv', 'b å t'), [('letter', 'B'), ('letter', 'Å'), ('letter', 'T')])
        for bad in ('', 'A Å', 'A 0', 'A 100', 'A-B'):
            with self.assertRaises(ValueError):
                parse_pattern('en', bad)

    def test_word_lookup_reports_dictionary_and_pattern(self):
        p = puzzle(1, 3, [1, 2, 3])
        found = pattern_search(p, 'house', WORDS)
        self.assertEqual(found['kind'], 'word')
        self.assertTrue(found['inDictionary'])
        self.assertEqual(found['plausibility']['label'], 'typical')
        missing = pattern_search(p, 'XKQZ', WORDS)
        self.assertFalse(missing['inDictionary'])
        self.assertEqual(missing['plausibility']['label'], 'implausible')
        self.assertIn('no vowel', missing['plausibility']['reasons'])

    def test_numbers_repeat_letters_and_stay_distinct(self):
        p = puzzle(1, 3, [1, 2, 3])
        result = pattern_search(p, 'A 12 12 A', WORDS)
        self.assertEqual(result['kind'], 'pattern')
        # 12 cannot be A: typed letters belong to another number.
        self.assertEqual(sorted(result['candidates']), ['ABBA', 'AKKA', 'ALLA', 'ANNA'])
        self.assertTrue(all(result['candidateEvidence'][w]['inDictionary'] for w in result['candidates']))

    def test_puzzle_mappings_fix_numbers_and_claim_letters(self):
        p = puzzle(1, 3, [1, 2, 3])
        p['cells'][0]['letter'] = 'K'
        self.assertEqual(pattern_search(p, 'A 1 1 A', WORDS)['candidates'], ['AKKA'])
        claimed = pattern_search(p, 'A 2 2 A', WORDS)['candidates']
        self.assertNotIn('AKKA', claimed)
        self.assertIn('ALLA', claimed)
        free = pattern_search(p, 'A 2 2 A', WORDS, use_mappings=False)['candidates']
        self.assertIn('AKKA', free)

    def test_wildcard_and_generated_guesses_are_labelled(self):
        p = puzzle(1, 3, [1, 2, 3], useDictionary=False)
        result = pattern_search(p, 'A 12 12 ?', [])
        self.assertTrue(result['candidates'])
        evidence = result['candidateEvidence'][result['candidates'][0]]
        self.assertEqual(evidence['source'], 'generated')
        self.assertFalse(evidence['inDictionary'])

    def test_selected_word_candidates_carry_dictionary_evidence(self):
        p = puzzle(1, 4, [1, 2, 2, 1])
        result = find_candidates(p, WORDS, [0])
        evidence = result['words'][0]['candidateEvidence']
        self.assertEqual(set(evidence), set(result['words'][0]['candidates']))
        self.assertEqual(evidence['ABBA'], dict(source='dictionary', inDictionary=True))
        p['cells'][3]['openAfterAcross'] = True
        fragments = find_candidates(p, WORDS, [0])['words'][0]['candidateEvidence']
        self.assertEqual(fragments['ABBA']['source'], 'dictionary')


class WordSetCacheTests(unittest.TestCase):
    def test_cache_reloads_when_dictionary_changes(self):
        import os, tempfile
        from app.dictionaries import dictionary_word_set, save_dictionary
        with tempfile.TemporaryDirectory() as folder:
            words, word_set = dictionary_word_set('nl', folder)
            self.assertIn('HUIS', word_set)
            save_dictionary('nl', ['fiets'], folder)
            path = os.path.join(folder, 'dictionaries', 'nl.json')
            stat = os.stat(path)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
            words, word_set = dictionary_word_set('nl', folder)
            self.assertEqual(words, ['FIETS'])
            self.assertIs(dictionary_word_set('nl', folder)[1], word_set)


if __name__ == '__main__':
    unittest.main()
