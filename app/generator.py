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
"""
import random
import time

from .dictionaries import ALPHABETS

DEFAULT_SECONDS = 20
MAX_SECONDS = 120
MAX_STARTERS = 10
MAX_SLOTS = 800


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

    def __init__(self, puzzle, slots, words, rng, deadline, cancel, progress, distinct=True, stage='filling'):
        self.cells, self.slots, self.rng = puzzle['cells'], slots, rng
        self.deadline, self.cancel, self.progress = deadline, cancel, progress
        self.distinct, self.stage, self.found = distinct, stage, None
        lengths = {len(slot) for slot in slots}
        self.words, self.masks, self.full = {}, {}, {}
        for length in lengths:
            group = [w for w in words if len(w) == length]
            rng.shuffle(group)
            self.words[length] = group
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

    def search(self, open_slots, budget):
        self.tick()
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
            if self.search(rest, budget):
                return True
            if self.distinct:
                self.used[length] &= ~(1 << k)
            self.undo(change)
        return False

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
    """Checked generator options: starters, seconds, unique and an optional seed."""
    if not isinstance(raw, dict):
        raise ValueError('Generator options must be an object.')
    starters, seconds, seed = raw.get('starters', 2), raw.get('seconds', DEFAULT_SECONDS), raw.get('seed')
    unique = raw.get('unique', True)
    if type(starters) is not int or not 0 <= starters <= MAX_STARTERS:
        raise ValueError(f'Starter letters must be a whole number from 0 to {MAX_STARTERS}.')
    if type(seconds) not in (int, float) or not 1 <= seconds <= MAX_SECONDS:
        raise ValueError(f'Generating time must be between 1 and {MAX_SECONDS} seconds.')
    if type(unique) is not bool:
        raise ValueError('The single-answer setting must be true or false.')
    if seed is not None and (type(seed) is not int or not 0 <= seed < 1 << 31):
        raise ValueError('The generator seed must be a whole number from 0 to 2147483647.')
    return dict(starters=starters, seconds=seconds, unique=unique, seed=seed)


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


def generate(puzzle, words, *, starters=2, seconds=DEFAULT_SECONDS, unique=True, seed=None,
             cancel=lambda: False, progress=lambda update: None):
    """Fill, number and choose starter letters for a drawn grid.

    starters is how many letters to give in addition to the letters already
    in the grid. With unique, more letters are given while another answer
    fits. Filling and checking each get up to seconds. The result holds the
    numbered cells (only given letters filled in) and the full answer; the
    answer is not shown as letters.
    """
    started = time.monotonic()
    slots = layout(puzzle)
    starters, seconds, unique, seed = options(dict(starters=starters, seconds=seconds, unique=unique, seed=seed)).values()
    seed = random.SystemRandom().randrange(1 << 31) if seed is None else seed
    rng = random.Random(seed)
    alphabet = set(ALPHABETS[puzzle['language']])
    lengths = {len(slot) for slot in slots}
    usable = sorted({w for w in words if len(w) in lengths and set(w) <= alphabet})
    stats = dict(seed=seed, dictionaryWords=len(usable), words=len(slots), nodes=0, restarts=0)
    missing = sorted(length for length in lengths if not any(len(w) == length for w in usable))
    diagnostics = []
    if missing:
        diagnostics.append('The dictionary has no words of length ' + ', '.join(map(str, missing)) + '.')
        letters, reason = None, 'search_exhausted'
    else:
        filler = _Filler(puzzle, slots, usable, rng, started + seconds, cancel, progress)
        letters, reason = filler.run()
        stats.update(nodes=filler.nodes, restarts=filler.restarts)
    stats.update(elapsedSeconds=round(time.monotonic() - started, 3), stopReason=reason,
                 exhaustive=reason == 'search_exhausted')
    if letters is None:
        status = 'cancelled' if reason == 'cancelled' else 'no_fill'
        return dict(status=status, stats=stats, diagnostics=diagnostics)
    cells = puzzle['cells']
    numbers = _numbering(cells, letters, rng)
    given = {cell['letter'] for cell in cells if not cell.get('black') and cell.get('letter')}
    choices = sorted(set(letters.values()) - given)
    given |= set(rng.sample(choices, min(starters, len(choices))))
    uniqueness, extra = 'unchecked', 0
    if unique:
        checked = time.monotonic()
        try:
            given, uniqueness, extra, check_nodes = _single_answer(cells, slots, usable, letters, numbers, given, rng,
                                                                  checked + seconds, cancel, progress)
        except _Stop:
            stats.update(elapsedSeconds=round(time.monotonic() - started, 3), stopReason='cancelled', exhaustive=False)
            return dict(status='cancelled', stats=stats, diagnostics=diagnostics)
        stats.update(checkNodes=check_nodes, checkSeconds=round(time.monotonic() - checked, 3))
        if uniqueness == 'unconfirmed':
            diagnostics.append('The check for other answers stopped at its time limit, so a single answer is not confirmed.')
    out = _numbered(cells, letters, numbers, given)
    answer = ['' if cell.get('black') else letters[i] for i, cell in enumerate(cells)]
    stats.update(distinctLetters=len(numbers), extraGivens=extra, elapsedSeconds=round(time.monotonic() - started, 3))
    return dict(status='generated', cells=out, answer=answer, givens=sorted(given), uniqueness=uniqueness,
                stats=stats, diagnostics=diagnostics)
