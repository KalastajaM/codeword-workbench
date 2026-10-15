"""Character n-gram language models and soft spelling rules per language.

A model estimates how much a letter sequence resembles the words it was
trained on, including how words typically start and end. It never verifies
that a sequence is a real word: names, loanwords and compounds can look
unusual, and invented strings can look typical.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import math
from pathlib import Path

from .dictionaries import ALPHABETS, normalize

ORDER = 4
DISCOUNT = 0.75
START = '^'
END = '$'
MODEL_DIR = Path(__file__).resolve().parent / 'models'
ADAPT_MIN_WORDS = 500
ADAPT_SAMPLE = 25000
# Average score per symbol, in bits relative to a uniform guess. Calibrated by
# scripts/build_language_models.py on held-out words and random strings.
# Fallback thresholds; bundled models carry per-length ones.
TYPICAL_BITS = 1.0
UNUSUAL_BITS = 0.0
# Upper word lengths of the calibration bands.
LENGTH_BANDS = (3, 4, 5, 7, 100)

VOWELS = {'en': set('AEIOUY'), 'fi': set('AEIOUYÄÖ'), 'nl': set('AEIOUY'), 'sv': set('AEIOUYÅÄÖ')}
_active = ContextVar('language_models', default=None)
_bundled = {}
_adapted = {}


def count_ngrams(words, counts=None, weight=1):
    """Add weighted n-gram counts for padded words, orders 1..ORDER."""
    counts = {} if counts is None else counts
    for word in words:
        padded = START * (ORDER - 1) + word + END
        for end in range(ORDER - 1, len(padded)):
            for n in range(1, ORDER + 1):
                gram = padded[end - n + 1:end + 1]
                counts[gram] = counts.get(gram, 0) + weight
    return counts


class CharModel:
    """Interpolated absolute-discounting model over letters plus word end."""

    def __init__(self, language, counts, source, thresholds=None):
        self.language = language
        self.source = source
        self.thresholds = thresholds
        self.symbols = len(ALPHABETS[language]) + 1
        self.counts = counts
        self.totals = {}
        self.types = {}
        for gram, count in counts.items():
            context = gram[:-1]
            self.totals[context] = self.totals.get(context, 0) + count
            self.types[context] = self.types.get(context, 0) + 1
        self.cache = {}

    def _probability(self, context, symbol):
        if not context:
            lower = 1 / self.symbols
        else:
            lower = self._probability(context[1:], symbol)
        total = self.totals.get(context)
        if not total:
            return lower
        count = self.counts.get(context + symbol, 0)
        return max(count - DISCOUNT, 0) / total + DISCOUNT * self.types[context] / total * lower

    def band(self, length):
        """(implausible below, typical from) thresholds for a word length."""
        for upper, implausible_below, typical_from in self.thresholds or ():
            if length <= upper:
                return implausible_below, typical_from
        return UNUSUAL_BITS, TYPICAL_BITS

    def bits(self, context, symbol):
        """Information gain over a uniform guess, in bits (positive = typical)."""
        key = context + symbol
        value = self.cache.get(key)
        if value is None:
            if len(self.cache) > 500000:
                self.cache.clear()
            value = math.log2(self._probability(context, symbol) * self.symbols)
            self.cache[key] = value
        return value

    def score(self, text, before=False, after=False):
        """Sum of per-symbol bits. Open ends drop the word-boundary context."""
        context = '' if before else START * (ORDER - 1)
        total = 0.0
        for letter in text:
            total += self.bits(context[-(ORDER - 1):], letter)
            context += letter
        if not after:
            total += self.bits(context[-(ORDER - 1):], END)
        return total


def _load_bundled(language):
    if language not in _bundled:
        path = MODEL_DIR / f'{language}.json'
        model = None
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            model = CharModel(language, data['counts'], data.get('source', 'bundled model'), data.get('thresholds'))
        _bundled[language] = model
    return _bundled[language]


def bundled(language):
    """The shipped model for a language, or None when none is available."""
    if language not in ALPHABETS:
        raise ValueError('Unsupported language.')
    return _load_bundled(language)


def adapted(language, words):
    """Blend the bundled model with a deterministic sample of a word list.

    The list is only a statistics source here; membership checks stay in the
    dictionary search. Short lists keep the bundled model unchanged.
    """
    base = bundled(language)
    if not isinstance(words, list) or len(words) < ADAPT_MIN_WORDS:
        return base
    step = max(1, len(words) // ADAPT_SAMPLE)
    sample = [normalize(w) for w in words[::step] if isinstance(w, str)]
    alphabet = set(ALPHABETS[language])
    sample = [w for w in sample if w and len(w) <= 100 and set(w) <= alphabet]
    if len(sample) < ADAPT_MIN_WORDS:
        return base
    key = (language, len(words), hash(tuple(sample[::max(1, len(sample) // 256)])))
    if key in _adapted:
        return _adapted[key]
    own = count_ngrams(sample)
    if base is None:
        counts = own
        source = 'trained from the current word list'
    else:
        # Equal mass from both sources: a noisy list cannot swamp the base
        # model, and a list with many inflections still shifts endings.
        scale = sum(base.counts.get(c, 0) for c in ALPHABETS[language]) / max(1, sum(own.get(c, 0) for c in ALPHABETS[language]))
        counts = dict(base.counts)
        for gram, count in own.items():
            counts[gram] = counts.get(gram, 0) + count * scale
        source = base.source + ', adapted to the current word list'
    model = CharModel(language, counts, source, base.thresholds if base is not None else None)
    if len(_adapted) >= 6:
        _adapted.clear()
    _adapted[key] = model
    return model


@contextmanager
def use(models):
    """Make {language: model} the active models for scoring in this context."""
    token = _active.set(models)
    try:
        yield
    finally:
        _active.reset(token)


def active(language):
    models = _active.get()
    if models and language in models:
        return models[language]
    return bundled(language)


def rule_findings(text, language, before=False, after=False):
    """Soft spelling rules: [(penalty, reason)]. None are prohibitions."""
    findings = []
    vowels = VOWELS[language]
    run = 1
    worst = 1
    for a, b in zip(text, text[1:]):
        run = run + 1 if a == b else 1
        # Dutch EE + Ë is written EEE in A-Z puzzles (IDEEËN -> IDEEEN).
        if not (language == 'nl' and a == 'E' and run == 3):
            worst = max(worst, run)
    if worst >= 3:
        findings.append((4.0 * (worst - 2), 'three or more identical letters in a row'))
    consonants = longest = 0
    for letter in text:
        consonants = 0 if letter in vowels else consonants + 1
        longest = max(longest, consonants)
    # English has five-consonant runs (STRENGTHS); Finnish natives rarely exceed three.
    limit = {'fi': 3, 'en': 5}.get(language, 4)
    if longest > limit:
        findings.append((1.5 * (longest - limit), f'{longest} consonants in a row'))
    if len(text) >= 3 and not before and not after and not set(text) & vowels:
        findings.append((3.0, 'no vowel'))
    if language in ('en', 'nl', 'sv') and any(a == 'Q' and b != 'U' for a, b in zip(text, text[1:] + ('' if after else ' '))):
        findings.append((2.0, 'Q not followed by U'))
    if language == 'fi':
        letters = set(text)
        # Harmony is a preference: compounds and loanwords can mix groups.
        if letters & set('AOU') and letters & set('ÄÖY'):
            harmonic = [(i, c in 'AOU') for i, c in enumerate(text) if c in 'AOUÄÖY']
            (previous, back), (last, final_back) = harmonic[-2], harmonic[-1]
            if back != final_back and last - previous <= 4 and not after:
                # A compound's last part is usually longer than a case ending.
                findings.append((5.0, 'ending does not follow vowel harmony'))
            else:
                findings.append((2.5, 'mixes back (A O U) and front (Ä Ö Y) vowels'))
        foreign = sorted(letters & set('BCFGQWXZÅ'))
        if foreign:
            findings.append((0.5 * len(foreign), 'letters mostly found in loanwords: ' + ' '.join(foreign)))
        if not before and len(text) >= 2 and text[0] not in vowels and text[1] not in vowels:
            findings.append((1.0, 'starts with two consonants (rare in native words)'))
        if not after and len(text) >= 2 and text[-1] not in vowels and text[-1] not in 'NSTLR':
            findings.append((1.5, f'ends in {text[-1]} (native words end in a vowel or N S T L R)'))
    if language == 'sv':
        foreign = sorted(set(text) & set('QWZ'))
        if foreign:
            findings.append((0.5 * len(foreign), 'letters mostly found in loanwords: ' + ' '.join(foreign)))
    if language == 'nl':
        if 'Y' in text and 'IJ' not in text:
            findings.append((0.5, 'Y is rare outside loanwords (IJ uses two cells)'))
    return findings


def plausibility(text, language, before=False, after=False):
    """Pattern assessment for display. Never a claim that a word exists."""
    model = active(language)
    findings = rule_findings(text, language, before, after)
    reasons = [reason for _, reason in findings]
    if model is None:
        return dict(label='unassessed', bitsPerLetter=None, reasons=reasons,
                    model='no language model available')
    symbols = len(text) + (0 if after else 1)
    bits = (model.score(text, before, after) - sum(p for p, _ in findings)) / max(1, symbols)
    implausible_below, typical_from = model.band(len(text))
    label = 'typical' if bits >= typical_from else 'unusual' if bits >= implausible_below else 'implausible'
    if label == 'typical' and any(penalty >= 4 for penalty, _ in findings):
        label = 'unusual'
    return dict(label=label, bitsPerLetter=round(bits, 2), reasons=reasons, model=model.source)
