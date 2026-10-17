import time
import unittest
from unittest.mock import patch
from test_solver import puzzle
from app import solver
from app.solver import solve


class Morphology:
    def __init__(self): self.calls = []
    def match(self, p, slot, base, rules, deadline, limit):
        self.calls.append(slot)
        return ['UNET'], False
    def details(self, words):
        return {w: [{'lemma': 'UNI', 'description': 'noun · plural', 'source': 'test'}] for w in words}


class ImprovementsTests(unittest.TestCase):
    def test_distant_domain_propagation(self):
        p = puzzle(1, 7, [1,2,None,2,3,None,3], {6:'T'})
        p['cells'][2]['black'] = p['cells'][5]['black'] = True
        r = solve(p, ['AN', 'NO', 'NT'])
        self.assertEqual(r['solutions'][0]['letters'], ['A','N','','N','T','','T'])
        self.assertGreater(r['stats']['propagationRounds'], 0)
        self.assertLessEqual(r['stats']['nodes'], 2)

    def test_index_avoids_scanning_unrelated_lengths_and_patterns(self):
        p = puzzle(1,3,[1,2,1])
        r = solve(p, ['DAD','DOG','SOMETHING','OTHER','AAAAAAAAAA'])
        self.assertEqual(r['stats']['dictionaryCandidatesVisited'], 1)

    def test_missing_word_inferred_from_other_numbered_word(self):
        p = puzzle(1,5,[1,2,None,2,1], allowUnknownWords=True)
        p['cells'][2]['black'] = True
        r = solve(p,['AT'])
        self.assertTrue(r['solutions'])
        words = r['solutions'][0]['words']
        self.assertEqual({w['text'] for w in words}, {'AT','TA'})
        unknown = next(w for w in words if w['text']=='TA')
        self.assertFalse(unknown['verified'])
        self.assertEqual(unknown['source'],'unverified')

    def test_unresolved_unknown_cells_are_not_invented(self):
        p = puzzle(1,4, allowUnknownWords=True)
        r = solve(p,['AT'])
        self.assertFalse(r['solutions'])
        self.assertTrue(any('unresolved' in d.lower() for d in r['diagnostics']))

    def test_morphology_opt_in_default_and_evidence(self):
        p = puzzle(1,4,[1,2,3,4],language='fi')
        m = Morphology()
        r = solve(p,[],morphology=m)
        self.assertEqual(r['solutions'][0]['letters'],list('UNET'))
        self.assertEqual(r['solutions'][0]['words'][0]['source'],'morphology')
        self.assertEqual(r['solutions'][0]['words'][0]['analyses'][0]['lemma'],'UNI')
        p['useMorphology'] = False
        self.assertEqual(solve(p,[],morphology=m)['status'],'empty_dictionary')
        self.assertEqual(len(m.calls),1)

    def test_deep_budget_cancel_progress(self):
        events=[]
        r=solve(puzzle(1,2,searchMode='deep'),['AT'],cancel=lambda: True,progress=events.append)
        self.assertEqual(r['status'],'cancelled')
        self.assertEqual(r['stats']['timeLimitSeconds'],60)
        self.assertTrue(events)
        self.assertIn('stage',events[0])

    def test_cancel_dictionary_free(self):
        self.assertEqual(solve(puzzle(1,2,useDictionary=False),[],cancel=lambda: True)['status'],'cancelled')

    def test_cancel_variant(self):
        p=puzzle(1,2,useDictionary=False)
        p['rules']['maxLettersPerNumber']=2
        self.assertEqual(solve(p,[],cancel=lambda: True)['status'],'cancelled')

    def test_cancellation_during_candidate_generation(self):
        state={'stop':False}
        def progress(event):
            if event['stage']=='generating_candidates': state['stop']=True
        r=solve(puzzle(1,2),['AT'],cancel=lambda:state['stop'],progress=progress)
        self.assertEqual(r['status'],'cancelled')

    def test_budget_status_preserved_with_solutions(self):
        with patch('app.solver.MAX_NODES',3):
            r=solve(puzzle(1,2),['AT','TO','GO','DO'])
        self.assertTrue(r['solutions'])
        self.assertEqual(r['status'],'budget_exhausted')

    def test_unknown_fallback_with_misleading_domain(self):
        p=puzzle(1,7,[1,2,3,None,3,2,1],{0:'C'},allowUnknownWords=True)
        p['cells'][3]['black']=True
        r=solve(p,['CAT','TEN'])
        self.assertTrue(r['solutions'])
        self.assertEqual(r['solutions'][0]['letters'],['C','A','T','','T','A','C'])
        self.assertFalse(r['solutions'][0]['words'][1]['verified'])

    def test_unknown_fallback_honors_forbidden_words(self):
        p=puzzle(1,5,[1,2,None,2,1],{0:'A'},allowUnknownWords=True)
        p['cells'][2]['black']=True
        p['rules']['forbiddenPatterns']=['TA']
        self.assertFalse(solve(p,['AT'])['solutions'])

    def test_missing_word_search_completes_grid_with_one_unlisted_word(self):
        # BAT/ORE/WED across, BOW/ARE/TED down; WED is absent from the list.
        # The transposed grid fits the same numbers just as well, so the
        # known A pins the orientation (otherwise the tie-break decides).
        letters = 'BATOREWED'
        numbers = [ 'BATORWED'.index(l)+1 for l in letters]
        p = puzzle(3,3,numbers,{1:'A'},allowUnknownWords=True)
        r = solve(p,['BAT','ORE','BOW','ARE','TED','TOE','BED'])
        self.assertEqual(''.join(r['solutions'][0]['letters']),letters)
        self.assertEqual(r['stats']['unsupportedWords'],1)
        wed = next(w for w in r['solutions'][0]['words'] if w['text']=='WED')
        self.assertFalse(wed['verified'])
        self.assertEqual(wed['source'],'unverified')

    def test_missing_word_search_returns_partial_without_guessing(self):
        p = puzzle(1,5,[1,2,None,3,4],allowUnknownWords=True)
        p['cells'][2]['black'] = True
        r = solve(p,['AT'])
        self.assertFalse(r['solutions'])
        self.assertEqual(r['partialLetters'],['A','T','','',''])
        self.assertEqual(r['stats']['unsupportedWords'],1)
        self.assertEqual(r['stats']['unresolvedCells'],2)

    def test_missing_word_search_keeps_low_ranked_candidates(self):
        # About 1000 fillers, many outranking QUA, push it out of a small
        # ranked cut; only QUA crosses QI.
        from itertools import permutations
        fillers = [''.join(t) for t in permutations('ETAOINSHRDL',3)]
        p = puzzle(2,3,[1,2,3,4,None,None],allowUnknownWords=True)
        p['cells'][4]['black'] = p['cells'][5]['black'] = True
        with patch('app.solver.MAX_CANDIDATES', 50):
            r = solve(p,fillers+['QUA','QI'])
        self.assertEqual(r['solutions'][0]['letters'],['Q','U','A','I','',''])
        self.assertEqual(r['stats']['unsupportedWords'],0)

    def test_strict_failure_suggests_missing_word_mode(self):
        p = puzzle(1,3,[1,2,3])
        r = solve(p,['AT'])
        self.assertFalse(r['solutions'])
        self.assertTrue(any('Allow words missing' in d for d in r['diagnostics']))

    def test_heuristic_keeps_found_solutions_when_time_expires(self):
        p=puzzle(10,10,[i%26+1 for i in range(100)],useDictionary=False)
        with patch('app.solver.MAX_SECONDS',.05): r=solve(p,[])
        self.assertEqual(r['status'],'budget_exhausted')
        self.assertTrue(r['solutions'])
        self.assertTrue(all(not w['verified'] for s in r['solutions'] for w in s['words']))

    def test_heuristic_keeps_found_solutions_when_cancelled(self):
        p=puzzle(2,3,[1,2,3,3,2,1],useDictionary=False)
        calls=[0]
        def cancel():
            calls[0]+=1
            return calls[0]>30
        r=solve(p,[],cancel=cancel)
        self.assertEqual(r['status'],'cancelled')
        self.assertTrue(r['solutions'])

    def test_open_fragment_index_is_bounded(self):
        from app.word_index import WordIndex
        index=WordIndex('en',['ABCDEFGHIJKLMNOPQRSTUVWXYZ','ZYXWVUTSRQPONMLKJIHGFEDCBA'],lambda:None)
        p=puzzle(1,2)
        slot=dict(cells=[0,1],before=True,after=True)
        with patch('app.word_index.MAX_FRAGMENTS',5):
            candidates=list(index.candidates(p,slot,p['rules'],lambda:None))
        self.assertEqual(len(candidates),5)
        self.assertTrue(index.truncated)
        self.assertEqual(len(next(iter(index.fragments.values()))),5)

    def test_extended_budget_and_cancel_reason(self):
        r=solve(puzzle(1,2,searchMode='extended'),['AT'],cancel=lambda:True)
        self.assertEqual(r['stats']['timeLimitSeconds'],300)
        self.assertEqual(r['stats']['nodeLimit'],5000000)
        self.assertEqual(r['stats']['searchMode'],'extended')
        self.assertEqual(r['stats']['stopReason'],'cancelled')

    def test_specific_stop_reasons(self):
        with patch('app.solver.MAX_SECONDS',0):
            self.assertEqual(solve(puzzle(1,2),['AT'])['stats']['stopReason'],'time_limit')
        with patch('app.solver.MAX_NODES',0):
            self.assertEqual(solve(puzzle(1,2),['AT'])['stats']['stopReason'],'node_limit')
        self.assertEqual(solve(puzzle(1,2),[])['stats']['stopReason'],'empty_dictionary')
        self.assertEqual(solve(puzzle(1,3),['AT'])['stats']['stopReason'],'no_candidates')
        self.assertEqual(solve(puzzle(1,2),['AT'])['stats']['stopReason'],'search_exhausted')
        self.assertEqual(solve(puzzle(1,2,[1,1],{0:'A',1:'B'}),['AT'])['stats']['stopReason'],'invalid_constraints')
        with patch('app.solver.MAX_SOLUTIONS',1):
            self.assertEqual(solve(puzzle(1,2),['AT','TO'])['stats']['stopReason'],'search_exhausted')

    def test_strict_search_keeps_the_highest_scoring_alternatives(self):
        words=['AT','TO','IT','IN','ON','AN','NO','SO','AS','IS','US','UP','ME','WE','HE','BE','BY','MY','OF','OR','GO','DO','IF']
        p=puzzle(2,2,[1,2,3,4])
        with patch('app.solver.MAX_SOLUTIONS',1000): everything=solve(p,words)
        self.assertGreater(len(everything['solutions']),3)
        best=sorted((s['score'] for s in everything['solutions']),reverse=True)[:3]
        with patch('app.solver.MAX_SOLUTIONS',3): r=solve(p,words)
        self.assertEqual([s['score'] for s in r['solutions']],best)
        self.assertEqual(r['stats']['stopReason'],'search_exhausted')
        self.assertTrue(r['stats']['exhaustive'])
        self.assertTrue(r['stats']['moreSolutions'])
        self.assertGreater(r['stats']['boundPruned'],0)
        self.assertLess(r['stats']['propagationRounds'],everything['stats']['propagationRounds'])
        self.assertTrue(any('3 highest-scoring' in d for d in r['diagnostics']))
        self.assertTrue(all('rawScore' not in s for s in r['solutions']))

    def test_dictionary_free_results_give_every_number_a_rival_margin(self):
        p=puzzle(2,3,[1,2,3,3,2,1],useDictionary=False)
        with patch('app.solver.MAX_NODES',3000): r=solve(p,[])
        self.assertEqual((r['stats']['closeMargin'],r['stats']['clearMargin']),(solver.CLOSE_MARGIN,solver.CLEAR_MARGIN))
        for s in r['solutions']:
            self.assertEqual(set(s['numberMargins']),{'1','2','3'})
            for number,info in s['numberMargins'].items():
                self.assertGreaterEqual(info['margin'],0)
                self.assertNotEqual(info['alternative'],s['letters'][[c['number'] for c in p['cells']].index(number)])

    def test_dictionary_free_result_records_a_replay_ending_on_the_top_alternative(self):
        p=puzzle(10,10,[i%26+1 for i in range(100)],useDictionary=False)
        with patch('app.solver.MAX_SECONDS',.6): r=solve(p,[])
        replay=r['replay']
        self.assertTrue(2<=len(replay)<=solver.REPLAY_FRAMES)
        self.assertEqual(replay[-1]['letters'],r['solutions'][0]['letters'])
        self.assertEqual([f['seconds'] for f in replay],sorted(f['seconds'] for f in replay))
        self.assertEqual([f['score'] for f in replay],sorted(f['score'] for f in replay),'Each step improves the score')
        for frame in replay:
            self.assertEqual(len(frame['letters']),len(p['cells']))
            self.assertTrue(frame['numberMargins'])
        with patch('app.solver.MAX_SECONDS',.6), patch('app.solver.REPLAY_FRAMES',3): short=solve(p,[])
        self.assertLessEqual(len(short['replay']),3)
        self.assertEqual(short['replay'][-1]['letters'],short['solutions'][0]['letters'])

    def test_dictionary_free_progress_streams_best_mapping(self):
        p=puzzle(10,10,[i%26+1 for i in range(100)],useDictionary=False)
        events=[]
        with patch('app.solver.MAX_SECONDS',.6): r=solve(p,[],progress=events.append)
        previews=[e['preview'] for e in events if 'preview' in e]
        self.assertTrue(previews)
        self.assertTrue(all(len(x)==len(p['cells']) and all(x) for x in previews))
        self.assertNotIn('preview',r)
        self.assertNotIn('previewMargins',r)
        margins=[e['previewMargins'] for e in events if e.get('previewMargins')]
        self.assertTrue(margins,'The live preview carries certainty margins')
        numbers={c['number'] for c in p['cells']}
        self.assertTrue(all(set(m)<=numbers and all(v['margin']>=0 for v in m.values()) for m in margins))

    def test_dictionary_free_alternatives_are_distinct_local_optima(self):
        numbers={}; cells=[numbers.setdefault(ch,len(numbers)+1) for ch in 'HEARTEMBERABUSERESINTREND']
        p=puzzle(5,5,cells,useDictionary=False)
        with patch('app.solver.MAX_NODES',20000): r=solve(p,[])
        self.assertGreater(len(r['solutions']),1)
        spread=r['stats']['minimumNumbersDifferent']
        self.assertEqual(spread,solver.MIN_MAPPING_DISTANCE)
        mappings=[{c['number']:l for c,l in zip(p['cells'],s['letters'])} for s in r['solutions']]
        for i,a in enumerate(mappings):
            for b in mappings[i+1:]:
                self.assertGreaterEqual(sum(a[n]!=b[n] for n in a),spread)
        scores=[s['score'] for s in r['solutions']]
        self.assertEqual(scores,sorted(scores,reverse=True))

    def test_pruning_is_separate_from_stop_reason(self):
        with patch('app.solver.MAX_CANDIDATES',1):
            r=solve(puzzle(1,2),['AT','TO'])
        self.assertEqual(r['stats']['stopReason'],'search_exhausted')
        self.assertIn('candidate_limit',r['stats']['limitsReached'])
        self.assertFalse(r['stats']['exhaustive'])

    def test_strict_search_retains_partial_on_cancellation(self):
        from app import solver
        original=solver._domain_propagation
        state={'stop':False}
        def propagated(*args,**kwargs):
            answer=original(*args,**kwargs)
            if answer and any(answer[0]): state['stop']=True
            return answer
        p=puzzle(1,5);p['cells'][2]['black']=True
        with patch('app.solver._domain_propagation',side_effect=propagated):
            r=solve(p,['AT','TO'],cancel=lambda:state['stop'])
        self.assertEqual(r['status'],'cancelled')
        self.assertEqual(r['stats']['stopReason'],'cancelled')
        self.assertTrue(any(r['partialLetters']))
        self.assertEqual(r['forcedLetters'],['']*5)

    def test_strict_normal_failure_does_not_keep_disproved_partial(self):
        p=puzzle(2,2,[1,2,3,4])
        r=solve(p,['AT','TO','GO','DO'])
        self.assertFalse(r['solutions'])
        self.assertNotIn('partialLetters',r)

    def test_pruning_flag_survives_cancellation_during_generation(self):
        from app import solver
        original=solver._score
        state={'stop':False}
        def score(*args):
            state['stop']=True
            return original(*args)
        with patch('app.solver.MISSING_WORD_CANDIDATES',1), patch('app.solver._score',side_effect=score):
            r=solve(puzzle(1,2),['AT','TO','GO'],cancel=lambda:state['stop'])
        self.assertEqual(r['stats']['stopReason'],'cancelled')
        self.assertIn('candidate_limit',r['stats']['limitsReached'])

    def test_heuristic_stop_reason_and_retained_guesses(self):
        with patch('app.solver.MAX_NODES',1):
            r=solve(puzzle(1,2,useDictionary=False),[])
        self.assertEqual(r['stats']['stopReason'],'node_limit')
        self.assertTrue(r['solutions'])

    def test_cancel_after_isolated_dead_end_discards_disproved_partial(self):
        from app import solver
        original=solver._mapping
        state={'stop':False}
        def mapping(cells,letters,rules):
            valid=original(cells,letters,rules)
            if all(letters[i] for i in (0,2,4)) and not valid:
                state['stop']=True
            return valid
        p=puzzle(1,5,[1,None,2,None,3])
        p['cells'][1]['black']=p['cells'][3]['black']=True
        p['rules']['forbiddenPatterns']=list('CDEFGHIJKLMNOPQRSTUVWXYZ')
        with patch('app.solver._mapping',side_effect=mapping):
            r=solve(p,[],cancel=lambda:state['stop'])
        self.assertEqual(r['status'],'cancelled')
        self.assertNotIn('partialLetters',r)


