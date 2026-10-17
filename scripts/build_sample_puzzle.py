"""Build an original codeword grid for the showcase sample.

Usage: python3 scripts/build_sample_puzzle.py WORDS.txt [--check-words BIG.txt] [--seed N] [--size 13]

WORDS.txt is any one-word-per-line list; it is read only while building and
is not stored. Each fill is numbered and solved with the app's strict
dictionary search; a grid is kept only if exactly one fill fits and the
search was exhaustive. Check against a broad list (--check-words, defaults to
WORDS.txt): a grid unique among common words can still have other fills
among all English words, which a solver may then prefer. The grid follows the usual codeword layout: words run along
even rows and even columns, (odd, odd) cells are black, and extra black
cells split long runs. The fill is a backtracking search, so the result is a
new arrangement of common words. Prints the grid rows (# is black) and the
letter count; copy the rows into static/samples.js.
"""
import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import solver  # noqa: E402
from app.dictionaries import clean_words  # noqa: E402


def pattern(size, rng, shortest=3, longest=8):
    """Black cells, symmetric under 180° rotation, with runs of 3–8 letters."""
    black = {(r, c) for r in range(size) for c in range(size) if r % 2 and c % 2}
    def runs(line):
        out, start = [], None
        for k, cell in enumerate(line + [None]):
            if cell is not None and cell not in black:
                if start is None: start = k
            elif start is not None:
                out.append((start, k)); start = None
        return out
    for _ in range(400):
        lines = [[(r, c) for c in range(size)] for r in range(0, size, 2)]
        lines += [[(r, c) for r in range(size)] for c in range(0, size, 2)]
        long = [(line, a, b) for line in lines for a, b in runs(line) if b - a > longest]
        if not long: break
        line, a, b = rng.choice(long)
        # Split on an even index so the black cell sits where words cross.
        options = [k for k in range(a + shortest, b - shortest) if k % 2 == 0]
        if not options: continue
        r, c = line[rng.choice(options)]
        black |= {(r, c), (size - 1 - r, size - 1 - c)}
    lines = [[(r, c) for c in range(size)] for r in range(size)] + [[(r, c) for r in range(size)] for c in range(size)]
    slots = [line[a:b] for line in lines for a, b in runs(line) if b - a >= 2]
    # A white cell left in no word would be an unclued letter: make it black.
    black |= {(r, c) for r in range(size) for c in range(size)} - black - {cell for s in slots for cell in s}
    if any(len(s) < shortest or len(s) > longest for s in slots): return None
    return black, slots


def fill(slots, words, rng, seconds):
    by_length = {}
    for w in words: by_length.setdefault(len(w), []).append(w)
    for group in by_length.values(): rng.shuffle(group)
    letters, used = {}, set()
    deadline = time.monotonic() + seconds
    def options(slot):
        known = [(k, letters.get(cell)) for k, cell in enumerate(slot)]
        return [w for w in by_length.get(len(slot), ()) if w not in used
                and all(l is None or w[k] == l for k, l in known)]
    def solve(open_slots):
        if time.monotonic() > deadline: raise TimeoutError
        if not open_slots: return True
        best = min(open_slots, key=lambda s: len(options(s)))
        for word in options(best)[:40]:
            placed = [cell for cell in best if cell not in letters]
            for k, cell in enumerate(best): letters[cell] = word[k]
            used.add(word)
            rest = [s for s in open_slots if s is not best and not all(cell in letters for cell in s)]
            done = [s for s in open_slots if s is not best and all(cell in letters for cell in s)]
            if all(''.join(letters[c] for c in s) in by_set and ''.join(letters[c] for c in s) not in used
                   for s in done) and all(options(s) for s in rest):
                for s in done: used.add(''.join(letters[c] for c in s))
                if solve(rest): return True
                for s in done: used.discard(''.join(letters[c] for c in s))
            used.discard(word)
            for cell in placed: del letters[cell]
        return False
    by_set = set(words)
    try:
        return letters if solve(list(slots)) else None
    except TimeoutError:
        return None


def read_words(path, longest=None):
    words = {line.strip().upper() for line in open(path, encoding='utf-8')
             if line.strip().isalpha() and line.strip().isascii() and len(line.strip()) >= 3}
    return sorted(w for w in words if longest is None or len(w) <= longest)


def solution_count(rows, words):
    """Fills of the numbered grid within words, and whether the search was exhaustive."""
    text = ''.join(rows)
    key = {letter: str(k + 1) for k, letter in enumerate(sorted(set(text) - {'#'}))}
    cells = [dict(black=ch == '#', number='' if ch == '#' else key[ch], letter='') for ch in text]
    puzzle = dict(rows=len(rows), cols=len(rows[0]), language='en', rules=solver.default_rules('en'), cells=cells,
                  useDictionary=True, allowUnknownWords=False, searchMode='extended')
    limit = solver.MAX_CANDIDATES
    solver.MAX_CANDIDATES = 10 ** 6  # every candidate, so an exhausted search proves uniqueness
    try:
        result = solver.solve(puzzle, clean_words('en', words))
    finally:
        solver.MAX_CANDIDATES = limit
    return len(result['solutions']), result['stats']['exhaustive']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('words')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--size', type=int, default=13)
    parser.add_argument('--attempts', type=int, default=200)
    parser.add_argument('--check-words', help='broad list for the uniqueness check (default: WORDS)')
    args = parser.parse_args()
    words = read_words(args.words, longest=8)
    check = read_words(args.check_words) if args.check_words else words
    rng = random.Random(args.seed)
    for attempt in range(args.attempts):
        built = pattern(args.size, rng)
        if not built: continue
        black, slots = built
        letters = fill(slots, words, rng, 10)
        if not letters: continue
        rows = [''.join('#' if (r, c) in black else letters[(r, c)] for c in range(args.size)) for r in range(args.size)]
        count, exhaustive = solution_count(rows, check)
        if count != 1 or not exhaustive:
            print(f'attempt {attempt}: rejected, {count} fills{"" if exhaustive else " (search not exhaustive)"}', file=sys.stderr)
            continue
        distinct = len(set(''.join(rows)) - {'#'})
        print(f'attempt {attempt}: {len(slots)} words, {distinct} distinct letters, unique', file=sys.stderr)
        for row in rows: print(row)
        return
    sys.exit('No unique fill found; try another seed or more attempts.')


if __name__ == '__main__':
    main()
