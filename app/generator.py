"""Fill a drawn grid with dictionary words and number it as a codeword.

The user draws the black cells and may fix some numbers and letters. Every
word of two or more cells is filled from the active dictionary, no word is
used twice, cells that share a number get the same letter and different
numbers get different letters. The fill is a randomised backtracking search
with restarts that stops at a time limit. Not finding a fill in time does not
prove that none exists; only a search that ran out of options says so.

The numbered grid is then searched again for every answer that fits, with
repeated words allowed, as a solver would. While a second answer exists, a
letter that tells the two apart is given and the grid is checked again. Only
a search that ran out of options confirms a single answer, and only within
this dictionary.

Difficulty is graded by solving the numbered grid as a person would. Easy:
words that only one dictionary word fits solve the whole grid. Medium: that
also needs letters every fitting word agrees on. Hard: neither is enough.
When a grid comes out harder than asked for, letters are given until it fits.
Words the user asks for are placed before the rest of the grid is filled.
"""
import random
import time

from .dictionaries import ALPHABETS, normalize

DEFAULT_SECONDS = 20
MAX_SECONDS = 120
MAX_STARTERS = 10
MAX_SLOTS = 800
MAX_INCLUDE = 30
DIFFICULTIES = ('easy', 'medium', 'hard', 'any')
STARTER_ATTEMPTS = 6
LEVELS = ('easy', 'medium', 'hard')


class _Stop(Exception):
    pass


class _Restart(Exception):
    pass


class _Enough(Exception):
    pass


def _position(i, cols):
    return f'row {i // cols + 1}, column {i % cols + 1}'


def layout(puzzle):
    """Word slots (lists of cell indices) of a drawable grid, or ValueError."""
    rows, cols, cells = puzzle['rows'], puzzle['cols'], puzzle['cells']
    rules = puzzle.get('rules') or {}
    if rules.get('maxLettersPerNumber', 1) != 1 or rules.get('uniqueLetters', True) is not True:
        raise ValueError('Generating needs the standard rules: one letter per number and a different letter for each number.')
    flags = ('openBeforeAcross', 'openAfterAcross', 'openBeforeDown', 'openAfterDown')
    if any(cell.get(flag) for cell in cells for flag in flags):
        raise ValueError('A generated puzzle has closed word ends. Clear the open word-boundary marks first.')
    slots = []
    for across in (True, False):
        for line in range(rows if across else cols):
            run = []
            for offset in range((cols if across else rows) + 1):
                i = line * cols + offset if across else offset * cols + line
                if offset < (cols if across else rows) and not cells[i].get('black'):
                    run.append(i)
                    continue
                if len(run) >= 2:
                    slots.append(run)
                run = []
    if not slots:
        raise ValueError('Draw at least one word of two or more letter cells.')
    if len(slots) > MAX_SLOTS:
        raise ValueError(f'The grid has {len(slots)} words; generating supports up to {MAX_SLOTS}.')
    covered = {i for slot in slots for i in slot}
    loose = [i for i, cell in enumerate(cells) if not cell.get('black') and i not in covered]
    if loose:
        more = f' and {len(loose) - 1} more' if len(loose) > 1 else ''
        raise ValueError(f'The letter cell at {_position(loose[0], cols)}{more} is not part of any word. '
                         'Make it black or extend a word through it.')
    letter_of, number_of = {}, {}
    for cell in cells:
        number, letter = cell.get('number', ''), cell.get('letter', '')
        if cell.get('black') or not number or not letter:
            continue
        if letter_of.setdefault(number, letter) != letter:
            raise ValueError(f'Number {number} has two different letters ({letter_of[number]} and {letter}).')
        if number_of.setdefault(letter, number) != number:
            raise ValueError(f'Letter {letter} is given to two numbers ({number_of[letter]} and {number}).')
    return slots


