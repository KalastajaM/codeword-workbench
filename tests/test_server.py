import json
import tempfile
import unittest
from pathlib import Path
from app.server import PuzzleStore, check_puzzle


def puzzle():
    return {'name': 'Test', 'rows': 1, 'cols': 2, 'language': 'en',
            'cells': [{'black': False, 'number': '1', 'letter': 'A'}, {'black': False, 'number': '2', 'letter': ''}],
            'rules': {'maxLettersPerNumber': 1, 'uniqueLetters': True}, 'useDictionary': True}


class StorageTests(unittest.TestCase):
    def test_mapping_anchor_roundtrip_and_boolean_validation(self):
        with tempfile.TemporaryDirectory() as d:
            store = PuzzleStore(Path(d))
            p = puzzle()
            p['cells'][0]['mappingAnchor'] = True
            saved = store.save(p)
            self.assertIs(store.get(saved['id'])['cells'][0]['mappingAnchor'], True)
            for value in ['true', 1, None]:
                p['cells'][0]['mappingAnchor'] = value
                with self.assertRaises(ValueError):
                    check_puzzle(p)

    def test_round_trip_retains_full_state(self):
        with tempfile.TemporaryDirectory() as d:
            store = PuzzleStore(Path(d))
            p = puzzle()
            p['imageBounds'] = {'x': 0, 'y': .2, 'width': 1, 'height': .5}
            p['suggestions'] = {'solutions': [{'letters': ['A', 'T']}]}
            saved = store.save(p)
            read = store.get(saved['id'])
            self.assertEqual(read['suggestions'], p['suggestions'])
            self.assertEqual(read['imageBounds'], p['imageBounds'])
            self.assertEqual(len(store.list()), 1)
            read['name'] = 'Changed'
            store.save(read)
            self.assertEqual(len(store.list()), 1)
            self.assertEqual(store.get(saved['id'])['name'], 'Changed')

    def test_paths_and_bad_state_rejected_without_write(self):
        with tempfile.TemporaryDirectory() as d:
            store = PuzzleStore(Path(d))
            with self.assertRaises(ValueError):
                store.get('../../elsewhere')
            p = puzzle()
            p['cells'][0]['letter'] = 'AA'
            with self.assertRaises(ValueError):
                store.save(p)
            self.assertEqual(store.list(), [])

    def test_schema_requires_real_dimensions_and_known_language(self):
        for key, value in [('rows', True), ('cols', 41), ('language', 'xx'), ('cells', [])]:
            p = puzzle()
            p[key] = value
            with self.assertRaises(ValueError):
                check_puzzle(p)

    def test_corrupt_image_does_not_replace_saved_puzzle(self):
        with tempfile.TemporaryDirectory() as d:
            store = PuzzleStore(Path(d))
            original = puzzle()
            saved = store.save(original)
            imported = store.get(saved['id'])
            imported['image'] = 'data:image/png;base64,bm90IGFuIGltYWdl'
            with self.assertRaises(ValueError):
                store.save(imported)
            self.assertNotIn('image', store.get(saved['id']))

    def test_malformed_optional_image_fields_rejected(self):
        for key, value in [('image', []), ('image', False), ('imageBounds', {}), ('imageBounds', [])]:
            p = puzzle()
            p[key] = value
            with self.assertRaises(ValueError):
                check_puzzle(p)

    def test_rename_preserves_progress_and_delete_moves_to_trash(self):
        with tempfile.TemporaryDirectory() as d:
            store = PuzzleStore(Path(d))
            original = puzzle()
            original['suggestions'] = {'solutions': [{'letters': ['A', 'T']}]}
            saved = store.save(original)
            renamed = store.rename(saved['id'], 'Renamed puzzle')
            self.assertEqual(renamed['name'], 'Renamed puzzle')
            read = store.get(saved['id'])
            self.assertEqual(read['cells'], original['cells'])
            self.assertEqual(read['suggestions'], original['suggestions'])
            deleted = store.delete(saved['id'])
            self.assertTrue(deleted['deleted'])
            self.assertEqual(store.list(), [])
            with self.assertRaises(FileNotFoundError):
                store.get(saved['id'])
            trash = list((Path(d) / 'trash' / 'puzzles').glob('*.json'))
            self.assertEqual(len(trash), 1)
            self.assertEqual(json.loads(trash[0].read_text())['name'], 'Renamed puzzle')

    def test_invalid_rename_or_delete_does_not_change_data(self):
        with tempfile.TemporaryDirectory() as d:
            store = PuzzleStore(Path(d))
            saved = store.save(puzzle())
            for name in ['', '  ', 'x' * 201, None]:
                with self.assertRaises(ValueError):
                    store.rename(saved['id'], name)
            with self.assertRaises(ValueError):
                store.delete('../outside')
            with self.assertRaises(FileNotFoundError):
                store.delete('a' * 32)
            self.assertEqual(store.get(saved['id'])['name'], 'Test')

    def test_clue_cell_metadata_validation(self):
        p = puzzle()
        p['cells'][0].update(black=True, clue=True, highlight=False, number='', letter='')
        check_puzzle(p)
        p['cells'][0]['clue'] = 'yes'
        with self.assertRaises(ValueError):
            check_puzzle(p)

    def test_late_save_cannot_resurrect_deleted_puzzle(self):
        with tempfile.TemporaryDirectory() as d:
            store = PuzzleStore(Path(d))
            saved = store.save(puzzle())
            in_flight = store.get(saved['id'])
            store.delete(saved['id'])
            with self.assertRaises(FileNotFoundError):
                store.save(in_flight)
            self.assertEqual(store.list(), [])

    def test_provisional_guess_roundtrip_and_normalization(self):
        with tempfile.TemporaryDirectory() as d:
            store = PuzzleStore(Path(d))
            p = puzzle()
            p['language'] = 'fi'
            p['cells'][1]['guess'] = ' a\u0308 '
            stored = store.get(store.save(p)['id'])
            self.assertEqual(stored['cells'][1]['guess'], 'Ä')
            self.assertEqual(stored['cells'][1]['letter'], '')
            stored['cells'][1]['black'] = True
            check_puzzle(stored)
            self.assertEqual(stored['cells'][1]['guess'], '')

    def test_invalid_provisional_guesses_rejected(self):
        for guess in ['AB', 'Ä', 2, None, ['A']]:
            p = puzzle()
            p['cells'][1]['guess'] = guess
            with self.assertRaises(ValueError):
                check_puzzle(p)

    def test_provisional_guess_is_not_a_solver_constraint(self):
        from app.solver import solve
        p = puzzle()
        p['cells'][1]['guess'] = 'Z'
        self.assertEqual(solve(check_puzzle(p), ['AT'])['solutions'][0]['letters'], ['A', 'T'])
