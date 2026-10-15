import tempfile
import unittest
from unittest.mock import patch
from app.solver import solve, validate, default_rules
from app.dictionaries import get_dictionary, save_dictionary


def puzzle(rows, cols, numbers=None, letters=None, **kw):
    p = dict(rows=rows, cols=cols, language='en', rules=default_rules('en'), useDictionary=True,
             cells=[dict(black=False, number=str(n) if n else '', letter='') for n in (numbers or [None]*(rows*cols))])
    for i, letter in (letters or {}).items(): p['cells'][i]['letter'] = letter
    p.update(kw)
    return p


class SolverTests(unittest.TestCase):
    def test_repeat_and_fixed(self):
        p = puzzle(1,3,[1,2,1], {0:'D'})
        r = solve(p,['DAD','DOG','DID'])
        self.assertEqual({''.join(s['letters']) for s in r['solutions']}, {'DAD','DID'})
    def test_conflicting_locks(self):
        self.assertFalse(validate(puzzle(1,2,[1,1],{0:'A',1:'B'}))['valid'])
        self.assertFalse(validate(puzzle(1,2,[1,2],{0:'A',1:'A'}))['valid'])
    def test_capacity(self):
        p = puzzle(1,3,[1,1,1]); p['rules']['maxLettersPerNumber']=2
        self.assertEqual({''.join(s['letters']) for s in solve(p,['ABA','ABC'])['solutions']}, {'ABA'})
    def test_relaxed_uniqueness(self):
        p=puzzle(1,2,[1,2]); p['rules']['uniqueLetters']=False
        self.assertEqual(solve(p,['AA'])['solutions'][0]['letters'], ['A','A'])
    def test_crossings_numberless(self):
        p=puzzle(2,2,letters={0:'A'})
        r=solve(p,['AT','TO'])
        self.assertEqual(r['solutions'][0]['letters'],list('ATTO'))
    def test_fragments(self):
        p=puzzle(1,2,letters={0:'A'})
        self.assertFalse(solve(p,['CAT'])['solutions'])
        p['cells'][0]['openBeforeAcross']=True
        self.assertEqual(solve(p,['CAT'])['solutions'][0]['letters'],list('AT'))
        p['cells'][0]['openBeforeAcross']=False
        p['cells'][1]['openAfterAcross']=True
        self.assertEqual(solve(p,['ATE'])['solutions'][0]['letters'],list('AT'))
    def test_unicode(self):
        p=puzzle(1,3,language='fi', letters={0:'ä'})
        self.assertEqual(solve(p,['a\u0308iti','ÄÄÄ'])['solutions'][0]['letters'],list('ÄÄÄ'))
    def test_forbidden(self):
        p=puzzle(1,3); p['rules']['forbiddenPatterns']=['AAA']
        self.assertFalse(solve(p,['AAA'])['solutions'])
    def test_generated_is_unverified(self):
        p=puzzle(1,3,useDictionary=False)
        r=solve(p,[])
        self.assertTrue(r['solutions'])
        self.assertFalse(r['solutions'][0]['words'][0]['verified'])
        self.assertFalse(r['stats']['exhaustive'])
    def test_empty_and_invalid(self):
        self.assertEqual(solve(puzzle(1,2),[])['status'],'empty_dictionary')
        self.assertFalse(validate(puzzle(1,2,letters={0:'AB'}))['valid'])
        self.assertFalse(validate({'rows':1,'cols':2,'cells':[]})['valid'])
    def test_isolated_known(self):
        r=solve(puzzle(1,1,[1],{0:'Z'}),[])
        self.assertEqual(r['solutions'][0]['letters'],['Z'])
    def test_soft_language_preferences(self):
        from app.solver import _score, _FREQUENCY
        from app.dictionaries import ALPHABETS
        for language in ALPHABETS:
            self.assertEqual(set(_FREQUENCY[language]),set(ALPHABETS[language]))
            self.assertEqual(len(_FREQUENCY[language]),len(ALPHABETS[language]))
        self.assertGreater(_score('THERE','en',default_rules('en')),_score('EEEEE','en',default_rules('en')))
        self.assertGreater(_score('KOTI','fi',default_rules('fi')),_score('AAAA','fi',default_rules('fi')))
        # Preferences must never become hard exclusions.
        self.assertTrue(solve(puzzle(1,5),['EEEEE'])['solutions'])
    def test_frontier_budget(self):
        p=puzzle(1,3); p['cells'][1]['black']=True
        with patch('app.solver.MAX_FRONTIER_CELLS',12):
            r=solve(p,[])
        self.assertTrue(r['solutions'])
        self.assertFalse(r['stats']['exhaustive'])
        self.assertTrue(any('memory budget' in d for d in r['diagnostics']))
        self.assertEqual(r['stats']['frontierLimit'],4)
    def test_budget_is_honest(self):
        with patch('app.solver.MAX_NODES',0):
            r=solve(puzzle(1,2),['AT'])
        self.assertEqual(r['status'],'budget_exhausted')
        self.assertFalse(r['stats']['exhaustive'])
    def test_both_open_endpoints(self):
        p=puzzle(1,2,letters={0:'A',1:'T'})
        p['cells'][0]['openBeforeAcross']=True
        p['cells'][1]['openAfterAcross']=True
        r=solve(p,['BATH'])
        self.assertEqual(r['solutions'][0]['letters'],list('AT'))
        self.assertFalse(r['solutions'][0]['words'][0]['verified'])
    def test_distant_known_mapping(self):
        p=puzzle(1,4,[1,2,None,1],{3:'D'})
        p['cells'][2]['black']=True
        self.assertEqual(solve(p,['DO','TO'])['solutions'][0]['letters'],['D','O','','D'])
    def test_capacity_sets_still_disjoint(self):
        p=puzzle(1,3,[1,1,2]); p['rules']['maxLettersPerNumber']=2
        self.assertFalse(solve(p,['ABA'])['solutions'])
        p['rules']['uniqueLetters']=False
        self.assertTrue(solve(p,['ABA'])['solutions'])
    def test_malformed_language(self):
        p=puzzle(1,1); p['language']=[]
        self.assertFalse(validate(p)['valid'])
    def test_forbidden_isolated_fixed(self):
        p=puzzle(1,1,letters={0:'A'}); p['rules']['forbiddenPatterns']=['A']
        self.assertFalse(validate(p)['valid'])
    def test_seeded_global_search_reproducible(self):
        p=puzzle(2,3,[1,2,3,3,2,1],useDictionary=False)
        with patch('app.solver.MAX_NODES',300):
            first=solve(p,[]); second=solve(p,[])
        self.assertEqual(first['solutions'],second['solutions'])
    def test_finnish_harmony_is_only_soft(self):
        p=puzzle(1,2,language='fi')
        self.assertTrue(solve(p,['AÖ'])['solutions'])

    def test_forced_letters_survive_empty_dictionary(self):
        p=puzzle(1,4,[1,2,1,2],{0:'A'})
        r=solve(p,[])
        self.assertEqual(r['status'],'empty_dictionary')
        self.assertEqual(r['forcedLetters'],['A','','A',''])
        self.assertEqual(p['cells'][2]['letter'],'')
    def test_forced_letters_survive_no_dictionary_solution(self):
        p=puzzle(1,3,[1,2,1],{0:'A'})
        self.assertEqual(solve(p,['DOG'])['forcedLetters'],['A','','A'])
    def test_large_global_heuristic(self):
        p=puzzle(20,20,[(r*7+c)%26+1 for r in range(20) for c in range(20)],{0:'A'},language='fi',useDictionary=False)
        with patch('app.solver.MAX_NODES',300): r=solve(p,[])
        self.assertTrue(r['solutions'])
        self.assertEqual(r['stats']['method'],'global_mapping_annealing')
        for solution in r['solutions']:
            assignments={}
            for c,l in zip(p['cells'],solution['letters']):
                self.assertTrue(l)
                assignments.setdefault(c['number'],set()).add(l)
            self.assertTrue(all(len(x)==1 for x in assignments.values()))
            self.assertEqual(len(set(next(iter(x)) for x in assignments.values())),26)
            self.assertEqual(solution['letters'][0],'A')
            self.assertTrue(all(not w['verified'] for w in solution['words']))
    def test_global_hard_rules_and_numberless(self):
        p=puzzle(2,3,[1,None,2,3,1,None],{0:'A'},useDictionary=False)
        p['rules']['forbiddenPatterns']=['E','AA','II']
        with patch('app.solver.MAX_NODES',1200): r=solve(p,[])
        self.assertTrue(r['solutions'])
        for solution in r['solutions']:
            self.assertEqual(solution['letters'][4],'A')
            for word in solution['words']:
                self.assertTrue(all(pattern not in word['text'] for pattern in p['rules']['forbiddenPatterns']))
    def test_global_nonunique_and_fixed(self):
        p=puzzle(1,3,[1,2,1],{0:'A',1:'A'},useDictionary=False)
        p['rules']['uniqueLetters']=False
        r=solve(p,[])
        self.assertEqual(r['solutions'][0]['letters'],list('AAA'))
    def test_variant_does_not_force_same_number(self):
        p=puzzle(1,3,[1,2,1],{0:'A'},useDictionary=False)
        p['rules']['maxLettersPerNumber']=2
        r=solve(p,[])
        self.assertEqual(r['forcedLetters'],['A','',''])
        self.assertTrue(r['solutions'])
    def test_propagation_detects_forbidden_pattern(self):
        p=puzzle(1,3,[1,1,1],{0:'A'})
        p['rules']['forbiddenPatterns']=['AAA']
        r=solve(p,[])
        self.assertEqual(r['status'],'conflict')
        self.assertEqual(r['forcedLetters'],list('AAA'))

    def test_dictionary_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn('demonstration',get_dictionary('fi',d)['source'])
            self.assertEqual(save_dictionary('fi',['äiti','ÄITI','koti'],d)['count'],2)
            self.assertEqual(get_dictionary('fi',d)['words'],['KOTI','ÄITI'])

if __name__=='__main__': unittest.main()
