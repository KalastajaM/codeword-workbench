"""Build bundled character n-gram models from local, redistributable word lists.

English: Webster's Second International (/usr/share/dict/web2, public domain).
Finnish: Kotus Nykysuomen sanalista 2024 (CC BY 4.0), plus a small set of
rule-generated case endings so the model sees inflected word endings.
Dutch:   OpenTaal word list (BSD/CC BY 3.0), when a local copy is supplied.
Swedish: SALDO full-form lexicon (CC BY 4.0), extracted with
         scripts/extract_saldo_forms.py.

Only n-gram counts are stored, pruned and rounded. Usage:
  python3 scripts/build_language_models.py --en /usr/share/dict/web2 \
      --fi path/to/nykysuomensanalista2024.txt [--nl path/to/wordlist.txt] \
      [--sv path/to/saldo-forms.txt]
"""
import argparse
import json
import random
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.dictionaries import ALPHABETS, normalize  # noqa: E402
from app import language_model as lm  # noqa: E402

SOURCES = {
    'en': "Webster's Second International word list (public domain)",
    'fi': 'Kotus Nykysuomen sanalista 2024 (CC BY 4.0) with rule-generated case endings',
    'nl': 'OpenTaal word list (BSD / CC BY 3.0)',
    'sv': 'SALDO full-form lexicon, Språkbanken Text (CC BY 4.0)',
}
MIN_COUNT = 2


def clean(language, words):
    alphabet = set(ALPHABETS[language])
    return sorted({w for w in (normalize(x) for x in words) if 2 <= len(w) <= 40 and set(w) <= alphabet})


def finnish_words(path):
    """Headwords plus regular endings on vowel-final nominals and type-1 verbs.

    This is deliberately crude: it adds plausible ending statistics, not a
    morphology. Consonant-stem and gradation forms are not generated.
    """
    lines = Path(path).read_text(encoding='utf-8').splitlines()[1:]
    words = []
    vowels = set('AEIOUYÄÖ')
    for line in lines:
        parts = line.split('\t')
        word = normalize(parts[0])
        kind = parts[2] if len(parts) > 2 else ''
        if not word or not set(word) <= set(ALPHABETS['fi']):
            continue
        words.append(word)
        front = not set(word) & set('AOU')
        a = 'Ä' if front else 'A'
        o = 'Ö' if front else 'O'
        u = 'Y' if front else 'U'
        if kind in ('substantiivi', 'adjektiivi') and word[-1] in vowels and word[-1] != 'E':
            # Singular cases, partitive (+A), illative (lengthened vowel + N).
            for ending in ('N', 'SS' + a, 'ST' + a, 'LL' + a, 'LT' + a, 'LLE', 'KSI', 'N' + a, a, 'T', word[-1] + 'N'):
                words.append(word + ending)
            if word[-1] in 'OUYÖ':
                # Plural stems keep the vowel and add I/J.
                for ending in ('J' + a, 'JEN', 'ISS' + a, 'IST' + a, 'ILL' + a, 'ILLE', 'IKSI', 'IN', 'IHIN', 'IN' + a):
                    words.append(word + ending)
        elif kind == 'verbi' and len(word) > 3 and word[-1] == a and word[-2] in vowels and word[-2] not in 'AÄ' + 'E':
            stem = word[:-1]
            for ending in ('N', 'T', 'MME', 'TTE', 'V' + a + 'T', 'I', 'IN', 'IT', 'IMME', 'TTIIN', 'MINEN', 'V' + a, 'NUT', 'NEET', 'TT' + a + 'V' + a):
                words.append(stem + ending)
            words.append(stem + stem[-1])
    return clean('fi', words)


def dutch_words(path):
    """OpenTaal entries; diacritics dropped for training only (IDEEËN -> IDEEEN).

    Puzzles write Dutch in A-Z, with IJ in two cells. Dictionary imports still
    keep spellings unchanged; this affects letter statistics alone.
    """
    words = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        decomposed = unicodedata.normalize('NFD', line)
        words.append(''.join(c for c in decomposed if not unicodedata.combining(c)))
    return clean('nl', words)


def build(language, words):
    counts = lm.count_ngrams(words)
    pruned = {g: c for g, c in counts.items() if len(g) < 3 or c >= MIN_COUNT}
    return dict(language=language, order=lm.ORDER, source=SOURCES[language],
                trainingWords=len(words), counts=pruned)


def calibrate(language, train, held_out):
    """Per-length label thresholds from held-out words and shuffled fakes.

    Implausible: below the 5th percentile of real words of that length.
    Typical: at or above both the 90th percentile of letter-shuffled words
    and the 10th percentile of real words. Short words overlap a lot, so
    their bands are wider; that is a property of short words, not a bug.
    """
    model = lm.CharModel(language, build(language, train)['counts'], 'calibration')
    rng = random.Random(1)
    def per_symbol(w):
        return (model.score(w) - sum(p for p, _ in lm.rule_findings(w, language))) / (len(w) + 1)
    q = lambda xs, f: round(xs[int(f * (len(xs) - 1))], 2)
    thresholds = []
    report = {}
    lower = 0
    for upper in lm.LENGTH_BANDS:
        band = [w for w in held_out if lower < len(w) <= upper]
        lower = upper
        if len(band) < 30:
            thresholds.append([upper, lm.UNUSUAL_BITS, lm.TYPICAL_BITS])
            continue
        real = sorted(per_symbol(w) for w in band)
        shuffled = sorted(per_symbol(''.join(rng.sample(w, len(w)))) for w in band)
        implausible_below = q(real, .05)
        typical_from = max(q(shuffled, .9), q(real, .1), implausible_below)
        thresholds.append([upper, implausible_below, typical_from])
        report[upper] = dict(words=len(band), real_p5=implausible_below, real_p50=q(real, .5),
                             shuffled_p90=q(shuffled, .9), typical_from=typical_from,
                             shuffled_typical=round(sum(x >= typical_from for x in shuffled) / len(shuffled), 2),
                             real_typical=round(sum(x >= typical_from for x in real) / len(real), 2))
    return thresholds, report


def held_out_sample(words):
    """Hold out up to 10% of each length band (at most 3000) for calibration."""
    rng = random.Random(0)
    held = set()
    lower = 0
    for upper in lm.LENGTH_BANDS:
        band = [w for w in words if lower < len(w) <= upper]
        lower = upper
        held.update(rng.sample(band, min(3000, len(band) // 10)))
    return held


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--en'); parser.add_argument('--fi'); parser.add_argument('--nl'); parser.add_argument('--sv')
    parser.add_argument('--out', default=str(lm.MODEL_DIR))
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    for language in ('en', 'fi', 'nl', 'sv'):
        path = getattr(args, language)
        if not path:
            continue
        if language == 'fi':
            words = finnish_words(path)
        elif language == 'nl':
            words = dutch_words(path)
        else:
            words = clean(language, Path(path).read_text(encoding='utf-8').splitlines())
        held = held_out_sample(words)
        train = [w for w in words if w not in held]
        thresholds, report = calibrate(language, train, sorted(held))
        print(language, len(words), 'words', json.dumps(report))
        data = build(language, words)
        data['thresholds'] = thresholds
        (out / f'{language}.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'), sort_keys=True), encoding='utf-8')
        print(language, len(data['counts']), 'n-grams', (out / f'{language}.json').stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
