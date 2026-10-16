"""Ruled-out letters per number and rejected words per slot, for one puzzle.

Both are user decisions and act as hard constraints. Suggested ruled-out
letters come from the bundled character statistics: a letter run that the
training words practically never contain. That is language-pattern evidence,
not proof, so suggestions are only applied when the user accepts them.
"""
from .dictionaries import ALPHABETS, normalize
from . import language_model

MAX_REJECTED_WORDS = 1000
DIRECTIONS = ('Across', 'Down')


def check(puzzle, language):
    """Validate and normalize both fields in place; raise ValueError."""
    alphabet = set(ALPHABETS[language])
    eliminations = puzzle.get('eliminations', {})
    if not isinstance(eliminations, dict) or len(eliminations) > 99:
        raise ValueError('Ruled-out letters must map numbers to letter lists.')
    normalized = {}
    for number, letters in eliminations.items():
        if not isinstance(number, str) or not number.isascii() or not number.isdecimal() or not 1 <= int(number) <= 99:
            raise ValueError('Ruled-out letters belong to numbers from 1 to 99.')
        if not isinstance(letters, list) or len(letters) > len(alphabet) or any(not isinstance(l, str) for l in letters):
            raise ValueError('Ruled-out letters must be a list of letters.')
        letters = {normalize(l.strip()) for l in letters}
        if any(len(l) != 1 or l not in alphabet for l in letters):
            raise ValueError('Ruled-out letters must come from the selected alphabet.')
        if letters:
            key = str(int(number))
            normalized[key] = sorted(set(normalized.get(key, ())) | letters)
    puzzle['eliminations'] = normalized
    rejected = puzzle.get('rejectedWords', [])
    if not isinstance(rejected, list) or len(rejected) > MAX_REJECTED_WORDS:
        raise ValueError(f'Rejected words must be a list of at most {MAX_REJECTED_WORDS:,} entries.')
    cleaned = []; seen = set()
    for entry in rejected:
        if (not isinstance(entry, dict) or type(entry.get('start')) is not int or entry['start'] < 0
                or entry.get('direction') not in DIRECTIONS or not isinstance(entry.get('word'), str)):
            raise ValueError('Each rejected word needs a start cell, a direction and a word.')
        word = normalize(entry['word'].strip())
        if not 2 <= len(word) <= 40 or not set(word) <= alphabet:
            raise ValueError('Rejected words must have 2 to 40 letters of the selected alphabet.')
        # A resized grid can leave entries behind; they have no slot, so drop them.
        if entry['start'] >= len(puzzle['cells']): continue
        key = (entry['start'], entry['direction'], word)
        if key not in seen:
            seen.add(key); cleaned.append(dict(start=key[0], direction=key[1], word=word))
    puzzle['rejectedWords'] = cleaned


def excluded_letters(puzzle):
    """{number: frozenset(letters)} from a puzzle, tolerating malformed input."""
    result = {}
    value = puzzle.get('eliminations') if isinstance(puzzle, dict) else None
    if not isinstance(value, dict): return result
    for number, letters in value.items():
        if isinstance(number, str) and number.isdecimal() and isinstance(letters, list):
            letters = frozenset(normalize(l) for l in letters if isinstance(l, str))
            if letters: result[str(int(number))] = result.get(str(int(number)), frozenset()) | letters
    return result


def rejected_words(puzzle):
    """{(start cell, direction): frozenset(words)} from a puzzle."""
    result = {}
    value = puzzle.get('rejectedWords') if isinstance(puzzle, dict) else None
    if not isinstance(value, list): return result
    for entry in value:
        if isinstance(entry, dict) and isinstance(entry.get('word'), str):
            key = (entry.get('start'), entry.get('direction'))
            result[key] = result.get(key, frozenset()) | {normalize(entry['word'])}
    return result


def conflicts(puzzle, slots, letters, rules):
    """Confirmed letters that contradict ruled-out letters or rejected words."""
    errors = []
    excluded = rules['excludedLetters']
    for cell, letter in zip(puzzle['cells'], letters):
        if letter and not cell.get('black') and cell.get('number') and letter in excluded.get(str(int(cell['number'])), ()):
            errors.append(f'Number {int(cell["number"])} has confirmed letter {letter}, which is ruled out.')
            break
    for slot in slots:
        text = ''.join(letters[i] or '?' for i in slot['cells'])
        if text in rules['rejectedWords'].get((slot['cells'][0], slot['direction']), ()):
            errors.append(f'Confirmed letters spell {text}, which is rejected for this word.')
            break
    return errors


def suggest(puzzle, slots, letters, rules, model=None):
    """Letters a number probably cannot be: [{number, letter, run}].

    `letters` are confirmed and mapping-forced letters per cell. Only runs of
    two or three symbols are used: bundled models keep every pair and every
    triple seen at least twice, so absence means practically never seen.
    """
    language = puzzle.get('language', 'en')
    model = model or language_model.bundled(language)
    if model is None or rules['maxLettersPerNumber'] != 1: return []
    cells = puzzle['cells']
    numbers = {}
    for i, c in enumerate(cells):
        if not c.get('black') and c.get('number'): numbers.setdefault(str(int(c['number'])), []).append(i)
    owned = {}
    for n, indices in numbers.items():
        for i in indices:
            if letters[i]: owned[n] = letters[i]
    taken = set(owned.values()) if rules['uniqueLetters'] else set()
    single_forbidden = {normalize(p) for p in rules['forbiddenPatterns'] if len(normalize(p)) == 1}
    alphabet = [l for l in ALPHABETS[language] if l not in single_forbidden]
    through = {}
    for slot in slots:
        for position, i in enumerate(slot['cells']): through.setdefault(i, []).append((slot, position))
    suggestions = []
    for n in sorted(numbers, key=int):
        if n in owned: continue
        candidates = [l for l in alphabet if l not in taken and l not in rules['excludedLetters'].get(n, ())]
        if len(candidates) < 2: continue
        ruled = {}
        for i in numbers[n]:
            for slot, position in through.get(i, ()):
                for run in _windows(slot, position, cells, letters, n):
                    texts = {l: run.replace('#', l) for l in candidates}
                    absent = {l for l, text in texts.items() if not model.counts.get(text)}
                    # A context that excludes every letter says more about
                    # the known letters (or a misread number) than about this one.
                    if len(absent) == len(candidates): continue
                    for l in absent: ruled.setdefault(l, texts[l])
        suggestions.extend(dict(number=n, letter=l, run=ruled[l].strip('^$')) for l in candidates if l in ruled)
    return suggestions


def _windows(slot, position, cells, letters, number):
    """Runs of 2–3 symbols around `position` with every other symbol known.

    The number's own cells are '#'; closed word ends are '^' and '$', as in
    the model's padding. Open ends have no boundary symbol.
    """
    symbols = ([] if slot['before'] else ['^'])
    offset = len(symbols)
    for i in slot['cells']:
        c = cells[i]
        symbols.append('#' if c.get('number') and str(int(c['number'])) == number else letters[i] or None)
    if not slot['after']: symbols.append('$')
    centre = position + offset
    runs = []
    for size in (2, 3):
        for start in range(centre - size + 1, centre + 1):
            window = symbols[start:start + size] if start >= 0 else []
            if len(window) == size and None not in window and not (window[0] == '^' and window[-1] == '$'):
                runs.append(''.join(window))
    return runs