def missing_word_grid(seed):
    """A 10×10 random-letter grid; five of its words are left out of a list
    padded with 1,500 random strings per length. Deterministic per seed."""
    import random
    from app.solver import _slots
    rnd = random.Random(seed); alphabet = 'ABCDEFGHIJKLMNOPQRST'
    letters = [rnd.choice(alphabet) for _ in range(100)]
    black = [rnd.random() < 0.25 for _ in range(100)]
    order = sorted(set(letters))
    p = puzzle(10, 10, [None if b else order.index(l)+1 for l, b in zip(letters, black)], allowUnknownWords=True)
    for cell, b in zip(p['cells'], black): cell['black'] = b
    words = sorted({''.join(letters[i] for i in s['cells']) for s in _slots(p)})
    missing = set(rnd.sample(words, 5))
    decoys = [''.join(rnd.choice(alphabet) for _ in range(n)) for n in range(2, 11) for _ in range(1500)]
    return p, [w for w in words if w not in missing] + decoys


class MissingWordScheduleTests(unittest.TestCase):
    def test_tight_caps_find_fewest_unsupported_words(self):
        # A first cap of many unsupported words let depth-first search settle
        # on early placements: this grid ended with 8 unsupported words at the
        # node limit. Caps rising from one find the 3 the list really lacks.
        p, words = missing_word_grid(52)
        with patch('app.solver.MAX_NODES', 3000), patch('app.solver.MAX_SECONDS', 60):
            r = solve(p, words)
        self.assertEqual(r['stats']['unsupportedWords'], 3)
        self.assertLess(r['stats']['nodes'], 3000)

    def test_budget_end_still_returns_a_hypothesis(self):
        # Low caps cannot settle this grid within the budget; the reserved
        # uncapped dive still returns a hypothesis instead of nothing.
        p, words = missing_word_grid(2)
        with patch('app.solver.MAX_NODES', 5000), patch('app.solver.MAX_SECONDS', 60):
            r = solve(p, words)
        self.assertEqual(r['stats']['stopReason'], 'node_limit')
        self.assertIsNotNone(r['stats'].get('unsupportedWords'))
        self.assertTrue(r['solutions'] or r.get('partialLetters'))


