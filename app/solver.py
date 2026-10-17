"""Bounded constraint search. Heuristic candidates are never verified words."""
import time
import math
import random
from .dictionaries import ALPHABETS, normalize, clean_words
from .word_index import WordIndex
from . import language_model
from . import eliminations as _eliminations

MAX_CANDIDATES=500
# Missing-word search keeps whole candidate lists: a score-ranked cut drops
# the intended word for most unconstrained slots of real puzzles.
MISSING_WORD_CANDIDATES=20000
MISSING_WORD_PHASE_NODES=1500
MISSING_WORD_EAGER=2000
MAX_NODES=30000
MAX_SECONDS=4.0
DEEP_SECONDS=60.0
EXTENDED_SECONDS=300.0
EXTENDED_NODES=5000000
DEEP_NODES=1000000
MAX_SOLUTIONS=12
# Dictionary-free alternatives must differ in at least this many numbers.
MIN_MAPPING_DISTANCE=3
# How far, in pattern-score points, a dictionary-free letter leads its best
# rival. Below CLOSE_MARGIN the rival is close: on the test grids every wrong
# letter fell there, along with a few right ones. From CLEAR_MARGIN up the lead
# is clear; no wrong letter on the test grids had one. Neither band is proof.
CLOSE_MARGIN=5.0
CLEAR_MARGIN=15.0
# Live preview throttles, in seconds.
PREVIEW_SECONDS=0.2
MARGIN_SECONDS=1.0
# Most steps kept for replaying how a dictionary-free search settled.
REPLAY_FRAMES=60
BEAM_WIDTH=64
MAX_FRONTIER_CELLS=200000


def default_rules(language):
    if language not in ALPHABETS: raise ValueError('Unsupported language.')
    return dict(maxLettersPerNumber=1,uniqueLetters=True,forbiddenPatterns=[],discouragedPatterns=[])


def _rules(puzzle):
    rules={**default_rules(puzzle.get('language','en')),**puzzle.get('rules',{})}
    # Per-puzzle user decisions, kept with the rules every check receives.
    rules['excludedLetters']=_eliminations.excluded_letters(puzzle)
    rules['rejectedWords']=_eliminations.rejected_words(puzzle)
    return rules


def _mapping(cells, letters, rules):
    groups={}; owners={}
    for c,l in zip(cells,letters):
        if c.get('black') or not l or not c.get('number'): continue
        n=str(int(c['number']))
        if l in rules.get('excludedLetters',{}).get(n,()): return False
        group=groups.setdefault(n,set()); group.add(l)
        if len(group)>rules['maxLettersPerNumber']: return False
        if rules['uniqueLetters'] and l in owners and owners[l]!=n: return False
        owners[l]=n
    return True


def validate(puzzle):
    errors=[]
    if not isinstance(puzzle,dict): return dict(valid=False,conflicts=['Puzzle must be an object.'])
    rows=puzzle.get('rows'); cols=puzzle.get('cols'); cells=puzzle.get('cells')
    if type(rows)!=int or type(cols)!=int or not 1<=rows<=40 or not 1<=cols<=40:
        return dict(valid=False,conflicts=['Grid dimensions must be integers from 1 to 40.'])
    if not isinstance(cells,list) or len(cells)!=rows*cols:
        return dict(valid=False,conflicts=['Cell count must equal rows × columns.'])
    language=puzzle.get('language','en')
    if not isinstance(language,str) or language not in ALPHABETS: return dict(valid=False,conflicts=['Unsupported language.'])
    if not isinstance(puzzle.get('rules',{}),dict): return dict(valid=False,conflicts=['Rules must be an object.'])
    rules=_rules(puzzle)
    if type(rules['maxLettersPerNumber'])!=int or not 1<=rules['maxLettersPerNumber']<=len(ALPHABETS[language]): errors.append('Mapping capacity must be between 1 and the alphabet size.')
    if type(rules['uniqueLetters'])!=bool: errors.append('uniqueLetters must be boolean.')
    if type(puzzle.get('useDictionary',True))!=bool: errors.append('useDictionary must be boolean.')
    try: _eliminations.check(dict(puzzle),language)
    except ValueError as error: errors.append(str(error))
    for field in ('forbiddenPatterns','discouragedPatterns'):
        value=rules[field]
        if not isinstance(value,list) or len(value)>100 or any(not isinstance(x,str) or not x.strip() or len(x)>40 or not set(normalize(x))<=set(ALPHABETS[language]) for x in value): errors.append(f'{field} must contain up to 100 nonempty letter patterns of at most 40 letters.')
    letters=[]
    for i,c in enumerate(cells):
        if not isinstance(c,dict): errors.append(f'Cell {i+1} must be an object.'); continue
        if type(c.get('black',False))!=bool: errors.append(f'Cell {i+1}: black must be boolean.')
        n=c.get('number',''); l=c.get('letter','')
        if not isinstance(n,str) or (n and (not n.isascii() or not n.isdecimal() or len(n)>2 or not 1<=int(n)<=99)): errors.append(f'Cell {i+1}: number must be empty or an integer from 1 to 99.')
        if not isinstance(l,str) or (l and (len(normalize(l))!=1 or normalize(l) not in ALPHABETS[language])): errors.append(f'Cell {i+1}: enter exactly one letter from the selected alphabet.')
        for key in ('openBeforeAcross','openAfterAcross','openBeforeDown','openAfterDown'):
            if key in c and type(c[key])!=bool: errors.append(f'Cell {i+1}: boundary flags must be boolean.')
        letters.append(normalize(l) if isinstance(l,str) else '')
    if not errors:
        errors.extend(_eliminations.conflicts(puzzle,_slots(puzzle),letters,rules))
    if not errors and not _mapping(cells,letters,rules): errors.append('Confirmed letters conflict with mapping capacity or letter uniqueness.')
    if not errors:
        single_forbidden={normalize(pattern) for pattern in rules['forbiddenPatterns'] if len(normalize(pattern))==1}
        if any(letter in single_forbidden for c,letter in zip(cells,letters) if not c.get('black')):
            errors.append('A confirmed letter is explicitly forbidden.')
        for slot in _slots(puzzle):
            text=''.join(letters[i] or '?' for i in slot['cells'])
            if any(normalize(p) in text for p in rules['forbiddenPatterns']): errors.append('Confirmed letters contain an explicitly forbidden pattern.')
    return dict(valid=not errors,conflicts=errors)


def suggested_eliminations(puzzle):
    """Letters each open number probably cannot be; never applied automatically."""
    rules=_rules(puzzle)
    base=['' if c.get('black') else normalize(c.get('letter','')) for c in puzzle['cells']]
    return _eliminations.suggest(puzzle,_slots(puzzle),_propagate(puzzle,base,rules),rules)


def _slots(p):
    cells=p['cells']; rows=p['rows']; cols=p['cols']; slots=[]
    for direction in ('Across','Down'):
        lines=([r*cols+c for c in range(cols)] for r in range(rows)) if direction=='Across' else ([r*cols+c for r in range(rows)] for c in range(cols))
        for line in lines:
            segment=[]
            for i in line+[None]:
                if i is not None and not cells[i].get('black',False): segment.append(i); continue
                if len(segment)>=2:
                    slots.append(dict(cells=segment,before=cells[segment[0]].get('openBefore'+direction,False),after=cells[segment[-1]].get('openAfter'+direction,False),direction=direction))
                segment=[]
    return slots