class _Filler:
    """Backtracking over slots, smallest candidate set first.

    Candidates are bitmasks over the words of one length, so narrowing a slot
    by its known letters is a handful of big-integer ANDs.
    """

    def __init__(self, puzzle, slots, words, rng, deadline, cancel, progress, distinct=True, stage='filling', include=()):
        self.cells, self.slots, self.rng = puzzle['cells'], slots, rng
        self.deadline, self.cancel, self.progress = deadline, cancel, progress
        self.distinct, self.stage, self.found = distinct, stage, None
        lengths = {len(slot) for slot in slots}
        self.words, self.masks, self.full, index = {}, {}, {}, {}
        for length in lengths:
            group = [w for w in words if len(w) == length]
            rng.shuffle(group)
            self.words[length] = group
            index.update((word, k) for k, word in enumerate(group))
            masks = [{} for _ in range(length)]
            for k, word in enumerate(group):
                bit = 1 << k
                for pos, letter in enumerate(word):
                    masks[pos][letter] = masks[pos].get(letter, 0) | bit
            self.masks[length] = masks
            self.full[length] = (1 << len(group)) - 1
        self.letters = {}
        self.number_letter, self.letter_number = {}, {}
        for i, cell in enumerate(self.cells):
            if cell.get('black'):
                continue
            letter, number = cell.get('letter', ''), cell.get('number', '')
            if letter:
                self.letters[i] = letter
            if letter and number:
                self.number_letter[number] = letter
                self.letter_number[letter] = number
        self.used = {length: 0 for length in lengths}
        self.nodes = self.restarts = 0
        self.last_report = 0.0
        self.forbidden = {}
        # Words to include, longest first: they are placed before any other slot.
        self.include = [(len(word), index[word]) for word in sorted(include, key=lambda w: (-len(w), w))]

    def known(self, i):
        letter = self.letters.get(i)
        if letter:
            return letter
        number = self.cells[i].get('number', '')
        return self.number_letter.get(number, '') if number else ''

    def options(self, slot):
        length = len(slot)
        mask = self.full[length] & ~self.used[length]
        masks = self.masks[length]
        for pos, i in enumerate(slot):
            letter = self.known(i)
            if letter:
                mask &= masks[pos].get(letter, 0)
            elif self.cells[i].get('number') and self.letter_number:
                # A numbered cell cannot take a letter that belongs to another
                # number. Cached until the number mappings change.
                key = (length, pos)
                if key not in self.forbidden:
                    taken = 0
                    for owned in self.letter_number:
                        taken |= masks[pos].get(owned, 0)
                    self.forbidden[key] = taken
                mask &= ~self.forbidden[key]
            if not mask:
                return 0
        return mask

    def place(self, slot, word):
        """Set the word's letters; return what to undo, or None when its numbers clash."""
        set_cells, set_numbers = [], []
        for i, letter in zip(slot, word):
            number = self.cells[i].get('number', '')
            if number:
                # The masks checked the grid before this word; two cells of
                # the word itself can still clash with each other.
                mapped = self.number_letter.get(number)
                owner = self.letter_number.get(letter)
                if (mapped and mapped != letter) or (owner and owner != number):
                    self.undo((set_cells, set_numbers))
                    return None
                if not mapped:
                    self.number_letter[number] = letter
                    self.letter_number[letter] = number
                    set_numbers.append(number)
                    self.forbidden.clear()
            if i not in self.letters:
                self.letters[i] = letter
                set_cells.append(i)
        return set_cells, set_numbers

    def undo(self, change):
        set_cells, set_numbers = change
        for i in set_cells:
            del self.letters[i]
        for number in set_numbers:
            del self.letter_number[self.number_letter.pop(number)]
        if set_numbers:
            self.forbidden.clear()

    def tick(self):
        now = time.monotonic()
        if self.cancel():
            raise _Stop('cancelled')
        if now > self.deadline:
            raise _Stop('time_limit')
        if now - self.last_report > 0.25:
            self.last_report = now
            self.progress(dict(stage=self.stage, nodes=self.nodes, restarts=self.restarts))

    def members(self, mask):
        """Set bits of mask, starting at a random bit and wrapping around."""
        start = self.rng.randrange(mask.bit_length())
        for part, offset in ((mask >> start, start), (mask & ((1 << start) - 1), 0)):
            while part:
                low = part & -part
                yield offset + low.bit_length() - 1
                part ^= low

    def search(self, open_slots, budget, included=0):
        self.tick()
        if included < len(self.include):
            return self.search_include(open_slots, budget, included)
        if not open_slots:
            if self.found is None:
                return True
            self.found.append(dict(self.letters))
            if len(self.found) >= self.limit:
                raise _Enough()
            return False
        best = best_mask = None
        for slot in open_slots:
            mask = self.options(slot)
            if not mask:
                return False
            if best is None or mask.bit_count() < best_count:
                best, best_mask, best_count = slot, mask, mask.bit_count()
                if best_count == 1:
                    break
        rest = [slot for slot in open_slots if slot is not best]
        length = len(best)
        for k in self.members(best_mask):
            self.nodes += 1
            if self.nodes > budget:
                raise _Restart()
            change = self.place(best, self.words[length][k])
            if change is None:
                continue
            if self.distinct:
                self.used[length] |= 1 << k
            if self.search(rest, budget, included):
                return True
            if self.distinct:
                self.used[length] &= ~(1 << k)
            self.undo(change)
        return False

    def search_include(self, open_slots, budget, included):
        """Place the next word to include in each slot it fits, in random order."""
        length, k = self.include[included]
        fits = [slot for slot in open_slots if len(slot) == length and self.options(slot) >> k & 1]
        self.rng.shuffle(fits)
        for slot in fits:
            self.nodes += 1
            if self.nodes > budget:
                raise _Restart()
            change = self.place(slot, self.words[length][k])
            if change is None:
                continue
            self.used[length] |= 1 << k
            rest = [other for other in open_slots if other is not slot]
            if all(self.options(other) for other in rest) and self.search(rest, budget, included + 1):
                return True
            self.used[length] &= ~(1 << k)
            self.undo(change)
        return False

    def deduce(self, letters_too):
        """Solve by deduction only: True when every cell is known.

        Each step fills a word that only one dictionary word fits; with
        letters_too, a cell whose letter every fitting word agrees on also
        counts. Mutates the filler.
        """
        open_slots = [slot for slot in self.slots if not all(self.known(i) for i in slot)]
        while open_slots:
            self.tick()
            progressed = False
            for slot in open_slots:
                mask = self.options(slot)
                if mask and mask & (mask - 1) == 0 and self.place(slot, self.words[len(slot)][mask.bit_length() - 1]):
                    progressed = True
            if not progressed and letters_too:
                for slot in open_slots:
                    mask, masks = self.options(slot), self.masks[len(slot)]
                    for pos, i in enumerate(slot):
                        if self.known(i) or not mask:
                            continue
                        agreed = [letter for letter, words in masks[pos].items() if not mask & ~words]
                        if agreed and self.place([i], agreed[0]):
                            progressed = True
                            break
                    if progressed:
                        break
            if not progressed:
                return False
            open_slots = [slot for slot in open_slots if not all(self.known(i) for i in slot)]
        return True

    def unknown_letters(self, answer):
        """Answer letters still unknown, most cells first."""
        counts = {}
        for i, letter in answer.items():
            if not self.known(i):
                counts[letter] = counts.get(letter, 0) + 1
        return sorted(counts, key=lambda letter: (-counts[letter], letter))

    def run(self):
        """(letters by cell, stop reason); letters is None without a fill."""
        initial = (dict(self.letters), dict(self.number_letter), dict(self.letter_number))
        budget = 400
        while True:
            self.letters, self.number_letter, self.letter_number = (dict(part) for part in initial)
            self.used = {length: 0 for length in self.used}
            self.nodes = 0
            try:
                found = self.search(list(self.slots), budget)
            except _Restart:
                self.restarts += 1
                budget *= 2
                continue
            except _Stop as stop:
                return None, str(stop)
            return (dict(self.letters), 'filled') if found else (None, 'search_exhausted')

    def count(self, limit):
        """(answers found, stop reason): every answer up to limit, without restarts."""
        self.found, self.limit = [], limit
        try:
            self.search(list(self.slots), float('inf'))
        except _Enough:
            return self.found, 'limit'
        except _Stop as stop:
            return self.found, str(stop)
        return self.found, 'search_exhausted'


