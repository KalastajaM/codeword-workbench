"""Scoped word search: local lists and jointly compatible selected alternatives.

This intentionally does not require unrelated slots to occur in the dictionary.
Dictionary membership is evidence of list inclusion, not semantic verification.
"""
import time
from itertools import chain
from .dictionaries import MAX_WORDS, clean_words, normalize
from .word_index import slot_length_filter
from . import language_model
from .solver import (_slots, _rules, _propagate, _local_ok, _mapping,
                     _allowed, _rejected, _generated, _score, validate, language_models_for)

MAX_SECONDS = 4.0
MAX_WORK = 200000
MAX_SLOTS = 8
MAX_CANDIDATES = 200
MAX_COMBINATIONS = 20


def find_candidates(puzzle, words, slot_ids, morphology=None):
    with language_model.use(language_models_for(puzzle, words)):
        return _find_candidates(puzzle, words, slot_ids, morphology)


def _find_candidates(puzzle, words, slot_ids, morphology=None):
    started = time.monotonic()
    deadline = started + MAX_SECONDS
    checked = validate(puzzle)
    if not checked['valid']:
        return dict(status='conflict', words=[], combinations=[],
                    diagnostics=checked['conflicts'], stats={'exhaustive': False})
    all_slots = _slots(puzzle)
    if (not isinstance(slot_ids, list) or not 1 <= len(slot_ids) <= MAX_SLOTS
            or any(type(i) is not int or not 0 <= i < len(all_slots) for i in slot_ids)
            or len(set(slot_ids)) != len(slot_ids)):
        raise ValueError('Select 1 to 8 distinct valid word slot IDs.')
    rules = _rules(puzzle)
    language = puzzle.get('language', 'en')
    dictionary_mode = puzzle.get('useDictionary', True)
    if language != 'fi' or not dictionary_mode or not puzzle.get('useMorphology',True): morphology=None
    base = ['' if c.get('black') else normalize(c.get('letter', '')) for c in puzzle['cells']]
    base = _propagate(puzzle, base, rules)
    selected = [all_slots[i] for i in slot_ids]
    eligible_length = slot_length_filter(selected)
    result = dict(status='no_candidates_found', words=[], combinations=[], diagnostics=[
        'Search is scoped to the selected words. Unselected words need not be in the dictionary; confirmed letters and number mappings anywhere still constrain candidates.'
    ], stats=dict(work=0, exhaustive=False, timeLimitSeconds=MAX_SECONDS,
                  workLimit=MAX_WORK, candidateLimit=MAX_CANDIDATES,
                  combinationLimit=MAX_COMBINATIONS))
    for slot_id, slot in zip(slot_ids, selected):
        first = slot['cells'][0]
        result['words'].append(dict(slotId=slot_id, cells=slot['cells'], direction=slot['direction'],
                                   row=first // puzzle['cols'] + 1, col=first % puzzle['cols'] + 1,
                                   pattern=''.join(base[i] or '?' for i in slot['cells']),
                                   candidates=[], truncated=False,
                                   partial=slot['before'] or slot['after'],
                                   source='dictionary' if dictionary_mode else 'heuristic'))
    # Normalize once in bounded batches, then index by word length. Dictionary
    # scans are not compatibility search nodes: fixed-letter prefilters remove
    # impossible strings before spending the shared work budget.
    by_length = {}
    has_dictionary_words = False
    preprocessing_complete = True
    if dictionary_mode:
        if not isinstance(words, list) or len(words) > MAX_WORDS:
            raise ValueError(f'Expected a list of at most {MAX_WORDS:,} words.')
        for offset in range(0, len(words), 2048):
            if time.monotonic() >= deadline:
                preprocessing_complete = False
                break
            batch = clean_words(language, words[offset:offset + 2048])
            has_dictionary_words |= bool(batch)
            for word in batch:
                if not eligible_length(len(word)): continue
                by_length.setdefault(len(word), set()).add(word)
        if preprocessing_complete:
            for length, bucket in by_length.items():
                if time.monotonic() >= deadline:
                    preprocessing_complete = False
                    break
                by_length[length] = sorted(bucket)
    result['stats'].update(dictionaryWords=sum(len(bucket) for bucket in by_length.values()),
                           preprocessingComplete=preprocessing_complete)

    if dictionary_mode:
        result['diagnostics'].append('Word-list candidates occur in the selected list (or match a fragment with open endpoints); membership does not establish the intended answer or semantic correctness.')
    else:
        result['diagnostics'].append('Generated candidates are unverified letter sequences. Beam pruning makes this search nonexhaustive.')
    if morphology is not None and dictionary_mode:
        result['diagnostics'].append('Local Kotus/Omorfi forms supplement the word list. Coverage is bounded: nominal cases and active indicative present/past verbs, without productive compound expansion, possessive suffixes or clitics. Morphological generation does not establish the intended answer. Open fragments use the word list only. Up to six source analyses are shown per candidate.')
    work = 0
    budget_hit = not preprocessing_complete
    combo_limited = False

    def exhausted():
        return work >= MAX_WORK or time.monotonic() >= deadline

    def compatible(slot, text, letters):
        if _rejected(slot, text, rules) or not _local_ok(slot, text, puzzle, letters, rules):
            return None
        trial = letters[:]
        for i, letter in zip(slot['cells'], text):
            trial[i] = letter
        trial = _propagate(puzzle, trial, rules)
        if rules['forbiddenPatterns'] or rules['rejectedWords']:
            # Unselected dictionary coverage is irrelevant, but an explicit
            # hard rule still applies to letters forced there by a mapping.
            for other in all_slots:
                other_text = ''.join(trial[i] or '?' for i in other['cells'])
                if not _allowed(other_text, rules) or _rejected(other, other_text, rules):
                    return None
        return trial

    for slot, output in zip(selected, result['words']):
        found = set()
        origins = {}
        length = len(slot['cells'])
        if exhausted() or not preprocessing_complete:
            budget_hit = True
            output['truncated'] = True
            continue
        if dictionary_mode:
            fixed_positions = [(position, base[i]) for position, i in enumerate(slot['cells']) if base[i]]
            if slot['before'] or slot['after']:
                dictionary = chain.from_iterable(by_length[size] for size in sorted(by_length) if size >= length)
            else:
                dictionary = by_length.get(length, ())
            for word in dictionary:
                if exhausted():
                    budget_hit = True
                    output['truncated'] = True
                    break

                if slot['before'] and slot['after']:
                    matches = (word[i:i + length] for i in range(len(word) - length + 1))
                elif slot['before']:
                    matches = [word[-length:]]
                elif slot['after']:
                    matches = [word[:length]]
                else:
                    matches = [word] if len(word) == length else []
                for text in matches:
                    if exhausted():
                        budget_hit = True
                        output['truncated'] = True
                        break
                    if text in found:
                        # A fragment seen earlier may also be a listed word.
                        if text == word: origins[text] = 'dictionary'
                        continue
                    if any(text[position] != letter for position, letter in fixed_positions):
                        continue
                    work += 1
                    if _allowed(text, rules) and compatible(slot, text, base) is not None:
                        found.add(text)
                        origins[text] = 'fragment' if text != word else 'dictionary'
                    if len(found) > MAX_CANDIDATES:
                        output['truncated'] = True
                        break
                if output['truncated']:
                    break
        else:
            found = {text for text in _generated(slot, puzzle, base, rules, deadline)
                     if compatible(slot, text, base) is not None}
            # The generator uses a beam, so its absence of candidates cannot
            # establish impossibility. Mark local coverage incomplete as well.
            output['truncated'] = True
            if time.monotonic() >= deadline:
                budget_hit = True
        if dictionary_mode and morphology is not None:
            additions, incomplete = morphology.match(puzzle,slot,base,rules,deadline)
            output['truncated'] = output['truncated'] or incomplete
            for text in additions:
                if exhausted():
                    budget_hit=True;output['truncated']=True;break
                work += 1
                if _allowed(text,rules) and compatible(slot,text,base) is not None:
                    found.add(text)
                    origins.setdefault(text,'morphology')
            if len(found)>MAX_CANDIDATES: output['truncated']=True
        flags = (slot['before'], slot['after'])
        output['candidates'] = sorted(found, key=lambda t: (-_score(t, language, rules, *flags), t))[:MAX_CANDIDATES]
        output['candidatePlausibility'] = {text: language_model.plausibility(text, language, *flags)
                                           for text in output['candidates']}
        # Where each candidate came from: listed word, fragment of a listed
        # word, Finnish form index only, or a generated (unverified) guess.
        output['candidateEvidence'] = {text: dict(source=origins.get(text, 'generated'),
                                                  inDictionary=origins.get(text) == 'dictionary')
                                       for text in output['candidates']}
        if dictionary_mode:
            output['candidateDetails'] = morphology.details(output['candidates']) if morphology is not None else {}
            for text in output['candidates']:
                if text in found and (len(text) in by_length and text in by_length[len(text)]):
                    output['candidateDetails'].setdefault(text,[]).append(dict(lemma='',analysis='Listed surface form',source='Current word list'))


    # Depth is at most eight. Keep one branch per level instead of constructing
    # a frontier containing copies of the entire grid for every alternative.
    order = sorted(range(len(selected)), key=lambda j: len(result['words'][j]['candidates']))
    chosen = {}

    def combine(depth, letters):
        nonlocal work, budget_hit, combo_limited
        if exhausted():
            budget_hit = True
            return
        if len(result['combinations']) >= MAX_COMBINATIONS:
            combo_limited = True
            return
        if depth == len(order):
            selected_letters = [''] * len(letters)
            for slot in selected:
                for i in slot['cells']:
                    selected_letters[i] = letters[i]
            result['combinations'].append(dict(
                words=[dict(slotId=slot_id, text=chosen[j]) for j, slot_id in enumerate(slot_ids)],
                letters=selected_letters,
                score=round(sum(_score(text, language, rules) for text in chosen.values()), 3)))
            return
        j = order[depth]
        slot = selected[j]
        for text in result['words'][j]['candidates']:
            if exhausted():
                budget_hit = True
                return
            if len(result['combinations']) >= MAX_COMBINATIONS:
                combo_limited = True
                return
            work += 1
            trial = compatible(slot, text, letters)
            if trial is None:
                continue
            # Mapping checks include all fixed cells, while only selected
            # slots receive dictionary constraints.
            if not _mapping(puzzle['cells'], trial, rules):
                continue
            chosen[j] = text
            combine(depth + 1, trial)
            chosen.pop(j)

    combine(0, base)
    result['combinations'].sort(key=lambda c: -c['score'])
    result['stats'].update(work=work, elapsedSeconds=round(time.monotonic() - started, 3),
                           exhaustive=dictionary_mode and not budget_hit and not combo_limited
                           and not any(w['truncated'] for w in result['words']))
    if any(w['candidates'] for w in result['words']):
        result['status'] = 'candidates_found'
    elif budget_hit:
        result['status'] = 'budget_exhausted'
    elif dictionary_mode and not has_dictionary_words:
        result['status'] = 'empty_dictionary'
    if budget_hit:
        result['diagnostics'].append('Time or work budget reached. Some lists or combinations may be incomplete.')
    if any(w['truncated'] for w in result['words']):
        result['diagnostics'].append('At least one local list is incomplete because of a candidate limit, search budget, or heuristic beam pruning.')
    if combo_limited:
        result['diagnostics'].append('Combination limit reached; additional compatible combinations may exist.')
    if not result['combinations']:
        result['diagnostics'].append('No joint combination was found in the searched lists. Each local candidate list remains available independently; this is not proof of impossibility.')
    result['diagnostics'].append('Ranking compares explored candidates only; the highest-scoring combination is not guaranteed.')
    return result
