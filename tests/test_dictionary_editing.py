import tempfile
import unittest

from app.dictionaries import (active_words, dictionary_state, edit_dictionary, get_disabled,
                              import_dictionary, save_dictionary, search_dictionary)


class DictionaryEditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = self.temp.name
        save_dictionary('sv', ['katt', 'katten', 'kattor', 'hund', 'räkning', 'ö'], self.folder)

    def tearDown(self):
        self.temp.cleanup()

    def words(self, query, status='all'):
        return [e['word'] for e in search_dictionary('sv', self.folder, query, status)['words']]

    def test_search_prefix_and_wildcards(self):
        self.assertEqual(self.words('KAT'), ['KATT', 'KATTEN', 'KATTOR'])
        self.assertEqual(self.words('K?TT'), ['KATT'])
        self.assertEqual(self.words('K?TT*'), ['KATT', 'KATTEN', 'KATTOR'])
        self.assertEqual(self.words('*NING'), ['RÄKNING'])
        self.assertEqual(self.words('*T*N'), ['KATTEN'])
        self.assertEqual(search_dictionary('sv', self.folder)['total'], 6)
        with self.assertRaises(ValueError):
            search_dictionary('sv', self.folder, 'K[A]T')

    def test_paging(self):
        page = search_dictionary('sv', self.folder, '', 'all', 2, 2)
        # Sorted: HUND KATT KATTEN KATTOR RÄKNING Ö.
        self.assertEqual([e['word'] for e in page['words']], ['KATTEN', 'KATTOR'])
        self.assertEqual(page['total'], 6)

    def test_add_delete_enable_disable(self):
        result = edit_dictionary('sv', self.folder, add=['båt', 'katt'], remove=['hund', 'saknas'])
        self.assertEqual((result['added'], result['removed'], result['skipped']), (1, 1, 2))
        self.assertIn('BÅT', active_words('sv', self.folder))
        self.assertNotIn('HUND', active_words('sv', self.folder))
        edit_dictionary('sv', self.folder, disable=['katt'])
        self.assertEqual(get_disabled('sv', self.folder), ['KATT'])
        self.assertNotIn('KATT', active_words('sv', self.folder))
        self.assertIn('KATT', dictionary_state('sv', self.folder)['words'])
        self.assertEqual(self.words('', 'disabled'), ['KATT'])
        self.assertNotIn('KATT', self.words('', 'enabled'))
        self.assertFalse(search_dictionary('sv', self.folder, 'KATT')['words'][0]['enabled'])
        edit_dictionary('sv', self.folder, enable=['katt'])
        self.assertIn('KATT', active_words('sv', self.folder))
        with self.assertRaises(ValueError):
            edit_dictionary('sv', self.folder, add=['ü'])

    def test_removing_or_replacing_drops_disabled_marks(self):
        edit_dictionary('sv', self.folder, disable=['katt', 'hund'])
        edit_dictionary('sv', self.folder, remove=['hund'])
        self.assertEqual(get_disabled('sv', self.folder), ['KATT'])
        import_dictionary('sv', 'katten\nkattor\n', self.folder)
        self.assertEqual(get_disabled('sv', self.folder), [])
        edit_dictionary('sv', self.folder, disable=['kattor'])
        save_dictionary('sv', ['kattor', 'båt'], self.folder)
        self.assertEqual(get_disabled('sv', self.folder), ['KATTOR'])

    def test_demo_list_becomes_custom_on_first_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(search_dictionary('nl', folder)['custom'])
            edit_dictionary('nl', folder, disable=['huis'])
            state = search_dictionary('nl', folder)
            self.assertTrue(state['custom'])
            self.assertEqual(state['disabledCount'], 1)
            self.assertGreater(state['count'], 50)


if __name__ == '__main__':
    unittest.main()