def _numbering(cells, letters, rng):
    """Number per letter: fixed numbers kept, the rest from the smallest free numbers in random order."""
    numbers = {}
    for i, cell in enumerate(cells):
        if not cell.get('black') and cell.get('number'):
            numbers[letters[i]] = cell['number']
    taken = {int(n) for n in numbers.values()}
    remaining = sorted(set(letters.values()) - set(numbers))
    rng.shuffle(remaining)
    free = (n for n in range(1, 100) if n not in taken)
    for letter in remaining:
        numbers[letter] = str(next(free))
    return numbers


def options(raw):
    """Checked generator options: starters, seconds, unique, difficulty, include and an optional seed."""
    if not isinstance(raw, dict):
        raise ValueError('Generator options must be an object.')
    starters, seconds, seed = raw.get('starters', 2), raw.get('seconds', DEFAULT_SECONDS), raw.get('seed')
    unique, difficulty, include = raw.get('unique', True), raw.get('difficulty', 'any'), raw.get('include', [])
    if difficulty not in DIFFICULTIES:
        raise ValueError('Difficulty must be easy, medium or hard.')
    if (not isinstance(include, list) or len(include) > MAX_INCLUDE or
            any(not isinstance(word, str) or len(word) > 40 for word in include)):
        raise ValueError(f'Words to include must be a list of up to {MAX_INCLUDE} words.')
    if type(starters) is not int or not 0 <= starters <= MAX_STARTERS:
        raise ValueError(f'Starter letters must be a whole number from 0 to {MAX_STARTERS}.')
    if type(seconds) not in (int, float) or not 1 <= seconds <= MAX_SECONDS:
        raise ValueError(f'Generating time must be between 1 and {MAX_SECONDS} seconds.')
    if type(unique) is not bool:
        raise ValueError('The single-answer setting must be true or false.')
    if seed is not None and (type(seed) is not int or not 0 <= seed < 1 << 31):
        raise ValueError('The generator seed must be a whole number from 0 to 2147483647.')
    return dict(starters=starters, seconds=seconds, unique=unique, difficulty=difficulty, include=include, seed=seed)


