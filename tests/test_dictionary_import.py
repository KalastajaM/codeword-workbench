import tempfile
import unittest
from app import dictionaries
from app.solver import solve
from app.candidates import find_candidates
from app.word_index import WordIndex


class DictionaryImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.large_words = ['W' + ''.join(chr(65 + (i // 26**j) % 26) for j in range(4))
                           for i in range(260000)] + ['CAT', 'ARE', 'TEN']

    def example(self):
        letters = 'CATARETEN'
        mapping = {letter: str(i + 1) for i, letter in enumerate('CATREN')}
        return dict(rows=3, cols=3, language='en', useDictionary=True, searchMode='deep',
                    cells=[dict(black=False, number=mapping[letter], letter='C' if i == 0 else '')
                           for i, letter in enumerate(letters)])

    def test_example_solves_with_dictionary_above_old_limit(self):
        result = solve(self.example(), self.large_words)
        self.assertTrue(result['solutions'], result['diagnostics'])
        self.assertEqual(result['solutions'][0]['letters'], list('CATARETEN'))
        self.assertEqual(result['stats']['dictionaryWordsIndexed'], 3)

    def test_selected_words_accept_dictionary_above_old_limit(self):
        result = find_candidates(self.example(), self.large_words, [0])
        self.assertIn('CAT', result['words'][0]['candidates'])
        self.assertEqual(result['stats']['dictionaryWords'], 3)

    def test_length_filter_keeps_only_exact_closed_lengths(self):
        slots = [dict(cells=[0, 1, 2], before=False, after=False),
                 dict(cells=list(range(5)), before=False, after=False)]
        index = WordIndex('en', ['AT', 'CAT', 'HOME', 'HOUSE', 'HOUSES'], lambda: None, slots=slots)
        self.assertEqual(dict(index.by_length), {3: ['CAT'], 5: ['HOUSE']})

    def test_open_fragment_keeps_longer_source_words(self):
        slots = [dict(cells=[0, 1], before=True, after=True)]
        index = WordIndex('en', ['A', 'AT', 'CAT', 'HOUSE'], lambda: None, slots=slots)
        self.assertEqual(set(index.by_length), {2, 3, 5})
        p = dict(rows=1, cols=2, language='en', useDictionary=True,
                 cells=[dict(letter='A', openBeforeAcross=True), dict(letter='T', openAfterAcross=True)])
        result = solve(p, ['BATH'])
        self.assertTrue(result['solutions'])
        self.assertEqual(find_candidates(p, ['BATH'], [0])['words'][0]['candidates'], ['AT'])

    def test_irrelevant_lengths_do_not_mean_empty_dictionary(self):
        result = solve(self.example(), ['HOUSE'])
        self.assertEqual(result['stats']['stopReason'], 'no_candidates')
        self.assertEqual(result['stats']['dictionaryWordsIndexed'], 0)
        self.assertEqual(find_candidates(self.example(), ['HOUSE'], [0])['status'], 'no_candidates_found')

    def test_large_dictionary_roundtrip_exceeds_old_limit(self):
        # Unique alphabetic words, generated rather than using personal vocabulary.
        words = ['W' + ''.join(chr(65 + (i // 26**j) % 26) for j in range(4))
                 for i in range(260000)]
        with tempfile.TemporaryDirectory() as folder:
            result = dictionaries.save_dictionary('en', words, folder)
            self.assertEqual(result['count'], len(words))
            self.assertEqual(dictionaries.get_dictionary('en', folder)['words'], sorted(words))