_FREQUENCY={'en':'ETAOINSHRDLCUMWFGYPBVKJXQZ','fi':'AITNESLOKUMÄVRJHYPDÖGBCFÅWZXQ',
            'nl':'ENATIRODSLGVHKMUBPWZCJFXYQ','sv':'EANTRSILDOMKGVHFUPÄBCÅÖYJXWZQ'}
_BIGRAMS={'en':set('TH HE IN ER AN RE ON AT EN ND TI ES OR TE OF ED IS IT AL AR ST TO NT NG SE HA AS OU IO LE VE CO ME DE HI RI RO IC NE EA RA CE LI CH LL BE MA SI OM UR'.split()),'fi':set('AI AN AA EN IN IS IT JA KA KE KI KK KO LA LE LI LL MA MI NA NE NI NN NT ON OO OS PA RA RI SA SE SI SS ST TA TE TI TT TU UA UL UN UU VA VI YÖ ÄÄ ÄI ÄN ÖI'.split())}

_TRIGRAMS={'en':set('THE AND ING HER ERE ENT THA NTH WAS ETH FOR ION TIO TER EST ERS ATI HAT ATE ALL HIS RES VER ITH OTH FRO ONE OUR OUT YOU'.split()),'fi':set('STA SSA LLA LLE NEN INE AAN AIN INN TTA TTI KSI DEN EEN ELL OLL TAI ALA LIK KAI AAM'.split())}

# Hand-tuned Dutch fallback preferences (used only without a trained model).
# IJ is scored as two letters and always occupies two cells.
_BIGRAMS['nl'] = set('EN ER DE TE EE AA OO IN AN ET HE GE IE IJ ND EL ST AR OR RE NG VE NE CH OE OU UI EU EI AU ON IT IS AT AL LE BE ME NT RD ZE ZI JK'.split())
# Hand-tuned Swedish fallback preferences, as for Dutch.
_BIGRAMS['sv'] = set('EN ER AR DE ET TT AN TE ST OR IN KA RA LL NG GE SK ÄR NA ON LA ME SA DA TA AT EL IG HA OM ÅR KO RE LI VA ÖR FÖ NN MM SS SO'.split())
_TRIGRAMS['sv'] = set('ING OCH ADE ARE NDE ERA STA LIG ATT DET SOM FÖR TER ENS ANS ADE IGT NIN STE ELL ARN ORN ETT'.split())
_TRIGRAMS['nl'] = set('EEN HET VAN DEN DER VER AAN ING SCH IJK IJS EEU OOR OON ACH EER GEN NDE AND ENT TER IET OED ERS STE ZIJ NIE'.split())

def _legacy_score(text,language):
    frequency=_FREQUENCY[language]
    score=sum((len(frequency)-frequency.index(c))/len(frequency) for c in text)
    score+=sum(1.6 for a,b in zip(text,text[1:]) if a+b in _BIGRAMS[language])
    score+=sum(1.2 for i in range(len(text)-2) if text[i:i+3] in _TRIGRAMS[language])
    return score


def _score(text,language,rules,before=False,after=False):
    """Character-model bits plus soft rule penalties; higher is more word-like.

    Without a trained model for the language, fall back to hand-tuned
    frequencies, pairs and triples. Neither path verifies a word.
    """
    model=language_model.active(language)
    if model is None: score=_legacy_score(text,language)
    else: score=model.score(text,before,after)
    score-=sum(penalty for penalty,_ in language_model.rule_findings(text,language,before,after))
    score-=sum(text.count(normalize(pattern))*5 for pattern in rules['discouragedPatterns'])
    return score


def _allowed(text,rules):
    return not any(normalize(p) in text for p in rules['forbiddenPatterns'])


def _rejected(slot,text,rules):
    """True when the user rejected this complete word for this slot."""
    return text in rules.get('rejectedWords',{}).get((slot['cells'][0],slot['direction']),())


def _local_ok(slot,text,p,base,rules):
    # Include all confirmed cells, so even distant known number mappings constrain candidates.
    letters=base[:]
    for i,l in zip(slot['cells'],text):
        if base[i] and base[i]!=l: return False
        letters[i]=l
    return _mapping(p['cells'],letters,rules)


def _generated(slot,p,base,rules,deadline,check=lambda: None):
    beam=['']; language=p.get('language','en')
    for k,i in enumerate(slot['cells']):
        extended=[]
        prefixslot={**slot,'cells':slot['cells'][:k+1]}
        for prefix in beam:
            check()
            for letter in (base[i] or _FREQUENCY[language]):
                text=prefix+letter
                if _allowed(text,rules) and _local_ok(prefixslot,text,p,base,rules): extended.append(text)
            if time.monotonic()>deadline: return []
        # Prefixes are open-ended until the last cell; slot flags apply too.
        open_end=slot['after'] or k<len(slot['cells'])-1
        ranked=sorted(extended,key=lambda t:(-_score(t,language,rules,slot['before'],open_end),t))
        # A single score-only beam collapses onto back-vowel prefixes before
        # complete front-vowel alternatives can develop. Reserve a bounded
        # share for each Finnish front vowel, using only compatible prefixes.
        # This preserves exploration, not evidence that a string is a word.
        retained=set()
        if language=='fi':
            quota=BEAM_WIDTH//8
            for vowel in 'ÄÖ':
                retained.update([text for text in ranked if vowel in text][:quota])
        for text in ranked:
            if len(retained)>=BEAM_WIDTH: break
            retained.add(text)
        beam=[text for text in ranked if text in retained]
        if not beam: break
    return beam


def _propagate(p, base, rules):
    forced=base[:]
    if rules['maxLettersPerNumber']==1:
        known={str(int(c['number'])):l for c,l in zip(p['cells'],base)
               if not c.get('black') and c.get('number') and l}
        for i,c in enumerate(p['cells']):
            if not c.get('black') and c.get('number'):
                forced[i]=known.get(str(int(c['number'])),forced[i])
    return forced