class PreparationBudgetTests(unittest.TestCase):
    def test_indexing_and_letter_model_are_outside_the_search_budget(self):
        from app import solver
        original = solver.WordIndex
        def slow_index(*args, **kwargs):
            time.sleep(.3)
            return original(*args, **kwargs)
        events = []
        with patch('app.solver.WordIndex', side_effect=slow_index), patch('app.solver.MAX_SECONDS', .2):
            r = solve(puzzle(1,3,[1,2,3]), ['CAT'], progress=events.append)
        self.assertEqual(r['status'], 'solutions_found')
        self.assertGreaterEqual(r['stats']['preparationSeconds'], .3)
        stages = [e['stage'] for e in events]
        for stage in ('adapting_letter_model', 'indexing_dictionary', 'generating_candidates'):
            self.assertIn(stage, stages)
        self.assertLess(stages.index('adapting_letter_model'), stages.index('indexing_dictionary'))
        self.assertLess(stages.index('indexing_dictionary'), stages.index('generating_candidates'))

    def test_cancel_still_works_during_preparation(self):
        from app import solver
        original = solver.WordIndex
        state = {'stop': False}
        def index(*args, **kwargs):
            state['stop'] = True
            return original(*args, **kwargs)
        with patch('app.solver.WordIndex', side_effect=index):
            r = solve(puzzle(1,3,[1,2,3]), ['CAT'], cancel=lambda: state['stop'])
        self.assertEqual(r['status'], 'cancelled')
