import unittest
from itertools import islice, product
from unittest.mock import patch
from app.candidates import find_candidates
from app.solver import default_rules


def puzzle(rows, cols, text='', numbers=None):
    p=dict(rows=rows,cols=cols,language='fi',useDictionary=True,rules=default_rules('fi'),cells=[])
    for i in range(rows*cols):
        c=text[i] if i<len(text) else '?'
        p['cells'].append(dict(black=c=='#',number=str(numbers[i]) if numbers and numbers[i] else '',letter=c if c not in '?#' else ''))
    return p


class CandidateTests(unittest.TestCase):
    def test_unrelated_word_does_not_hide_match(self):
        p=puzzle(2,5,'LA?EN?????')
        r=find_candidates(p,['LADEN','LAPEN'],[0])
        self.assertEqual(r['words'][0]['pattern'],'LA?EN')
        self.assertEqual(set(r['words'][0]['candidates']),{'LADEN','LAPEN'})
        self.assertTrue(r['combinations'])
        self.assertEqual(r['combinations'][0]['letters'][5:],['']*5)
    def test_distant_fixed_number_mapping(self):
        p=puzzle(1,5,'??#?D',[1,2,None,None,1])
        r=find_candidates(p,['DO','TO'],[0])
        self.assertEqual(r['words'][0]['pattern'],'D?')
        self.assertEqual(r['words'][0]['candidates'],['DO'])
    def test_local_candidates_survive_joint_mapping_conflict(self):
        p=puzzle(1,5,'A?#?E',[None,1,None,1,None])
        r=find_candidates(p,['AT','BE'],[0,1])
        self.assertEqual(r['words'][0]['candidates'],['AT'])
        self.assertEqual(r['words'][1]['candidates'],['BE'])
        self.assertEqual(r['combinations'],[])
        self.assertTrue(r['stats']['exhaustive'])
    def test_selected_crossings(self):
        p=puzzle(2,2,'A???')
        r=find_candidates(p,['AT','TO'],[0,1,2,3])
        self.assertEqual(r['combinations'][0]['letters'],list('ATTO'))
    def test_partial_endpoints(self):
        p=puzzle(1,2,'AT')
        self.assertFalse(find_candidates(p,['BATH'],[0])['combinations'])
        p['cells'][0]['openBeforeAcross']=True
        p['cells'][1]['openAfterAcross']=True
        r=find_candidates(p,['BATH'],[0])
        self.assertEqual(r['words'][0]['candidates'],['AT'])
        self.assertTrue(r['words'][0]['partial'])
    def test_invalid_ids(self):
        p=puzzle(2,2)
        for ids in ([],[True],[-1],[4],[0,0],list(range(9)),None,'0'):
            with self.assertRaises(ValueError): find_candidates(p,[],ids)
    def test_budget_honesty(self):
        with patch('app.candidates.MAX_WORK',0):
            r=find_candidates(puzzle(1,2),['AT'],[0])
        self.assertFalse(r['stats']['exhaustive'])
        self.assertTrue(r['words'][0]['truncated'])
        self.assertEqual(r['status'],'budget_exhausted')
    def test_dictionary_free_variant(self):
        p=puzzle(1,3,'A??',[1,1,1]);p['useDictionary']=False;p['rules']['maxLettersPerNumber']=2
        r=find_candidates(p,[],[0])
        self.assertTrue(r['combinations'])
        self.assertEqual(r['words'][0]['source'],'heuristic')
        self.assertFalse(r['stats']['exhaustive'])
        for c in r['combinations']: self.assertLessEqual(len(set(c['letters'])),2)
    def test_finnish_generated_candidates_retain_front_vowels(self):
        p=puzzle(1,7,numbers=[1,2,3,4,5,6,2]);p['useDictionary']=False
        r=find_candidates(p,[],[0])
        candidates=r['words'][0]['candidates']
        for letter in 'ÄÖ':
            self.assertTrue(any(letter in text for text in candidates), letter)
        for text in candidates:
            self.assertEqual(text[1],text[6])
            self.assertEqual(len(set(text[:6])),6)
        self.assertEqual(r['words'][0]['source'],'heuristic')
        self.assertFalse(r['stats']['exhaustive'])

    def test_finnish_generation_diversity_respects_forbidden_letters(self):
        p=puzzle(1,7,numbers=[1,2,3,4,5,6,2]);p['useDictionary']=False
        p['rules']['forbiddenPatterns']=['Ä','Ö']
        candidates=find_candidates(p,[],[0])['words'][0]['candidates']
        self.assertTrue(candidates)
        self.assertTrue(all(not set(text)&set('ÄÖ') for text in candidates))

    def test_forced_hard_rule_in_unselected_word(self):
        p=puzzle(1,6,'??#???',[1,2,None,1,1,1])
        p['rules']['forbiddenPatterns']=['AAA']
        r=find_candidates(p,['AT','TO'],[0])
        self.assertEqual(r['words'][0]['candidates'],['TO'])
    def test_large_dictionary_eight_constrained_slots(self):
        words=[''.join(chars) for chars in islice(product('ABCDEFGHIJKL', repeat=5),118000)]
        words.append('LADEN')
        p=puzzle(8,5,'LA?EN'*8)
        r=find_candidates(p,words,list(range(8)))
        self.assertEqual([w['candidates'] for w in r['words']],[['LADEN']]*8)
        self.assertTrue(all(not w['truncated'] for w in r['words']))
        self.assertTrue(r['stats']['exhaustive'])
        self.assertLess(r['stats']['work'],100)
        self.assertEqual(len(r['combinations']),1)
    def test_preprocessing_deadline(self):
        with patch('app.candidates.MAX_SECONDS',0):
            r=find_candidates(puzzle(1,2),['AT'],[0])
        self.assertEqual(r['status'],'budget_exhausted')
        self.assertFalse(r['stats']['exhaustive'])
        self.assertTrue(r['words'][0]['truncated'])

    def test_hard_rules(self):
        p=puzzle(1,3);p['rules']['forbiddenPatterns']=['AAA']
        self.assertFalse(find_candidates(p,['AAA'],[0])['combinations'])

if __name__=='__main__': unittest.main()