def included_words(puzzle, slots, include):
    """Words to include, normalized and checked against the grid, or ValueError."""
    alphabet = set(ALPHABETS[puzzle['language']])
    words = list(dict.fromkeys(normalize(word) for word in include if word.strip()))
    lengths = {}
    for slot in slots:
        lengths[len(slot)] = lengths.get(len(slot), 0) + 1
    for word in words:
        if not set(word) <= alphabet:
            raise ValueError(f'{word} uses a letter outside the selected language.')
        if len(word) not in lengths:
            sizes = ', '.join(map(str, sorted(lengths)))
            raise ValueError(f'{word} has {len(word)} letters, but the grid has only words of {sizes} letters.')
    for length, count in lengths.items():
        wanted = [word for word in words if len(word) == length]
        if len(wanted) > count:
            raise ValueError(f'{len(wanted)} words to include have {length} letters, but the grid has only {count} such word{"" if count == 1 else "s"}.')
    return words


def prepare(puzzle, raw):
    """Slots, checked options and normalized words to include; ValueError before any search."""
    slots = layout(puzzle)
    checked = options(raw)
    checked['include'] = included_words(puzzle, slots, checked['include'])
    return slots, checked


def _numbered(cells, letters, numbers, given):
    """Cells as the solver sees them: every letter cell numbered, given letters filled in."""
    out = []
    for i, cell in enumerate(cells):
        if cell.get('black'):
            out.append(dict(black=True, number='', letter=''))
            continue
        shown = letters[i] if letters[i] in given else ''
        out.append(dict(black=False, number=numbers[letters[i]], letter=shown, prefilled=bool(shown)))
    return out


def _starters(letters, given, count, difficulty, rng):
    """Starter letters: frequent ones for easy, rare ones for hard, any for the rest."""
    counts = {}
    for letter in letters.values():
        if letter not in given:
            counts[letter] = counts.get(letter, 0) + 1
    chosen = set()
    for _ in range(min(count, len(counts))):
        pool = sorted(set(counts) - chosen)
        weight = {'easy': lambda n: n * n, 'hard': lambda n: 1 / (n * n)}.get(difficulty, lambda n: 1)
        chosen.add(rng.choices(pool, [weight(counts[letter]) for letter in pool])[0])
    return given | chosen


