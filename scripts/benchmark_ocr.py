#!/usr/bin/env python3
"""Compare fresh number recognition with saved, user-reviewed puzzles.

Usage: python3 scripts/benchmark_ocr.py [--auto] [puzzle.json or directory ...]

Defaults to data/puzzles. Every saved puzzle with an image is recognized again
and its numbers are compared with the saved cells, which count as ground truth
only as far as the user reviewed them. Saved data stays local; this script
never writes. A mismatch can be an error in the saved puzzle, so inspect the
image before changing the recognizer.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import ocr  # noqa: E402


def puzzles(paths):
    for path in paths:
        yield from sorted(path.glob('*.json')) if path.is_dir() else [path]


def main(argv):
    auto = '--auto' in argv
    paths = [Path(arg) for arg in argv if arg != '--auto'] or [ROOT/'data'/'puzzles']
    seen, correct, total = set(), 0, 0
    for path in puzzles(paths):
        saved = json.loads(path.read_text())
        if not saved.get('image'):
            continue
        # Several saved puzzles can share one source image.
        key = hashlib.sha1(saved['image'].encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        started = time.monotonic()
        payload = {'image': saved['image'], 'autoDetect': True} if auto else {
            'image': saved['image'], 'rows': saved['rows'], 'cols': saved['cols'], 'bounds': saved.get('imageBounds')}
        result = ocr.recognize(payload)
        elapsed = time.monotonic()-started
        if (result['rows'], result['cols']) != (saved['rows'], saved['cols']):
            print(f"{saved['name']}: detected {result['rows']}x{result['cols']}, saved {saved['rows']}x{saved['cols']}")
            continue
        errors = []
        for index, (expected, found) in enumerate(zip(saved['cells'], result['cells'])):
            if expected.get('black') or not (expected.get('number') or found['number']):
                continue
            total += 1
            if (expected.get('number') or '') == found['number']:
                correct += 1
            else:
                errors.append((*divmod(index, saved['cols']), expected.get('number') or '', found['number']))
        print(f"{saved['name']} ({path.name}): {len(errors)} number differences, {elapsed:.1f}s")
        for row, col, expected, found in errors[:20]:
            print(f'  row {row+1} col {col+1}: saved {expected!r}, recognized {found!r}')
    print(f'Matched {correct} of {total} numbered cells.')


if __name__ == '__main__':
    main(sys.argv[1:])
