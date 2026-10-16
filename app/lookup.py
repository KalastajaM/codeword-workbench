"""Single-word lookup and manual pattern search such as "A 12 12 K 5".

Pattern tokens: a letter is known, a number stands for one puzzle number
(the same number is the same letter), and ? . _ or * is any letter. Numbers
follow the puzzle's mapping rules, so with unique letters two different
numbers, or a number and a typed letter, cannot share a letter.
"""
import re

from . import language_model
from .candidates import find_candidates
from .dictionaries import ALPHABETS, normalize
from .eliminations import excluded_letters
from .solver import _rules, _slots, language_models_for

MAX_TOKENS = 40
WILDCARDS = '?._*'
_TOKEN = re.compile(r'(\d+)|([?._*])|(\S)')


def parse_pattern(language, text):
    """Return [('number', '12') | ('letter', 'A') | ('any', None)]."""
    if language not in ALPHABETS:
        raise ValueError('Unsupported language.')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Enter a word or a pattern such as A 12 12 K 5.')
    alphabet = set(ALPHABETS[language])
    tokens = []
    for match in _TOKEN.finditer(normalize(text)):
        number, wildcard, letter = match.groups()
        if number is not None:
            if not 1 <= int(number) <= 99:
                raise ValueError('Pattern numbers must be from 1 to 99.')
            tokens.append(('number', str(int(number))))
        elif wildcard is not None:
            tokens.append(('any', None))
        elif letter in alphabet:
            tokens.append(('letter', letter))
        else:
            raise ValueError(f'“{letter}” is not a letter of the selected alphabet, a number, or a ? wildcard.')
    if len(tokens) > MAX_TOKENS:
        raise ValueError(f'Patterns can have at most {MAX_TOKENS} letters.')
    return tokens


def lookup_word(puzzle, word, words, morphology=None, word_set=None):
    """Report dictionary membership and the pattern check for one word."""
    language = puzzle['language']
    with language_model.use(language_models_for(dict(puzzle, useDictionary=True), words)):
        plausibility = language_model.plausibility(word, language)
    forms = morphology.details([word]).get(word, []) if morphology is not None else []
    in_dictionary = word in (word_set if word_set is not None else set(words))
    diagnostics = ['Dictionary membership means the word is in your list or form index, not that it is the intended answer.',
                   'The pattern check compares letter sequences only. It cannot prove a word exists, and names, loanwords and compounds can look unusual.']
    return dict(kind='word', word=word, inDictionary=in_dictionary, inMorphology=bool(forms),
                analyses=forms, plausibility=plausibility, diagnostics=diagnostics)


def pattern_search(puzzle, text, words, morphology=None, use_mappings=True):
    """Search words matching a pattern under the puzzle's language and rules."""
    language = puzzle['language']
    tokens = parse_pattern(language, text)
    if all(kind == 'letter' for kind, _ in tokens):
        return lookup_word(puzzle, ''.join(value for _, value in tokens), words, morphology)
    if len(tokens) < 2:
        raise ValueError('A pattern needs at least two letters, numbers or wildcards.')
    rules = _rules(puzzle)
    known = {}
    if use_mappings:
        for cell in puzzle['cells']:
            if not cell.get('black') and cell.get('number') and cell.get('letter'):
                known[str(int(cell['number']))] = normalize(cell['letter'])
    owner = {letter: number for number, letter in known.items()}
    used = {value for kind, value in tokens if kind == 'number'} | set(known)
    spare = (str(n) for n in range(99, 0, -1) if str(n) not in used)
    # Typed letters belong to some number. Give each a stand-in number so
    # unique-letter rules keep other numbers from taking it.
    letter_numbers = {}
    cells = []
    for kind, value in tokens:
        if kind == 'number':
            cells.append(dict(black=False, number=value, letter=known.get(value, '')))
        elif kind == 'letter':
            if value not in owner and value not in letter_numbers:
                letter_numbers[value] = next(spare)
            cells.append(dict(black=False, number=owner.get(value) or letter_numbers[value], letter=value))
        else:
            cells.append(dict(black=False, number='', letter=''))
    pattern_numbers = {value for kind, value in tokens if kind == 'number'}
    typed = {value for kind, value in tokens if kind == 'letter'}
    # Known mappings outside the pattern occupy isolated cells (black around
    # them), so they constrain letter ownership without forming words.
    extras = [(n, l) for n, l in known.items() if n not in pattern_numbers and l not in typed]
    black = dict(black=True, number='', letter='')
    cols = max(len(tokens), 39) if extras else len(tokens)
    rows = [cells + [dict(black) for _ in range(cols - len(tokens))]]
    per_row = (cols + 1) // 2
    for start in range(0, len(extras), per_row):
        rows.append([dict(black) for _ in range(cols)])
        row = [dict(black) for _ in range(cols)]
        for k, (n, l) in enumerate(extras[start:start + per_row]):
            row[2 * k] = dict(black=False, number=n, letter=l)
        rows.append(row)
    trial = dict(rows=len(rows), cols=cols, language=language, rules=rules,
                 useDictionary=puzzle.get('useDictionary', True), useMorphology=puzzle.get('useMorphology', True),
                 cells=[c for row in rows for c in row])
    if use_mappings:
        # Stand-in numbers are spare numbers, so only pattern numbers keep ruled-out letters.
        excluded = excluded_letters(puzzle)
        trial['eliminations'] = {n: sorted(excluded[n]) for n in pattern_numbers if n in excluded}
    slot_id = next(i for i, slot in enumerate(_slots(trial)) if slot['cells'] == list(range(len(tokens))))
    result = find_candidates(trial, words, [slot_id], morphology)
    result['diagnostics'] = [d for d in result['diagnostics'] if not d.startswith('Search is scoped to the selected words')
                             and not d.startswith('No joint combination')]
    found = result['words'][0]
    shown = ' '.join(value if kind != 'any' else '?' for kind, value in tokens)
    applied = sorted((n for n in known if any(k == 'number' and v == n for k, v in tokens)), key=int)
    result['diagnostics'].insert(0, 'Same number means same letter.' + (' Different numbers and typed letters use different letters.' if rules['uniqueLetters'] else ''))
    if applied:
        result['diagnostics'].insert(1, 'Applied confirmed puzzle mappings: ' + ', '.join(f'{n}={known[n]}' for n in applied) + '.')
    return dict(kind='pattern', pattern=shown, candidates=found['candidates'], truncated=found['truncated'],
                candidateDetails=found.get('candidateDetails', {}), candidatePlausibility=found.get('candidatePlausibility', {}),
                candidateEvidence=found.get('candidateEvidence', {}), source=found['source'], status=result['status'],
                diagnostics=result['diagnostics'], stats=result['stats'])
