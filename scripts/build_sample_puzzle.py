"""Build an original codeword grid for the showcase sample.

Usage: python3 scripts/build_sample_puzzle.py WORDS.txt [--seed N] [--size 13]

WORDS.txt is any one-word-per-line list; it is read only while building and
is not stored. The grid follows the usual codeword layout: words run along
even rows and even columns, (odd, odd) cells are black, and extra black
cells split long runs. The fill is a backtracking search, so the result is a
new arrangement of common words. Prints the grid rows (# is black) and the
letter count; copy the rows into static/samples.js.
"""
import argparse
import random
import sys
import time


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('words')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--size', type=int, default=13)
    parser.add_argument('--attempts', type=int, default=200)
    args = parser.parse_args()
    words = sorted({line.strip().upper() for line in open(args.words, encoding='utf-8')
                    if line.strip().isalpha() and line.strip().isascii() and 3 <= len(line.strip()) <= 8})
    rng = random.Random(args.seed)
    for attempt in range(args.attempts):
        built = pattern(args.size, rng)
        if not built: continue
        black, slots = built
        letters = fill(slots, words, rng, 10)
        if not letters: continue
        rows = [''.join('#' if (r, c) in black else letters[(r, c)] for c in range(args.size)) for r in range(args.size)]
        distinct = len(set(''.join(rows)) - {'#'})
        print(f'attempt {attempt}: {len(slots)} words, {distinct} distinct letters', file=sys.stderr)
        for row in rows: print(row)
        return
    sys.exit('No fill found; try another seed or a larger word list.')


if __name__ == '__main__':
    main()
