"""Benchmark full-grid solving on the bundled original puzzles.

Usage:
  python3 scripts/benchmark_solver.py [--modes quick,deep] [--words LIST.txt] [--keys 3]

Each puzzle in scripts/benchmark_puzzles.json is numbered with several
random number keys (no letters given) and solved without a dictionary in
each search mode. With --words, the same puzzles are also solved with that
word list as the dictionary (strict search, then missing-word fallback).
The word list is read for this run only and is not stored.

Reported per mode: cells right in the top alternative (median and worst
over all runs), grids solved completely, median seconds until the search
stopped, median seconds until the grid preview first showed the final top
answer (dictionary-free only), and how many wrong cells the close-rival
marking flagged. Times depend on the machine; run nothing else meanwhile.
"""
import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.solver import solve, default_rules  # noqa: E402
from app.dictionaries import clean_words  # noqa: E402


def numbered(rows, seed, language):
    text = ''.join(rows)
    letters = sorted(set(text) - {'#'})
    numbers = list(range(1, len(letters) + 1))
    random.Random(seed).shuffle(numbers)
    key = dict(zip(letters, numbers))
    cells = [dict(black=True, number='', letter='') if ch == '#' else dict(black=False, number=str(key[ch]), letter='')
             for ch in text]
    return dict(rows=len(rows), cols=len(rows[0]), language=language, rules=default_rules(language), cells=cells), text


def run(puzzle, answer, mode, words):
    p = dict(puzzle, searchMode=mode, useDictionary=words is not None, allowUnknownWords=True)
    seen = []
    started = time.monotonic()
    def progress(event):
        if event.get('preview'): seen.append((time.monotonic() - started, event['preview']))
    result = solve(p, words or [], progress=progress)
    elapsed = time.monotonic() - started
    open_cells = [i for i, ch in enumerate(answer) if ch != '#']
    top = result['solutions'][0]['letters'] if result['solutions'] else [''] * len(answer)
    wrong = [i for i in open_cells if top[i] != answer[i]]
    settled = next((t for t, preview in seen if preview == top), None) if seen else None
    weak = (result['solutions'][0].get('weakNumbers') or {}) if result['solutions'] else {}
    flagged = sum(1 for i in wrong if puzzle['cells'][i]['number'] in weak)
    return dict(right=1 - len(wrong) / len(open_cells), wrong=len(wrong), seconds=elapsed, settled=settled,
                flagged=flagged, weak=len(weak))


def summary(label, runs):
    rights = [r['right'] for r in runs]
    settled = [r['settled'] for r in runs if r['settled'] is not None]
    wrong = sum(r['wrong'] for r in runs)
    print(f"{label:<22} median {statistics.median(rights):6.1%}  worst {min(rights):6.1%}  "
          f"solved {sum(r['wrong'] == 0 for r in runs)}/{len(runs)}  "
          f"stop {statistics.median(r['seconds'] for r in runs):5.1f}s  "
          + (f"settled {statistics.median(settled):5.1f}s  " if settled else '')
          + (f"wrong cells flagged {sum(r['flagged'] for r in runs)}/{wrong}" if wrong else 'no wrong cells'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--modes', default='quick,deep')
    parser.add_argument('--keys', type=int, default=3, help='number keys per puzzle')
    parser.add_argument('--words', help='optional word list for dictionary runs')
    args = parser.parse_args()
    data = json.loads((ROOT / 'scripts' / 'benchmark_puzzles.json').read_text(encoding='utf-8'))
    words = None
    if args.words:
        lines = Path(args.words).read_text(encoding='utf-8').splitlines()
        words = clean_words('en', [w.strip() for w in lines if w.strip().isascii() and w.strip().isalpha()])
    configs = [(mode, None) for mode in args.modes.split(',')]
    if words is not None: configs += [(mode, words) for mode in args.modes.split(',')]
    for mode, dictionary in configs:
        runs = []
        for puzzle in data['puzzles']:
            for seed in range(args.keys):
                p, answer = numbered(puzzle['rows'], seed, puzzle['language'])
                result = run(p, answer, mode, dictionary)
                runs.append(result)
                print(f"  {mode:<6} {'dictionary' if dictionary else 'no dictionary':<13} {puzzle['name']:<9} key {seed}: "
                      f"{result['right']:6.1%} right, {result['seconds']:5.1f}s", file=sys.stderr, flush=True)
        summary(f"{mode} {'dictionary' if dictionary else 'no dictionary'}", runs)


if __name__ == '__main__':
    main()