def _grade(cells, slots, words, letters, numbers, given, rng, deadline, cancel, progress):
    """Measured level of the numbered grid with these letters given."""
    for level, letters_too in (('easy', False), ('medium', True)):
        solver = _Filler(dict(cells=_numbered(cells, letters, numbers, given)), slots, words, rng,
                         deadline, cancel, progress, distinct=False, stage='grading')
        if solver.deduce(letters_too):
            return level, solver
    return 'hard', solver


def _reach_level(cells, slots, words, letters, numbers, given, target, rng, deadline, cancel, progress):
    """Give letters until deduction alone reaches target: (given, level, extra letters).

    The letter given is the one filling the most cells still unknown where
    deduction stops, so each step helps as much as possible.
    """
    extra = 0
    while True:
        level, solver = _grade(cells, slots, words, letters, numbers, given, rng, deadline, cancel, progress)
        if LEVELS.index(level) <= LEVELS.index(target):
            return given, level, extra
        if target == 'easy' and level == 'medium':
            # Where word-by-word deduction stops, not where letters would carry on.
            solver = _Filler(dict(cells=_numbered(cells, letters, numbers, given)), slots, words, rng,
                             deadline, cancel, progress, distinct=False, stage='grading')
            solver.deduce(False)
        missing = solver.unknown_letters(letters)
        given = given | {missing[0]}
        extra += 1


def _single_answer(cells, slots, words, letters, numbers, given, rng, deadline, cancel, progress):
    """Give letters until no other answer fits: (given, outcome, extra letters, search nodes).

    outcome is 'unique' only when the search ran out of options with one
    answer left; 'unconfirmed' when it stopped at the time limit.
    """
    extra = nodes = 0
    while True:
        checker = _Filler(dict(cells=_numbered(cells, letters, numbers, given)), slots, words, rng,
                          deadline, cancel, progress, distinct=False, stage='checking')
        found, reason = checker.count(2)
        nodes += checker.nodes
        if reason == 'cancelled':
            raise _Stop('cancelled')
        if reason == 'time_limit':
            return given, 'unconfirmed', extra, nodes
        others = [answer for answer in found if answer != letters]
        if not others:
            return given, 'unique' if reason == 'search_exhausted' else 'unconfirmed', extra, nodes
        # Give one letter whose number takes another letter in the rival answer.
        rival = others[0]
        differing = sorted({letters[i] for i in rival if rival[i] != letters[i]} - given)
        if not differing:
            return given, 'unconfirmed', extra, nodes
        given = given | {rng.choice(differing)}
        extra += 1


