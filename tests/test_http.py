"""Integration tests use an ephemeral loopback port and disposable data."""
import http.client
import sqlite3
from contextlib import closing
from pathlib import Path
import json
import tempfile
import threading
import unittest
from app.server import make_server


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.server = make_server(0, cls.temp.name)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def request(self, path, value=None, method=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        head = {'Content-Type': 'application/json'}
        head.update(headers or {})
        conn.request(method or ('POST' if value is not None else 'GET'), path,
                     json.dumps(value) if value is not None else None, head)
        response = conn.getresponse()
        code, body = response.status, response.read()
        conn.close()
        return code, json.loads(body)

    def puzzle(self):
        return {'name': 'Integration fixture', 'language': 'en', 'rows': 1, 'cols': 3,
                'cells': [{'black': False, 'number': str(i+1), 'letter': 'C' if i==0 else ''} for i in range(3)],
                'useDictionary': True, 'rules': {'maxLettersPerNumber': 1, 'uniqueLetters': True}}

    def test_roundtrip_and_solver(self):
        code, result = self.request('/api/solve', self.puzzle())
        self.assertEqual(code, 200)
        self.assertTrue(result['solutions'])
        self.assertTrue(all(s['letters'][0] == 'C' for s in result['solutions']))
        p = self.puzzle()
        p['suggestions'] = result
        code, saved = self.request('/api/puzzles', p)
        self.assertEqual(code, 200)
        code, opened = self.request('/api/puzzles/' + saved['id'])
        self.assertEqual(opened['suggestions'], result)
        self.assertEqual(saved['language'], 'en')
        listed = [item for item in self.request('/api/puzzles')[1]['puzzles'] if item['id'] == saved['id']]
        self.assertEqual(listed[0]['language'], 'en')

    def test_word_list_import_filters_and_reports_without_rewriting_words(self):
        code, result = self.request('/api/dictionaries/en/import', {
            'text': '\ufeffcat\nCAT\ndog\n10-point\n1080\ncan\'t\n\n'})
        self.assertEqual(code, 200)
        self.assertEqual((result['count'], result['skipped'], result['duplicates'], result['total']), (2, 3, 1, 6))
        _, saved = self.request('/api/dictionaries/en')
        self.assertEqual(saved['words'], ['CAT', 'DOG'])
        for value in ('123\n10-point', '', None):
            code, _ = self.request('/api/dictionaries/en/import', {'text': value})
            self.assertEqual(code, 400)
        _, retained = self.request('/api/dictionaries/en')
        self.assertEqual(retained['words'], ['CAT', 'DOG'])
        # Restore this shared fixture for other tests.
        self.request('/api/dictionaries/en', {'words': ['CAT', 'CAR']}, 'PUT')

    def test_dutch_dictionary_save_and_puzzle_roundtrip(self):
        code, result = self.request('/api/dictionaries/nl/import', {'text': 'kat\nhuis\nijs'})
        self.assertEqual(code, 200)
        self.assertEqual(result['count'], 3)
        p = self.puzzle()
        p['language'] = 'nl'
        p['cells'][0]['letter'] = 'K'
        code, result = self.request('/api/solve', p)
        self.assertEqual(code, 200)
        self.assertEqual(result['solutions'][0]['letters'], list('KAT'))
        code, saved = self.request('/api/puzzles', p)
        self.assertEqual(code, 200)
        _, opened = self.request('/api/puzzles/' + saved['id'])
        self.assertEqual(opened['language'], 'nl')

    def test_origin_and_dns_rebinding_rejected(self):
        for headers in [{'Origin': 'https://example.com'}, {'Host': 'example.com'}]:
            code, result = self.request('/api/puzzles', self.puzzle(), headers=headers)
            self.assertEqual(code, 403)

    def test_invalid_patterns_rejected_before_save(self):
        p = self.puzzle()
        p['rules']['forbiddenPatterns'] = ['!!!']
        code, _ = self.request('/api/puzzles', p)
        self.assertEqual(code, 400)

    def test_invalid_payloads_are_client_errors(self):
        for p in [[], {'rows': 100}, {'image': 'garbage', 'rows': 1, 'cols': 1}]:
            code, _ = self.request('/api/ocr' if isinstance(p, dict) and 'image' in p else '/api/solve', p)
            self.assertEqual(code, 400)

    def test_ruled_out_letters_and_rejected_words_round_trip(self):
        p = self.puzzle()
        p['eliminations'] = {'2': ['q']}
        p['rejectedWords'] = [{'start': 0, 'direction': 'Across', 'word': 'cat'}]
        code, saved = self.request('/api/puzzles', p)
        self.assertEqual(code, 200)
        code, opened = self.request('/api/puzzles/' + saved['id'])
        self.assertEqual(opened['eliminations'], {'2': ['Q']})
        self.assertEqual(opened['rejectedWords'], [{'start': 0, 'direction': 'Across', 'word': 'CAT'}])
        code, checked = self.request('/api/validate', p)
        self.assertEqual(code, 200)
        self.assertTrue(checked['valid'])
        self.assertIsInstance(checked['suggestedEliminations'], list)
        self.assertFalse(any(s['number'] == '2' and s['letter'] == 'Q' for s in checked['suggestedEliminations']))
        p['eliminations'] = {'2': ['1']}
        self.assertEqual(self.request('/api/puzzles', p)[0], 400)

    def test_number_review_marks_are_validated(self):
        p = self.puzzle()
        p['cells'][0]['numberReview'] = 'check'
        self.assertEqual(self.request('/api/puzzles', p)[0], 200)
        p['cells'][0]['numberReview'] = 'maybe'
        self.assertEqual(self.request('/api/puzzles', p)[0], 400)
        # A cell later marked as a block or picture area may still carry its
        # old mark; solving must not fail on it.
        p['cells'][0].update(numberReview='check', black=True, clue=True, number='', letter='')
        self.assertEqual(self.request('/api/solve', p)[0], 200)

    def test_autosave_round_trip_and_validation(self):
        p = self.puzzle()
        p['cells'][0]['letter'] = 'K'
        code, _ = self.request('/api/autosave', {'puzzle': p, 'unsaved': True}, 'PUT')
        self.assertEqual(code, 200)
        code, result = self.request('/api/autosave')
        self.assertEqual(code, 200)
        self.assertTrue(result['autosave']['unsaved'])
        self.assertEqual(result['autosave']['puzzle']['cells'][0]['letter'], 'K')
        for bad in [{'puzzle': p}, {'puzzle': {'rows': 100}, 'unsaved': False}, []]:
            self.assertEqual(self.request('/api/autosave', bad, 'PUT')[0], 400)
        # A rejected autosave never replaces the last good one.
        self.assertEqual(self.request('/api/autosave')[1]['autosave']['puzzle']['cells'][0]['letter'], 'K')

    def test_straighten_endpoint(self):
        import base64, io
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB', (200, 160), 'white').save(buffer, format='PNG')
        image = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
        handles = {name: {'x': x, 'y': y} for name, (x, y) in zip(
            ('topLeft', 'top', 'topRight', 'right', 'bottomRight', 'bottom', 'bottomLeft', 'left'),
            [(.1, .1), (.5, .1), (.9, .1), (.9, .5), (.9, .9), (.5, .9), (.1, .9), (.1, .5)])}
        code, result = self.request('/api/straighten', {'image': image, 'handles': handles})
        self.assertEqual(code, 200)
        self.assertTrue(result['image'].startswith('data:image/jpeg;base64,'))
        for bad in [[], {'image': image}, {'image': 'garbage', 'handles': handles}]:
            code, _ = self.request('/api/straighten', bad)
            self.assertEqual(code, 400)
        self.assertEqual(self.request('/api/straighten/detect', {'image': image}), (200, {'handles': None}))
        for bad in [[], {'image': 'garbage'}]:
            self.assertEqual(self.request('/api/straighten/detect', bad)[0], 400)

    def test_empty_dictionary_and_generated_mode(self):
        code, _ = self.request('/api/dictionaries/fi', {'words': []}, 'PUT')
        self.assertEqual(code, 200)
        p = self.puzzle()
        p['language'] = 'fi'
        code, result = self.request('/api/solve', p)
        self.assertEqual(result['status'], 'empty_dictionary')
        p['useDictionary'] = False
        code, result = self.request('/api/solve', p)
        self.assertTrue(result['solutions'])
        self.assertTrue(all(not word['verified'] for s in result['solutions'] for word in s['words']))

    def test_rename_delete_api_and_origin_protection(self):
        _, saved = self.request('/api/puzzles', self.puzzle())
        route = '/api/puzzles/' + saved['id']
        code, result = self.request(route, {'name': 'Renamed'}, 'PATCH')
        self.assertEqual(code, 200)
        self.assertEqual(result['name'], 'Renamed')
        code, opened = self.request(route)
        self.assertEqual(opened['cells'], self.puzzle()['cells'])
        code, _ = self.request(route, None, 'DELETE', headers={'Origin': 'https://example.com'})
        self.assertEqual(code, 403)
        code, _ = self.request(route)
        self.assertEqual(code, 200)
        code, deleted = self.request(route, None, 'DELETE')
        self.assertEqual(code, 200)
        self.assertTrue(deleted['deleted'])
        code, _ = self.request(route)
        self.assertEqual(code, 404)
        code, _ = self.request(route, {'name': 'Missing'}, 'PATCH')
        self.assertEqual(code, 404)

    def test_morphology_index_toggle_and_sources(self):
        folder=Path(self.temp.name)/'morphology';folder.mkdir(exist_ok=True)
        path=folder/'fi.sqlite'
        try:
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE forms(word,length,pattern,lemma,analysis,source)')
                db.execute('INSERT INTO forms VALUES(?,?,?,?,?,?)',('TALOJEN',7,'0.1.2.3.4.5.6','talo','[NUM=PL][CASE=GEN]','Omorfi test fixture'))
            p=self.puzzle();p.update(language='fi',cols=7,cells=[dict(black=False,number='',letter=c if c!='?' else '') for c in 'TALO?EN'])
            code,result=self.request('/api/candidates',dict(puzzle=p,slotIds=[0]))
            self.assertEqual(code,200)
            self.assertIn('TALOJEN',result['words'][0]['candidates'])
            self.assertEqual(result['words'][0]['candidateDetails']['TALOJEN'][0]['description'],'plural · genitive')
            p['useMorphology']=False
            code,result=self.request('/api/candidates',dict(puzzle=p,slotIds=[0]))
            self.assertEqual(code,200)
            self.assertNotIn('TALOJEN',result['words'][0]['candidates'])
            p['useMorphology']='yes'
            code,_=self.request('/api/candidates',dict(puzzle=p,slotIds=[0]))
            self.assertEqual(code,400)
        finally:
            path.unlink(missing_ok=True)

    def test_lookup_api_word_and_pattern(self):
        # Swedish keeps this dictionary away from fixtures that use the demo lists.
        puzzle = dict(self.puzzle(), language='sv')
        code, _ = self.request('/api/dictionaries/sv', {'words': ['abba', 'anna', 'båten']}, 'PUT')
        self.assertEqual(code, 200)
        code, word = self.request('/api/lookup', {'puzzle': puzzle, 'query': 'båten'})
        self.assertEqual(code, 200)
        self.assertEqual(word['kind'], 'word')
        self.assertTrue(word['inDictionary'])
        code, found = self.request('/api/lookup', {'puzzle': puzzle, 'query': 'A 7 7 A'})
        self.assertEqual(code, 200)
        self.assertEqual(sorted(found['candidates']), ['ABBA', 'ANNA'])
        code, _ = self.request('/api/lookup', {'puzzle': puzzle, 'query': 'A Ü'})
        self.assertEqual(code, 400)
        code, _ = self.request('/api/lookup', {'puzzle': puzzle})
        self.assertEqual(code, 400)

    def test_dictionary_search_and_edit_api(self):
        code, _ = self.request('/api/dictionaries/sv', {'words': ['katt', 'katten', 'hund']}, 'PUT')
        self.assertEqual(code, 200)
        code, found = self.request('/api/dictionaries/sv/search?q=K%3FTT*&status=all&offset=0')
        self.assertEqual(code, 200)
        self.assertEqual([e['word'] for e in found['words']], ['KATT', 'KATTEN'])
        code, result = self.request('/api/dictionaries/sv/entries', {'add': ['båt'], 'disable': ['katt']})
        self.assertEqual((code, result['added'], result['disabled']), (200, 1, 1))
        code, saved = self.request('/api/dictionaries/sv')
        self.assertEqual(saved['disabled'], ['KATT'])
        puzzle = dict(self.puzzle(), language='sv', cells=[{'black': False, 'number': '', 'letter': l} for l in 'KAT'] + [{'black': False, 'number': '', 'letter': ''}])
        puzzle['cols'] = 4
        code, word = self.request('/api/lookup', {'puzzle': puzzle, 'query': 'katt'})
        self.assertEqual(code, 200)
        self.assertFalse(word['inDictionary'])
        self.assertTrue(word['disabled'])
        code, found = self.request('/api/lookup', {'puzzle': puzzle, 'query': 'K A T ?'})
        self.assertNotIn('KATT', found['candidates'])
        code, _ = self.request('/api/dictionaries/sv/search?q=%5B&status=all')
        self.assertEqual(code, 400)
        code, _ = self.request('/api/dictionaries/sv/entries', {'add': 'katt'})
        self.assertEqual(code, 400)

    def test_selected_candidates_api(self):
        code, result = self.request('/api/candidates', {'puzzle': self.puzzle(), 'slotIds': [0]})
        self.assertEqual(code, 200)
        self.assertTrue(result['words'][0]['candidates'])
        self.assertTrue(result['combinations'])
        for ids in [None, [], [False], [999], [0, 0]]:
            code, _ = self.request('/api/candidates', {'puzzle': self.puzzle(), 'slotIds': ids})
            self.assertEqual(code, 400)
        for payload in [[], {}, {'puzzle': []}]:
            code, _ = self.request('/api/candidates', payload)
            self.assertEqual(code, 400)
        code, _ = self.request('/api/candidates', {'puzzle': self.puzzle(), 'slotIds': [0]},
                               headers={'Origin': 'https://example.com'})
        self.assertEqual(code, 403)

    def test_pdf_api_rejects_invalid_and_foreign_requests(self):
        code, _ = self.request('/api/pdf', {'pdf': 'invalid'})
        self.assertEqual(code, 400)
        code, _ = self.request('/api/pdf', {}, headers={'Origin': 'https://example.com'})
        self.assertEqual(code, 403)
