"""Place black cells so a grid has a target number of words.

The user's black cells stay, and cells with a number or letter never become
black. Every letter cell must be part of a word, every word must be within
the length limits, and the letter cells must form one connected piece. With
mirror, black cells are placed in pairs symmetric under 180° rotation. The
search is simulated annealing over black cells with restarts until its time
limit; it returns the best layout it found, which may miss the word count
when the grid and limits cannot reach it exactly. Among layouts that meet
the target it prefers fewer black cells and no 2 × 2 black squares, as in
printed codewords.
"""
import math
import time

MAX_SECONDS = 1.5
# Penalties: any broken rule outweighs a word of count, which outweighs the
# look of the grid (black cells, 2 × 2 black squares).
RULE = 100
WORD = 10
BLACK = 0.2
SQUARE = 1.0


def check_target(target, rows, cols):
    """Checked target: words, shortest, longest and mirror, or ValueError."""
    if not isinstance(target, dict):
        raise ValueError('The word layout must be an object.')
    words, shortest, longest = target.get('words'), target.get('shortest', 3), target.get('longest')
    mirror = target.get('mirror', True)
    longest = max(rows, cols) if longest is None else longest
    if type(words) is not int or not 1 <= words <= rows * cols:
        raise ValueError('The number of words must be a whole number of at least 1.')
    if type(shortest) is not int or type(longest) is not int or not 2 <= shortest <= longest:
        raise ValueError('Word lengths must be whole numbers, at least 2, with the shortest no longer than the longest.')
    if shortest > max(rows, cols):
        raise ValueError(f'A {rows} × {cols} grid has no room for words of {shortest} letters.')
    if type(mirror) is not bool:
        raise ValueError('Mirror black cells must be true or false.')
    return dict(words=words, shortest=shortest, longest=min(longest, max(rows, cols)), mirror=mirror)


def runs(rows, cols, black):
    """Across and down runs of letter cells, including single cells."""
    out = []
    for across in (True, False):
        for line in range(rows if across else cols):
            run = []
            size = cols if across else rows
            for offset in range(size + 1):
                i = line * cols + offset if across else offset * cols + line
                if offset < size and i not in black:
                    run.append(i)
                    continue
                if run:
                    out.append(run)
                run = []
    return out


def measure(rows, cols, black, shortest, longest, need=None):
    """(rule breaks, words, lengths) for a layout.

    Rule breaks count letter cells outside any word, letters by which words
    miss the length limits, extra pieces of the grid, and missing words of a
    length in need (length: count).
    """
    words = [run for run in runs(rows, cols, black) if len(run) >= 2]
    covered = {i for run in words for i in run}
    white = [i for i in range(rows * cols) if i not in black]
    breaks = sum(1 for i in white if i not in covered)
    breaks += sum(max(0, shortest - len(run), len(run) - longest) for run in words)
    if white:
        # Pieces of the grid that are not connected to the first letter cell.
        seen, stack = {white[0]}, [white[0]]
        while stack:
            i = stack.pop()
            r, c = divmod(i, cols)
            for j, ok in ((i - cols, r > 0), (i + cols, r < rows - 1), (i - 1, c > 0), (i + 1, c < cols - 1)):
                if ok and j not in black and j not in seen:
                    seen.add(j)
                    stack.append(j)
        if len(seen) < len(white):
            pieces, left = 1, set(white) - seen
            while left:
                start = left.pop()
                pieces += 1
                stack = [start]
                while stack:
                    i = stack.pop()
                    r, c = divmod(i, cols)
                    for j, ok in ((i - cols, r > 0), (i + cols, r < rows - 1), (i - 1, c > 0), (i + 1, c < cols - 1)):
                        if ok and j in left:
                            left.discard(j)
                            stack.append(j)
            breaks += pieces - 1
    else:
        breaks += 1
    lengths = sorted(len(run) for run in words)
    for length, count in (need or {}).items():
        breaks += max(0, count - lengths.count(length))
    return breaks, len(words), lengths


def plan(puzzle, target, rng, seconds=MAX_SECONDS, need=None, cancel=lambda: False):
    """Best black cells found for the target: (black set, rule breaks, words, lengths)."""
    rows, cols, cells = puzzle['rows'], puzzle['cols'], puzzle['cells']
    n = rows * cols
    fixed = {i for i, cell in enumerate(cells) if cell.get('black')}
    locked = {i for i, cell in enumerate(cells) if not cell.get('black') and (cell.get('number') or cell.get('letter'))}
    units, seen = [], set()
    for i in range(n):
        if i in fixed or i in locked or i in seen:
            continue
        unit = {i}
        mirror = n - 1 - i
        if target['mirror'] and mirror != i:
            if mirror in locked:
                continue  # Its partner can never be black, so neither can it.
            if mirror not in fixed:
                unit.add(mirror)
        seen |= unit
        units.append(tuple(unit))
    shortest, longest, goal = target['shortest'], target['longest'], target['words']

    def cost(black):
        breaks, words, lengths = measure(rows, cols, black, shortest, longest, need)
        squares = sum(1 for i in black if i % cols < cols - 1 and i // cols < rows - 1
                      and i + 1 in black and i + cols in black and i + cols + 1 in black)
        look = BLACK * (len(black) - len(fixed)) + SQUARE * squares
        return RULE * breaks + WORD * abs(words - goal) + look, breaks, words, lengths

    best = (math.inf, None, None, None, None)
    deadline = time.monotonic() + seconds
    start = 0
    while time.monotonic() < deadline and not cancel():
        black = set(fixed)
        if units and start % 2:
            # Every other restart begins from the usual codeword lattice.
            for unit in units:
                if all((i // cols) % 2 and (i % cols) % 2 for i in unit):
                    black.update(unit)
        start += 1
        current = cost(black)
        if current[0] < best[0]:
            best = current + (set(black),)
        temperature = 3.0 * WORD
        for step in range(400 * max(1, len(units))):
            if not units or time.monotonic() > deadline:
                break
            unit = rng.choice(units)
            if unit[0] in black:
                black.difference_update(unit)
            else:
                black.update(unit)
            trial = cost(black)
            if trial[0] <= current[0] or rng.random() < math.exp((current[0] - trial[0]) / temperature):
                current = trial
                if current[0] < best[0]:
                    best = current + (set(black),)
            else:
                if unit[0] in black:
                    black.difference_update(unit)
                else:
                    black.update(unit)
            temperature = max(0.05, temperature * 0.997)
        if not units:
            break
    return best[4], best[1], best[2], best[3]