def generate(puzzle, words, *, starters=2, seconds=DEFAULT_SECONDS, unique=True, difficulty='any', include=(),
             seed=None, cancel=lambda: False, progress=lambda update: None):
    """Fill, number and choose starter letters for a drawn grid.

    starters is how many letters to give in addition to the letters already
    in the grid. For an easy or medium puzzle, more letters are given until
    deduction alone solves it, which also proves a single answer. Otherwise,
    with unique, more letters are given while another answer fits. The level
    reached is always measured. Filling and checking each get up to seconds.
    Words in include are placed first; ones missing from the dictionary are
    used for this puzzle only. The result holds the numbered cells (only given
    letters filled in) and the full answer; the answer is not shown as letters.
    """
    started = time.monotonic()
    slots, checked = prepare(puzzle, dict(starters=starters, seconds=seconds, unique=unique, difficulty=difficulty,
                                          include=list(include), seed=seed))
    starters, seconds, unique, difficulty, include, seed = checked.values()
    seed = random.SystemRandom().randrange(1 << 31) if seed is None else seed
    rng = random.Random(seed)
    alphabet = set(ALPHABETS[puzzle['language']])
    lengths = {len(slot) for slot in slots}
    usable = {w for w in words if len(w) in lengths and set(w) <= alphabet}
    diagnostics = []
    added = [word for word in include if word not in usable]
    if added:
        diagnostics.append(', '.join(added) + (' is not in the dictionary and counted as a word' if len(added) == 1 else
                                               ' are not in the dictionary and counted as words') + ' for this puzzle only.')
    usable = sorted(usable | set(include))
    stats = dict(seed=seed, dictionaryWords=len(usable), words=len(slots), nodes=0, restarts=0, included=len(include))
    missing = sorted(length for length in lengths if not any(len(w) == length for w in usable))
    if missing:
        diagnostics.append('The dictionary has no words of length ' + ', '.join(map(str, missing)) + '.')
        letters, reason = None, 'search_exhausted'
    else:
        filler = _Filler(puzzle, slots, usable, rng, started + seconds, cancel, progress, include=include)
        letters, reason = filler.run()
        stats.update(nodes=filler.nodes, restarts=filler.restarts)
    stats.update(elapsedSeconds=round(time.monotonic() - started, 3), stopReason=reason,
                 exhaustive=reason == 'search_exhausted')
    if letters is None:
        status = 'cancelled' if reason == 'cancelled' else 'no_fill'
        return dict(status=status, stats=stats, diagnostics=diagnostics)
    cells = puzzle['cells']
    numbers = _numbering(cells, letters, rng)
    fixed = {cell['letter'] for cell in cells if not cell.get('black') and cell.get('letter')}
    given = _starters(letters, fixed, starters, difficulty, rng)
    uniqueness, grade, extra = 'unchecked', None, 0
    checked_at = time.monotonic()
    deadline = checked_at + seconds
    try:
        # A medium or hard request can come out easier; other starter letters
        # often change that, so a few sets are tried and the closest is kept.
        for attempt in range(STARTER_ATTEMPTS if difficulty in ('medium', 'hard') else 1):
            tried = given if attempt == 0 else _starters(letters, fixed, starters, difficulty, rng)
            if difficulty in ('easy', 'medium'):
                # Solving by deduction alone also proves that only one answer fits.
                tried, level, added = _reach_level(cells, slots, usable, letters, numbers, tried, difficulty, rng,
                                                   deadline, cancel, progress)
                single = 'unique'
            else:
                single, added = 'unchecked', 0
                if unique:
                    tried, single, added, check_nodes = _single_answer(cells, slots, usable, letters, numbers, tried,
                                                                      rng, deadline, cancel, progress)
                    stats['checkNodes'] = stats.get('checkNodes', 0) + check_nodes
                level = _grade(cells, slots, usable, letters, numbers, tried, rng, deadline, cancel, progress)[0]
            target = LEVELS.index(difficulty) if difficulty != 'any' else None
            if grade is None or (target is not None and abs(LEVELS.index(level) - target) < abs(LEVELS.index(grade) - target)):
                given, grade, extra, uniqueness = tried, level, added, single
            if target is None or LEVELS.index(grade) == target:
                break
    except _Stop as stop:
        if str(stop) == 'cancelled':
            stats.update(elapsedSeconds=round(time.monotonic() - started, 3), stopReason='cancelled', exhaustive=False)
            return dict(status='cancelled', stats=stats, diagnostics=diagnostics)
        if uniqueness == 'unchecked' and (unique or difficulty in ('easy', 'medium')):
            uniqueness = 'unconfirmed'
        diagnostics.append('Checking stopped at its time limit, so ' +
                           ('the difficulty was not reached.' if difficulty in ('easy', 'medium') else 'the difficulty was not measured.'))
    stats.update(checkSeconds=round(time.monotonic() - checked_at, 3))
    if uniqueness == 'unconfirmed' and difficulty not in ('easy', 'medium'):
        diagnostics.append('The check for other answers stopped at its time limit, so a single answer is not confirmed.')
    out = _numbered(cells, letters, numbers, given)
    answer = ['' if cell.get('black') else letters[i] for i, cell in enumerate(cells)]
    stats.update(distinctLetters=len(numbers), extraGivens=extra, elapsedSeconds=round(time.monotonic() - started, 3))
    return dict(status='generated', cells=out, answer=answer, givens=sorted(given), uniqueness=uniqueness,
                difficulty=difficulty, grade=grade, stats=stats, diagnostics=diagnostics)