def _global_heuristic(p, slots, base, rules, result, started, deadline, control):
    """Anneal whole number mappings, with cached scores for affected word slots.

    Hard constraints hold in returned candidates. Temporary forbidden-pattern
    violations receive a repair penalty during search, never reach the output.
    """
    language=p.get('language','en'); rng=random.Random(0)
    forbidden=[normalize(x) for x in rules['forbiddenPatterns']]
    alphabet=[x for x in _FREQUENCY[language] if x not in forbidden]
    groups={}; cell_var={}; fixed={}; numbered=set()
    for i,c in enumerate(p['cells']):
        if c.get('black'): continue
        key=('number',str(int(c['number']))) if c.get('number') else ('cell',i)
        v=groups.setdefault(key,len(groups)); cell_var[i]=v
        if c.get('number'): numbered.add(v)
        if base[i]: fixed[v]=base[i]
    variables=list(range(len(groups))); movable=[v for v in variables if v not in fixed]
    result['stats'].update(method='global_mapping_annealing',seed=0,exhaustive=False)
    result['diagnostics'].append('Global language-model optimization scores intersecting words together. All generated words are unverified. Letter patterns are soft preferences.')
    if language == 'fi':
        result['diagnostics'].append('Finnish vowel harmony is a soft preference, including exceptions for compounds and loanwords.')
    if (not alphabet and movable) or (rules['uniqueLetters'] and len(numbered)>len(alphabet)):
        result['stats']['stopReason']='invalid_constraints'
        result['diagnostics'].append('The available alphabet cannot satisfy the mapping and forbidden-letter rules.')
        return result
    scoring_slots=[s['cells'] for s in slots]
    covered={i for indices in scoring_slots for i in indices}
    scoring_slots += [[i] for i in cell_var if i not in covered]
    # Isolated cells are scored as single letters with open boundaries.
    boundaries=[(s['before'],s['after']) for s in slots]+[(True,True)]*(len(scoring_slots)-len(slots))
    slot_vars=[[cell_var[i] for i in indices] for indices in scoring_slots]
    excluded={v:rules['excludedLetters'].get(key[1],frozenset()) if key[0]=='number' else frozenset() for key,v in groups.items()}
    affected=[set() for _ in variables]
    for j,vs in enumerate(slot_vars):
        for v in vs: affected[v].add(j)
    # Runs revisit the same words often; a slot's value depends only on its
    # text and, through ruled-out letters, on which variables hold it.
    evaluated={}
    def evaluate(j, assignment):
        text=''.join(assignment[v] for v in slot_vars[j])
        value=evaluated.get((j,text))
        if value is not None: return value
        violations=sum(text.count(pattern) for pattern in forbidden)
        # Ruled-out letters and rejected words are hard rules, repaired like forbidden patterns.
        violations+=sum(1 for v in slot_vars[j] if assignment[v] in excluded[v])
        if j<len(slots) and _rejected(slots[j],text,rules): violations+=1
        if len(evaluated)>500000: evaluated.clear()
        value=evaluated[(j,text)]=(_score(text,language,rules,*boundaries[j]), violations)
        return value
    # Neighbouring states of one run differ by a swap or two. Keep only the
    # best state of each run, polished to a local optimum, and require kept
    # mappings to differ in several numbers so alternatives are distinct.
    spread=min(MIN_MAPPING_DISTANCE,max(1,len(movable)//3))
    # The grid preview: the best violation-free mapping seen so far, including
    # the running state before a run is polished, at most every PREVIEW_SECONDS.
    # Its certainty margins are recomputed at most every MARGIN_SECONDS.
    live=dict(score=-math.inf,assignment=None,shown=0.0,margins_for=None,margins_at=0.0)
    # Every improvement of the best mapping, for replaying how the grid settled.
    frames=[]; began=time.monotonic()
    def publish(assignment, score, force=False):
        now=time.monotonic()
        if score>(frames[-1][2] if frames else -math.inf): frames.append((now-began,list(assignment),score))
        if score<=live['score'] or (not force and now-live['shown']<PREVIEW_SECONDS): return
        preview=['']*len(p['cells'])
        for i,v in cell_var.items(): preview[i]=assignment[v]
        result['preview']=preview
        # Margins of an earlier preview would mislabel this one.
        result.pop('previewMargins',None)
        live.update(score=score,assignment=list(assignment),shown=now)
    def refresh_margins():
        now=time.monotonic()
        if live['assignment'] is None or live['assignment']==live['margins_for'] or now-live['margins_at']<MARGIN_SECONDS: return
        result['previewMargins']=number_margins(live['assignment'])
        live.update(margins_for=live['assignment'],margins_at=time.monotonic())
    solutions={}
    def keep(assignment, score):
        key=tuple(assignment)
        if key in solutions: return
        close=[k for k in solutions if sum(a!=b for a,b in zip(k,key))<spread]
        if any(solutions[k]>=score for k in close): return
        for k in close: del solutions[k]
        if len(solutions)>=MAX_SOLUTIONS:
            worst=min(solutions,key=solutions.get)
            if solutions[worst]>=score: return
            del solutions[worst]
        solutions[key]=score
        result['stats']['heuristicSolutionsFound']=len(solutions)
        publish(assignment,score,force=True)
    def propose(assignment, values, v, letter):
        """Apply a move in place; None when it would take a confirmed letter."""
        changes={v:letter}
        if v in numbered and rules['uniqueLetters']:
            owner=next((u for u in numbered if assignment[u]==letter),None)
            if owner in fixed: return None
            if owner is not None: changes[owner]=assignment[v]
        old={u:assignment[u] for u in changes}
        impacted=set().union(*(affected[u] for u in changes))
        for u,l in changes.items(): assignment[u]=l
        updated={j:evaluate(j,assignment) for j in impacted}
        gain=sum(updated[j][0]-values[j][0] for j in impacted)
        broken=sum(updated[j][1]-values[j][1] for j in impacted)
        return old,updated,gain,broken
    number_of={v:key[1] for key,v in groups.items() if key[0]=='number'}
    def number_margins(assignment):
        """Each number's best rival letter and how many points it trails by."""
        assignment=list(assignment)
        values=[evaluate(j,assignment) for j in range(len(slot_vars))]
        margins={}
        for v in movable:
            if v not in number_of: continue
            best=None
            for letter in alphabet:
                if letter==assignment[v]: continue
                moved=propose(assignment,values,v,letter)
                if moved is None: continue
                old,updated,gain,broken=moved
                for u,l in old.items(): assignment[u]=l
                if broken<=0 and (best is None or gain>best[0]): best=(gain,letter)
            if best: margins[number_of[v]]=dict(alternative=best[1],margin=round(max(0.0,-best[0]),2))
        return margins
    iterations=0; restarts=0; polished=0; run_best=None
    def exhausted():
        return iterations>=control.node_limit or time.monotonic()>=deadline
    def polish(assignment, values, total):
        """Greedy single moves until none improves the score; budget-bounded."""
        nonlocal iterations
        improved=True
        while improved:
            improved=False
            for v in movable:
                for letter in alphabet:
                    if letter==assignment[v]: continue
                    if exhausted(): return total
                    control.check("heuristic_search")
                    iterations+=1; result["stats"]["nodes"]=iterations
                    moved=propose(assignment,values,v,letter)
                    if moved is None: continue
                    old,updated,gain,broken=moved
                    if broken==0 and gain>1e-9:
                        total+=gain; improved=True
                        for j,value in updated.items(): values[j]=value
                    else:
                        for u,l in old.items(): assignment[u]=l
        return total
    stopped_status = None; stopped_reason = None
    try:
        while iterations<control.node_limit and time.monotonic()<deadline:
            control.check("heuristic_search")
            assignment=['']*len(variables)
            for v,l in fixed.items(): assignment[v]=l
            available=[l for l in alphabet if l not in {fixed[v] for v in numbered if v in fixed}]
            if restarts: rng.shuffle(available)
            ordered=sorted((v for v in numbered if v not in fixed),key=lambda v:(-len(affected[v]),v))
            for v in ordered:
                assignment[v]=available.pop(0) if rules['uniqueLetters'] else rng.choice(alphabet)
            for v in movable:
                if v not in numbered: assignment[v]=rng.choice(alphabet)
            values=[evaluate(j,assignment) for j in range(len(slot_vars))]
            total=sum(v[0] for v in values); violations=sum(v[1] for v in values)
            run_best=None if violations else (total,assignment[:],values[:])
            if not movable: break
            for step in range(1200):
                result["stats"]["nodes"]=iterations
                control.check("heuristic_search")
                if exhausted(): break
                if step%50==0: refresh_margins()
                iterations+=1
                v=rng.choice(movable); letter=rng.choice(alphabet)
                if letter==assignment[v]: continue
                moved=propose(assignment,values,v,letter)
                if moved is None: continue
                old,updated,gain,broken=moved
                next_total=total+gain; next_violations=violations+broken
                delta=next_total-total-1000*(next_violations-violations)
                temperature=0.3+5*(1-step/1200)
                if delta>=0 or rng.random()<math.exp(max(-700,delta/temperature)):
                    total=next_total; violations=next_violations
                    for j,value in updated.items(): values[j]=value
                    if not violations and (run_best is None or total>run_best[0]):
                        run_best=(total,assignment[:],values[:])
                        publish(assignment,total)
                else:
                    for u,l in old.items(): assignment[u]=l
            if run_best:
                best_assignment=run_best[1][:]
                score=polish(best_assignment,run_best[2][:],run_best[0])
                polished+=score>run_best[0]+1e-9
                keep(best_assignment,score); run_best=None
            restarts+=1
    except _Stopped as stopped:
        stopped_status = stopped.status; stopped_reason = stopped.reason
    # A run cut short by the budget or cancellation keeps its best state unpolished.
    if run_best: keep(run_best[1],run_best[0])
    for assignment,score in sorted(solutions.items(),key=lambda item:-item[1]):
        letters=['']*len(p['cells'])
        for i,v in cell_var.items(): letters[i]=assignment[v]
        solution_words=[dict(cells=s['cells'],text=''.join(letters[i] for i in s['cells']),verified=False,source='unverified') for s in slots]
        result['solutions'].append(dict(letters=letters,score=round(score,3),words=solution_words,numberMargins=number_margins(assignment)))
    result['stats'].update(closeMargin=CLOSE_MARGIN,clearMargin=CLEAR_MARGIN)
    if frames and solutions:
        # The replay ends on the top alternative, even if a throttled preview
        # never showed it, and keeps at most REPLAY_FRAMES evenly spread steps.
        top=max(solutions,key=solutions.get)
        if tuple(frames[-1][1])!=top: frames.append((time.monotonic()-began,list(top),solutions[top]))
        if len(frames)>REPLAY_FRAMES:
            picks=sorted({round(k*(len(frames)-1)/(REPLAY_FRAMES-1)) for k in range(REPLAY_FRAMES)})
            frames[:]=[frames[k] for k in picks]
        def cells_of(assignment):
            letters=['']*len(p['cells'])
            for i,v in cell_var.items(): letters[i]=assignment[v]
            return letters
        result['replay']=[dict(seconds=round(t,2),score=round(score,3),letters=cells_of(a),numberMargins=number_margins(a))
                          for t,a,score in frames]
    result['stats'].update(nodes=iterations,restarts=restarts,polishedRuns=polished,minimumNumbersDifferent=spread,elapsedSeconds=round(time.monotonic()-started,3),solutionLimit=MAX_SOLUTIONS)
    result['wordCandidates']=[dict(cells=s['cells'],direction=s['direction'],candidates=list(dict.fromkeys(solution['words'][j]['text'] for solution in result['solutions'])),partial=s['before'] or s['after'],verified=False) for j,s in enumerate(slots)]
    if stopped_status:
        result['status']=stopped_status; result['stats']['stopReason']=stopped_reason
    elif iterations>=control.node_limit:
        result['status']='budget_exhausted'; result['stats']['stopReason']='node_limit'
    elif time.monotonic()>=deadline:
        result['status']='budget_exhausted'; result['stats']['stopReason']='time_limit'
    elif result['solutions']: result['status']='solutions_found'
    result['diagnostics'].append('Search is bounded and nonexhaustive; suggestions are plausible letter sequences, not proof of real words or a correct solution.')
    if not result['solutions']: result['diagnostics'].append('No complete assignment satisfying the hard rules was found within the search budget. Forced letters remain available.')
    return result


def _limit_reached(result, code):
    if code not in result['stats']['limitsReached']:
        result['stats']['limitsReached'].append(code)


class _Stopped(Exception):
    def __init__(self, status, reason=None):
        self.status = status
        self.reason = reason or ('cancelled' if status == 'cancelled' else 'time_limit')


class _Control:
    """Progress, cancellation and the search budget.

    Preparation (indexing the word list, adapting the letter model) has no
    deadline, so a large dictionary cannot use up a quick search before it
    starts. start_budget() starts the clock.
    """
    def __init__(self, started, seconds, node_limit, result, cancel, progress):
        self.started = started
        self.seconds = seconds
        self.deadline = math.inf
        self.node_limit = node_limit
        self.result = result
        self.cancel = cancel
        self.progress = progress
        self.last_progress = -1.0
        self.stage = ''

    def check(self, stage=None, force=False):
        now = time.monotonic()
        stage = stage or self.stage or 'preparing'
        if self.progress and (force or stage != self.stage or now-self.last_progress >= .1):
            update = dict(stage=stage, nodes=self.result['stats']['nodes'],
                          elapsedSeconds=round(now-self.started, 3),
                          solutionsFound=max(len(self.result['solutions']),self.result['stats'].get('heuristicSolutionsFound',0)))
            # The best unverified mapping so far, for display while searching.
            if self.result.get('preview'): update['preview'] = self.result['preview']
            if self.result.get('previewMargins') is not None: update['previewMargins'] = self.result['previewMargins']
            self.progress(update)
            self.last_progress = now
        self.stage = stage
        if self.cancel and self.cancel(): raise _Stopped('cancelled')
        if now >= self.deadline: raise _Stopped('budget_exhausted', 'time_limit')

    def start_budget(self):
        if self.deadline == math.inf:
            now = time.monotonic()
            self.deadline = now + self.seconds
            self.result['stats']['preparationSeconds'] = round(now-self.started, 3)


def _compatible(slot, text, cells, letters, rules, known=None, owners=None):
    """Check one candidate in O(word length), using precomputed known mappings."""
    if known is None: known, owners = _known_maps(cells, letters)
    added = {}; claimed = {}
    for i, letter in zip(slot['cells'], text):
        if letters[i] and letters[i] != letter: return False
        number = cells[i].get('number')
        if not number: continue
        number = str(int(number))
        if letter in rules['excludedLetters'].get(number, ()): return False
        group = added.setdefault(number, set(known.get(number, ())))
        group.add(letter)
        if len(group) > rules['maxLettersPerNumber']: return False
        if rules['uniqueLetters']:
            if owners.get(letter, number) != number or claimed.get(letter, number) != number: return False
            claimed[letter] = number
    return True


def _known_maps(cells, letters):
    known = {}; owners = {}
    for c, letter in zip(cells, letters):
        if c.get('black') or not c.get('number') or not letter: continue
        number = str(int(c['number']))
        known.setdefault(number, set()).add(letter)
        owners[letter] = number
    return known, owners


def _domain_propagation(p, slots, domains, letters, rules, control, optional=False):
    """Intersect cell and shared-number supports until reaching a fixed point.

    Optional words cannot force letters: they may be absent from the lexicon.
    Variant mappings share capacity/ownership constraints, not one letter domain.
    """
    cells = p['cells']; standard = rules['maxLettersPerNumber'] == 1
    keys = [('n', str(int(c['number']))) if standard and c.get('number') else ('c', i)
            for i, c in enumerate(cells)]
    domains = dict(domains)
    while True:
        control.check()
        control.result['stats']['propagationRounds'] += 1
        letters = _propagate(p, letters, rules)
        if not _mapping(cells, letters, rules): return None
        for slot in slots:
            text = ''.join(letters[i] or '?' for i in slot['cells'])
            if not _allowed(text, rules) or _rejected(slot, text, rules): return None
        known, owners = _known_maps(cells, letters)
        changed = False; support = {}
        for j, candidates in list(domains.items()):
            kept = []
            for k, text in enumerate(candidates):
                if k % 128 == 0: control.check()
                if _compatible(slots[j], text, cells, letters, rules, known, owners): kept.append(text)
            if not kept and not optional: return None
            kept = tuple(kept)
            if kept != candidates: changed = True
            domains[j] = kept
            if optional: continue
            for pos, i in enumerate(slots[j]['cells']):
                values = {word[pos] for word in kept}; key = keys[i]
                support[key] = support[key] & values if key in support else values
                if not support[key]: return None
        if optional: return letters, domains
        # A fixed value for one number removes that value from all other numbers.
        if standard and rules['uniqueLetters']:
            singleton_owners = dict(owners)
            for key, values in support.items():
                if key[0] == 'n' and len(values) == 1:
                    letter = next(iter(values))
                    if singleton_owners.get(letter, key[1]) != key[1]: return None
                    singleton_owners[letter] = key[1]
            for key in support:
                if key[0] == 'n':
                    support[key] = {v for v in support[key] if singleton_owners.get(v, key[1]) == key[1]}
                    if not support[key]: return None
        for i, c in enumerate(cells):
            values = support.get(keys[i])
            if c.get('black') or not values: continue
            if letters[i] and letters[i] not in values: return None
            if not letters[i] and len(values) == 1:
                letters[i] = next(iter(values)); changed = True
        for j, candidates in list(domains.items()):
            kept = tuple(word for word in candidates if all(letter in support[keys[i]]
                         for i, letter in zip(slots[j]['cells'], word)))
            if not kept: return None
            if kept != candidates: changed = True; domains[j] = kept
        if not changed: return letters, domains


def _constraint_search(p, slots, initial, base, rules, result, control, evidence,
                       use_dictionary, optional=False):
    cells = p['cells']; language = p.get('language', 'en')
    frontier_limit = max(4, MAX_FRONTIER_CELLS // max(1, len(cells)))
    result['stats']['frontierLimit'] = frontier_limit
    stack = [(base[:], dict(enumerate(initial)))]
    seen = {tuple(s['letters']) for s in result['solutions']}
    unknown_cells = {i for slot in slots for i in slot['cells']}
    previous_partial = result.get('partialLetters')
    previous_supported = result['stats'].get('partialSupportedCells')
    pruned = False; unresolved = False; best_partial = base[:]
    best_partial_rank = (-1, -1)
    # Keep the MAX_SOLUTIONS best alternatives rather than the first ones found.
    # Strict domains stay ranked by score, so a slot's first candidate bounds
    # what it can add; branches that cannot beat the weakest kept alternative
    # are cut. Optional words make the support count vary, so no bound there.
    scores = {}
    def word_score(text):
        if text not in scores: scores[text] = _score(text, language, rules)
        return scores[text]
    def solution_rank(solution): return (solution.get('supportedWords',0), solution['rawScore'])
    for solution in result['solutions']:
        solution.setdefault('rawScore', solution['score'])
    bounded = not optional
    def cannot_improve(letters, domains):
        if not bounded or len(result['solutions']) < MAX_SOLUTIONS: return False
        bound = sum(word_score(domains[j][0]) if j in domains and not all(letters[i] for i in slot['cells'])
                    else word_score(''.join(letters[i] for i in slot['cells'])) for j, slot in enumerate(slots))
        if bound > min(solution_rank(s) for s in result['solutions'])[1]: return False
        result['stats']['moreSolutions'] = True
        result['stats']['boundPruned'] = result['stats'].get('boundPruned', 0) + 1
        return True
    def queue(states):
        nonlocal pruned
        available = frontier_limit-len(stack)
        if len(states) > available:
            pruned = True
            if 'memory_limit' not in result['stats']['limitsReached']: result['stats']['limitsReached'].append('memory_limit')
        stack.extend(reversed(states[:available]))
    while stack:
        control.check('unknown_word_search' if optional else 'constraint_search')
        if result['stats']['nodes'] >= control.node_limit: raise _Stopped('budget_exhausted', 'node_limit')
        letters, domains = stack.pop()
        result['stats']['nodes'] += 1
        if cannot_improve(letters, domains): continue
        propagated = _domain_propagation(p, slots, domains, letters, rules, control, optional)
        if propagated is None:
            if not optional:
                result.pop('partialLetters',None)
                result['stats'].pop('partialSupportedCells',None)
                best_partial_rank=(-1,-1)
            continue
        letters, domains = propagated
        if cannot_improve(letters, domains): continue
        supported_cells = set()
        for j, slot in enumerate(slots):
            text = ''.join(letters[i] or '?' for i in slot['cells'])
            if text in evidence[j]: supported_cells.update(slot['cells'])
        rank = (len(supported_cells), sum(bool(x) for x in letters))
        if rank > best_partial_rank:
            best_partial_rank = rank; best_partial = letters[:]
            if any(letters):
                result['partialLetters'] = best_partial
                result['stats']['partialSupportedCells'] = rank[0]
        control.check()
        # Filled slots still need to pass their domain in strict mode; optional
        # slots may become unverified words and are checked against hard rules.
        domains = {j:d for j,d in domains.items() if not all(letters[i] for i in slots[j]['cells'])}
        if domains:
            if optional:
                # Empty lexicon domains are deferred; only evidence may assign
                # unknown word cells, avoiding arbitrary alphabet enumeration.
                domains = {j:d for j,d in domains.items() if d}
            if domains:
                best = min(domains, key=lambda j: (len(domains[j]), -len(slots[j]['cells']), j))
                rest = {j:d for j,d in domains.items() if j != best}
                states = []
                for word in domains[best]:
                    trial = letters[:]
                    for i,l in zip(slots[best]['cells'], word): trial[i] = l
                    states.append((trial, rest))
                if optional: states.append((letters[:], rest))
                queue(states)
                continue
        unfilled = next((i for i,c in enumerate(cells) if not c.get('black') and not letters[i]), None)
        if unfilled is not None:
            if optional and any(not letters[i] for i in unknown_cells):
                unresolved = True; continue
            states = []
            for letter in _FREQUENCY[language]:
                trial = letters[:]; trial[unfilled] = letter
                if _allowed(letter, rules) and _mapping(cells, trial, rules): states.append((trial, {}))
            if not states and not optional:
                # This branch cannot fill its next isolated cell. Do not retain
                # its disproved snapshot if cancellation arrives at the next check.
                result.pop('partialLetters',None)
                result['stats'].pop('partialSupportedCells',None)
                best_partial_rank=(-1,-1)
            queue(states); continue
        key = tuple(letters)
        if key not in seen:
            seen.add(key); solution_words = []
            for j, slot in enumerate(slots):
                text = ''.join(letters[i] for i in slot['cells'])
                source = evidence[j].get(text, 'unverified')
                verified = source in ('dictionary', 'morphology')
                solution_words.append(dict(cells=slot['cells'], text=text, verified=verified, source=source))
            supported = sum(w['verified'] for w in solution_words)
            score = sum(word_score(w['text']) for w in solution_words)
            result['solutions'].append(dict(letters=letters, score=round(score,3), rawScore=score,
                                            supportedWords=supported, words=solution_words))
            if len(result['solutions']) > MAX_SOLUTIONS:
                result['solutions'].remove(min(result['solutions'], key=solution_rank))
                result['stats']['moreSolutions'] = True
    if pruned:
        result['diagnostics'].append('Queued search states reached the memory budget. Some alternatives were pruned; search is not exhaustive.')
    if unresolved:
        result['diagnostics'].append('Some unknown-word cells remain unresolved by dictionary evidence, crossings and number mappings; unrestricted guesses were not generated for them.')
        result['partialLetters'] = best_partial
    if not optional:
        # Strict partials are interruption snapshots, not evidence of a solution.
        # Exhausting their branches must not expose a disproved hypothesis.
        if previous_partial is None: result.pop('partialLetters',None)
        else: result['partialLetters']=previous_partial
        if previous_supported is None: result['stats'].pop('partialSupportedCells',None)
        else: result['stats']['partialSupportedCells']=previous_supported
    return not pruned and not optional


def _missing_word_search(p, slots, domains, evidence, base, rules, result, control):
    """Branch and bound over word placements, minimizing unsupported slots.

    A slot left without a compatible listed word becomes unsupported. Its
    letters come only from crossings, number mappings and confirmed cells,
    never from alphabet guesses. Requires one letter per number.
    """
    cells = p['cells']; language = p.get('language', 'en'); unique = rules['uniqueLetters']
    keys = [('n', str(int(c['number']))) if c.get('number') else ('c', i) for i, c in enumerate(cells)]
    slot_keys = [tuple(keys[i] for i in s['cells']) for s in slots]
    key_slots = {}
    for j, ks in enumerate(slot_keys):
        for k in set(ks): key_slots.setdefault(k, []).append(j)
    # Per-slot position index turns each new assignment into set operations.
    positions = []
    for j, words in enumerate(domains):
        if j % 8 == 0: control.check('preparing_missing_word_search')
        index = {}
        for word in words:
            for q, letter in enumerate(word): index.setdefault((q, letter), set()).add(word)
        positions.append(index)
    # Try least-constraining words first: letters that many crossing
    # candidates share. Static counts keep this cheap.
    crossings = [[] for _ in slots]; where = {}
    for j, slot in enumerate(slots):
        for q, i in enumerate(slot['cells']): where.setdefault(i, []).append((j, q))
    for i, places in where.items():
        for j, q in places:
            crossings[j].extend((q, other, r) for other, r in places if other != j)
    ranks = []
    for j, words in enumerate(domains):
        if j % 8 == 0: control.check('preparing_missing_word_search')
        support = {word: -sum(math.log1p(len(positions[other].get((r, word[q]), ()))) for q, other, r in crossings[j])
                   for word in words}
        ranks.append(support)
    empty = frozenset()
    assigned = {keys[i]: l for i, l in enumerate(base) if l and not cells[i].get('black')}

    def reduce(assigned, open_, cost, changed):
        """Apply new assignments to open domains; None when a hard rule fails."""
        touched = {j for k in changed for j in key_slots.get(k, ())}
        for j in touched:
            text = ''.join(assigned.get(k, '?') for k in slot_keys[j])
            if not _allowed(text, rules) or _rejected(slots[j], text, rules): return None
        claimed = {l: k for k, l in changed.items() if k[0] == 'n'} if unique else {}
        reduced = {}
        for j, words in open_.items():
            if claimed or j in touched:
                for q, k in enumerate(slot_keys[j]):
                    if not words: break
                    if k in changed: words = words & positions[j].get((q, changed[k]), empty)
                    elif k[0] == 'n' and k not in assigned and len(words) <= MISSING_WORD_EAGER:
                        # Large domains defer uniqueness to branching, avoiding
                        # copies of big sets; they are rarely the smallest domain.
                        for letter, owner in claimed.items():
                            if owner != k and (q, letter) in positions[j]: words = words - positions[j][(q, letter)]
            if not words or all(k in assigned for k in slot_keys[j]):
                cost += not words
                continue
            reduced[j] = words
        return reduced, cost

    state = reduce(assigned, {j: frozenset(d) for j, d in enumerate(domains)}, 0, {})
    if state is None: return
    # A cap on unsupported words abandons poor early placements. Under a
    # loose cap, depth-first search settles into placements that leave many
    # words unsupported and rarely backtracks out of them. So caps start at
    # one and widen geometrically while no hypothesis exists, and each
    # improvement restarts from the root with a cap just below it. Every
    # start gets a node slice scaled to the search budget.
    best_cost = 1; best_seen = None; found = {}; partial = None
    frames = []
    slice_nodes = max(MISSING_WORD_PHASE_NODES, control.node_limit // 40)

    def push(assigned, open_, cost):
        nonlocal best_cost, best_seen, partial
        if cost > best_cost: return
        if open_:
            j = min(open_, key=lambda j: (len(open_[j]), -len(slot_keys[j]), j))
            owned = {l for k, l in assigned.items() if k[0] == 'n'} if unique else ()
            free = [q for q, k in enumerate(slot_keys[j]) if k[0] == 'n' and k not in assigned]
            options = sorted((w for w in open_[j] if not any(w[q] in owned for q in free)), key=ranks[j].get) + [None]
            frames.append([assigned, open_, cost, j, options, 0])
            return
        letters = ['' if c.get('black') else assigned.get(keys[i], '') for i, c in enumerate(cells)]
        unresolved = sum(1 for i, c in enumerate(cells) if not c.get('black') and not letters[i])
        best_cost = min(best_cost, cost)
        best_seen = cost if best_seen is None else min(best_seen, cost)
        if unresolved:
            if partial is None or (cost, unresolved) < partial[0]: partial = ((cost, unresolved), letters)
        else:
            score = sum(_score(''.join(letters[i] for i in s['cells']), language, rules) for s in slots)
            found[tuple(letters)] = (cost, -score)
            if len(found) > MAX_SOLUTIONS: del found[max(found, key=found.get)]

    root = assigned
    began = result['stats']['nodes']; now = time.monotonic()
    # The last quarter of the budget goes to a dive without a cap when no
    # hypothesis exists yet, so a poor hypothesis still beats none.
    dive_nodes = control.node_limit - (control.node_limit - began) // 4
    dive_time = control.deadline - (control.deadline - now) / 4
    try:
        while True:
            start_seen = best_seen; next_cap = None
            # The dive tightens by branch and bound instead of restarting.
            push(root, *state); phase_end = result['stats']['nodes'] + slice_nodes if best_cost < len(slots) else control.node_limit
            while frames:
                control.check('missing_word_search')
                nodes = result['stats']['nodes']
                if nodes >= control.node_limit: raise _Stopped('budget_exhausted', 'node_limit')
                if best_seen is None and best_cost < len(slots) and (nodes >= dive_nodes or time.monotonic() >= dive_time):
                    next_cap = len(slots)
                elif nodes >= phase_end:
                    if best_seen is None: next_cap = max(best_cost + 1, best_cost * 3 // 2)
                    elif best_seen > 0 and (start_seen is None or best_seen < start_seen): next_cap = best_seen - 1
                    # This start did not improve: keep searching it.
                    else: phase_end = control.node_limit
                if next_cap is not None:
                    frames.clear(); break
                frame = frames[-1]
                assigned, open_, cost, j, options, k = frame
                if k == len(options) or cost > best_cost:
                    frames.pop(); continue
                frame[5] += 1; word = options[k]
                result['stats']['nodes'] += 1
                rest = {x: d for x, d in open_.items() if x != j}
                if word is None:
                    push(assigned, rest, cost+1); continue
                changed = {key: l for key, l in zip(slot_keys[j], word) if key not in assigned}
                child = {**assigned, **changed}
                reduced = reduce(child, rest, cost, changed)
                if reduced is not None: push(child, *reduced)
            if next_cap is None:
                # An exhausted tree leaves no better hypothesis in the candidates.
                if best_seen is not None or best_cost >= len(slots): break
                next_cap = max(best_cost + 1, best_cost * 3 // 2)
            best_cost = next_cap
    finally:
        # Budget stops and cancellation keep the best hypotheses found so far.
        _record_missing_word_results(p, slots, evidence, rules, result, found, partial)


def _record_missing_word_results(p, slots, evidence, rules, result, found, partial):
    language = p.get('language', 'en')
    ranked = sorted(found.items(), key=lambda item: item[1])[:MAX_SOLUTIONS]
    for letters, (cost, _) in ranked:
        letters = list(letters); words = []
        for j, slot in enumerate(slots):
            text = ''.join(letters[i] for i in slot['cells'])
            source = evidence[j].get(text, 'unverified')
            words.append(dict(cells=slot['cells'], text=text, verified=source in ('dictionary', 'morphology'), source=source))
        result['solutions'].append(dict(letters=letters, score=round(sum(_score(w['text'], language, rules) for w in words), 3),
                                        supportedWords=sum(w['verified'] for w in words), words=words))
    if ranked: result['stats']['unsupportedWords'] = ranked[0][1][0]
    elif partial:
        (cost, unresolved), letters = partial
        result['partialLetters'] = letters
        result['stats'].update(unsupportedWords=cost, unresolvedCells=unresolved,
                               partialSupportedCells=sum(1 for l in letters if l))
        result['diagnostics'].append(f'Best hypothesis leaves {cost} word(s) without dictionary support and {unresolved} cell(s) unresolved. Unresolved cells occur only in unsupported words; unrestricted guesses were not generated for them.')


LANGUAGE_NAMES = {'en': 'English', 'fi': 'Finnish', 'nl': 'Dutch', 'sv': 'Swedish'}


def language_models_for(puzzle, words):
    """Active scoring models: bundled, adapted to the word list when one is used."""
    language = puzzle.get('language', 'en') if isinstance(puzzle, dict) else 'en'
    if language not in ALPHABETS: return {}
    if puzzle.get('useDictionary', True) and isinstance(words, list) and len(words) <= MAX_WORDS_FOR_MODEL:
        return {language: language_model.adapted(language, words)}
    return {language: language_model.bundled(language)}


MAX_WORDS_FOR_MODEL = 1_000_000


def annotate_plausibility(puzzle, result):
    """Attach pattern assessments to solution words. They never verify words."""
    if not isinstance(puzzle, dict) or puzzle.get('language') not in ALPHABETS or not result.get('solutions'):
        return result
    language = puzzle['language']
    try: slots = {tuple(s['cells']): s for s in _slots(puzzle)}
    except (KeyError, TypeError, ValueError): return result
    cache = {}
    for solution in result['solutions']:
        for word in solution.get('words', []):
            slot = slots.get(tuple(word['cells']))
            flags = (slot['before'], slot['after']) if slot else (False, False)
            key = (word['text'],) + flags
            if key not in cache: cache[key] = language_model.plausibility(word['text'], language, *flags)
            word['plausibility'] = cache[key]
    model = language_model.active(language)
    name = LANGUAGE_NAMES[language]
    if model is None:
        result['diagnostics'].append(f'No trained {name} letter model is available; pattern checks use hand-tuned letter preferences only.')
    else:
        result['diagnostics'].append(f'Pattern checks compare each word with {name} letter sequences ({model.source}). “Typical” means word-like, not a verified word.')
    best = result['solutions'][0]
    suspicious = [w['text'] for w in best.get('words', []) if not w.get('verified') and w.get('plausibility', {}).get('label') == 'implausible']
    if suspicious and puzzle.get('useDictionary', True):
        shown = ', '.join(suspicious[:5]) + (' …' if len(suspicious) > 5 else '')
        result['diagnostics'].append(f'Unverified words with implausible {name} letter patterns in the top alternative: {shown}. Check the transcription or crossing words.')
    return result


def solve(puzzle, words, *, morphology=None, cancel=None, progress=None):
    # _solve adapts the models as a reported preparation stage.
    models = {}
    with language_model.use(models):
        result = _solve(puzzle, words, morphology=morphology, cancel=cancel, progress=progress, models=models)
        return annotate_plausibility(puzzle, result)


def _solve(puzzle, words, *, morphology=None, cancel=None, progress=None, models=None):
    started = time.monotonic()
    mode = puzzle.get('searchMode', 'quick') if isinstance(puzzle, dict) else 'quick'
    deep = mode in ('deep','extended')
    seconds = EXTENDED_SECONDS if mode == 'extended' else DEEP_SECONDS if deep else MAX_SECONDS
    node_limit = EXTENDED_NODES if mode == 'extended' else DEEP_NODES if deep else MAX_NODES
    result = dict(status='no_solution_found', solutions=[], diagnostics=[], stats=dict(
        nodes=0, exhaustive=False, candidateLimit=MAX_CANDIDATES, nodeLimit=node_limit,
        timeLimitSeconds=seconds, searchMode=mode, stopReason='search_exhausted', limitsReached=[],
        dictionaryCandidatesVisited=0, propagationRounds=0, solutionLimit=MAX_SOLUTIONS))
    control = _Control(started, seconds, node_limit, result, cancel, progress)
    try:
        control.check('preparing')
        checked = validate(puzzle)
        if not checked['valid']:
            result['stats']['stopReason']='invalid_constraints'
            result.update(status='conflict', diagnostics=checked['conflicts']); return result
        p = puzzle; rules = _rules(p); language = p.get('language','en'); cells = p['cells']; slots = _slots(p)
        base = ['' if c.get('black') else normalize(c.get('letter','')) for c in cells]
        base = _propagate(p, base, rules)
        result['forcedLetters'] = base[:]
        for slot in slots:
            if not _allowed(''.join(base[i] or '?' for i in slot['cells']), rules):
                result['stats']['stopReason']='invalid_constraints'
                result.update(status='conflict', diagnostics=['Fixed number mappings force a forbidden letter pattern.'])
                return result
        use_dictionary = p.get('useDictionary',True)
        if use_dictionary: control.check('adapting_letter_model')
        if models is not None: models.update(language_models_for(p, words))
        if not use_dictionary and rules['maxLettersPerNumber'] == 1:
            control.start_budget()
            return _global_heuristic(p, slots, base, rules, result, started, control.deadline, control)
        use_morphology = use_dictionary and language == 'fi' and p.get('useMorphology',True) and morphology is not None
        optional = use_dictionary and p.get('allowUnknownWords',False)
        control.check('indexing_dictionary')
        index = WordIndex(language, words, control.check, slots=slots) if use_dictionary else None
        if index is not None:
            result['stats'].update(dictionaryWordsTotal=index.size, dictionaryWordsIndexed=index.indexed_size)
            result['diagnostics'].append(f'Word-length filter kept {index.indexed_size:,} of {index.size:,} dictionary entries for this puzzle; longer source words remain eligible for open fragments.')
        control.start_budget()
        if use_dictionary and not index.size and not use_morphology and slots and not optional:
            result['stats']['stopReason']='empty_dictionary'
            result.update(status='empty_dictionary',diagnostics=['The selected dictionary is empty. Import words or disable the dictionary.'])
            return result
        result['stats']['method'] = 'indexed_constraint_propagation' if use_dictionary else 'bounded_variant_beam'
        clipped = False; domains = []; full_domains = []; evidence = []; morphology_clipped = False
        known, owners = _known_maps(cells, base)
        query_cache = {}
        for slot in slots:
            control.check('generating_candidates')
            found = {}; partial = slot['before'] or slot['after']
            if use_dictionary:
                candidates = index.candidates(p, slot, rules, control.check)
                for k, text in enumerate(candidates):
                    if k % 128 == 0: control.check()
                    result['stats']['dictionaryCandidatesVisited'] += 1
                    if _allowed(text, rules) and _compatible(slot,text,cells,base,rules,known,owners):
                        found[text] = 'fragment' if partial else 'dictionary'
                    # Collect broadly before ranking: words arrive alphabetically.
                    if len(found) > MISSING_WORD_CANDIDATES:
                        clipped = True; _limit_reached(result,'candidate_limit'); break
                if index.truncated: _limit_reached(result,'candidate_limit')
                if use_morphology and not partial:
                    cache_key = (tuple(str(int(cells[i]['number'])) if cells[i].get('number') else '' for i in slot['cells']),
                                 tuple(base[i] for i in slot['cells']))
                    if cache_key not in query_cache:
                        # Per-query slices prevent one broad SQL query consuming
                        # the entire full-grid run. Cancellation is checked between slices.
                        query_deadline = min(control.deadline, time.monotonic()+(.2 if deep else .05))
                        query_cache[cache_key] = morphology.match(p,slot,base,rules,query_deadline,limit=MISSING_WORD_CANDIDATES)
                    forms, cut = query_cache[cache_key]
                    morphology_clipped |= cut
                    if cut: _limit_reached(result,'morphology_query_limit')
                    for k,text in enumerate(forms):
                        if k % 128 == 0: control.check()
                        if _allowed(text,rules) and _compatible(slot,text,cells,base,rules,known,owners):
                            found.setdefault(text,'morphology')
            else:
                found = {text:'unverified' for text in _generated(slot,p,base,rules,control.deadline,control.check)}
            found = {text:source for text,source in found.items() if not _rejected(slot,text,rules)}
            ranked = sorted(found, key=lambda text:(-_score(text,language,rules),text))
            if len(ranked) > MAX_CANDIDATES:
                clipped = True; _limit_reached(result,'candidate_limit')
            ranked = tuple(ranked[:MISSING_WORD_CANDIDATES])
            domains.append(ranked[:MAX_CANDIDATES]); full_domains.append(ranked)
            evidence.append({text:found[text] for text in ranked})
        result['wordCandidates'] = [dict(cells=s['cells'], direction=s['direction'], candidates=list(d[:20]),
                partial=s['before'] or s['after'], verified=use_dictionary and not(s['before'] or s['after']))
                for s,d in zip(slots,domains)]
        if any(s['before'] or s['after'] for s in slots):
            result['diagnostics'].append('Open endpoints match dictionary fragments; fragments are not asserted to be complete words.')
        clipped |= bool(index and index.truncated)
        if clipped: _limit_reached(result,'candidate_limit')
        if morphology_clipped: _limit_reached(result,'morphology_query_limit')
        if clipped or morphology_clipped:
            result['diagnostics'].append('Candidate lists or local morphology queries were bounded/truncated. Search is not exhaustive.')
        if not use_dictionary:
            result['diagnostics'].append('Language-model candidates are unverified letter sequences, not known words. Beam search is not exhaustive.')
        full_deadline, full_nodes = control.deadline, control.node_limit
        if optional:
            # Strict search gets a fifth: printed puzzles rarely fit the word
            # list entirely, and missing-word search also finds complete fits.
            control.deadline = time.monotonic() + max(0, full_deadline-time.monotonic())*.2
            control.node_limit = max(1, full_nodes//5)
        try:
            exhaustive = _constraint_search(p,slots,domains,base,rules,result,control,evidence,use_dictionary)
        except _Stopped as stopped:
            if stopped.status != 'budget_exhausted' or not optional: raise
            exhaustive = False
            result['stats']['budgetReached'] = True
            result['stats']['stopReason'] = stopped.reason
            result['diagnostics'].append('Strict dictionary search reached its reserved budget; remaining time is available for missing-word fallback.')
        finally:
            control.deadline, control.node_limit = full_deadline, full_nodes
        if optional and not result['solutions']:
            result['stats']['stopReason']='search_exhausted'
            result['stats']['budgetReached']=False
            result['diagnostics'].append('Missing-word fallback allows unsupported words only when their letters follow from other word assignments or fixed mappings. Results may contain unverified words.')
            if rules['maxLettersPerNumber'] == 1:
                _missing_word_search(p,slots,full_domains,evidence,base,rules,result,control)
            else:
                _constraint_search(p,slots,domains,base,rules,result,control,evidence,use_dictionary,optional=True)
            exhaustive = False
        elif use_dictionary and not result['solutions']:
            result['diagnostics'].append('Printed puzzles often contain names or words missing from the word list. Enable “Allow words missing from the dictionary” to search with unsupported words.')
        result['stats']['exhaustive'] = use_dictionary and exhaustive and not optional and not clipped and not morphology_clipped
        result['solutions'].sort(key=lambda s:(-s.get('supportedWords',0),-s['score']))
        if use_morphology:
            control.check('collecting_evidence')
            forms = {w['text'] for solution in result['solutions'] for w in solution['words'] if w['source']=='morphology'}
            details = {}
            ordered_forms = sorted(forms)
            for k in range(0,len(ordered_forms),16):
                control.check()
                details.update(morphology.details(ordered_forms[k:k+16]))
            for solution in result['solutions']:
                for word in solution['words']:
                    if word['source']=='morphology': word['analyses'] = details.get(word['text'],[])
        if not result['solutions'] and not optional and any(not d for d in domains):
            result['stats']['stopReason']='no_candidates'
        if result['solutions']: result['status'] = 'budget_exhausted' if result['stats'].get('budgetReached') else 'solutions_found'
        else: result['diagnostics'].append('No solution found in the searched candidates. Check transcription, rules, open endpoints, and dictionary coverage; this is not proof the puzzle is impossible.')
        result['diagnostics'].append('Alternatives are ranked within the searched candidates; the highest-scoring global solution is not guaranteed.')
    except _Stopped as stopped:
        result['status'] = stopped.status
        result['stats']['stopReason'] = stopped.reason
        result['stats']['exhaustive'] = False
        if stopped.status == 'budget_exhausted':
            result['diagnostics'].append('Search stopped at the time or node budget; other solutions may exist.')
        else: result['diagnostics'].append('Search was cancelled; any returned suggestions are provisional.')
    finally:
        if result['stats']['limitsReached']: result['stats']['exhaustive']=False
        for solution in result['solutions']: solution.pop('rawScore', None)
        result.pop('preview', None)
        result.pop('previewMargins', None)
        if result['stats'].get('moreSolutions') and result['solutions']:
            result['diagnostics'].append(
                f'More than {MAX_SOLUTIONS} solutions fit the searched candidates; these are the {MAX_SOLUTIONS} highest-scoring.'
                if result['stats']['exhaustive'] else
                f'More than {MAX_SOLUTIONS} solutions were found; these are the {MAX_SOLUTIONS} highest-scoring found before the search stopped.')
        result['solutions'].sort(key=lambda s:(-s.get('supportedWords',0),-s['score']))
        if result.get('partialLetters') and not result['solutions'] and not any('unresolved' in d for d in result['diagnostics']):
            result['diagnostics'].append('Partial letters are provisional search hypotheses; unknown-word cells remain unresolved and these are not forced deductions.')
        result['stats']['elapsedSeconds'] = round(time.monotonic()-started,3)
        if progress:
            progress(dict(stage='finished', nodes=result['stats']['nodes'],
                          elapsedSeconds=result['stats']['elapsedSeconds'], solutionsFound=len(result['solutions'])))
    return result
