"""Per-search word index: closed slots never scan irrelevant lengths/patterns."""
from collections import defaultdict
from .dictionaries import ALPHABETS, MAX_WORDS, normalize

MAX_FRAGMENTS = 20000


def pattern(items):
    seen = {}
    return tuple(seen.setdefault(item, len(seen)) for item in items)


def slot_length_filter(slots):
    """Closed slots need exact lengths; open fragments may come from longer words."""
    if slots is None:
        return lambda length: True
    closed = {len(slot['cells']) for slot in slots if not slot['before'] and not slot['after']}
    minimum_open = min((len(slot['cells']) for slot in slots if slot['before'] or slot['after']), default=None)
    return lambda length: length in closed or (minimum_open is not None and length >= minimum_open)


class WordIndex:
    def __init__(self, language, words, check, *, slots=None):
        if not isinstance(words, list) or len(words) > MAX_WORDS:
            raise ValueError(f'Expected a list of at most {MAX_WORDS:,} words.')
        alphabet = set(ALPHABETS[language])
        eligible_length = slot_length_filter(slots)
        unique = set()
        self.by_length = defaultdict(list)
        self.by_pattern = defaultdict(list)
        self.fragments = {}
        self.truncated = False
        for j, word in enumerate(words):
            if j % 128 == 0: check()
            if not isinstance(word, str): raise ValueError('Dictionary entries must be strings.')
            word = normalize(word)
            if not word: continue
            if len(word) > 100 or not set(word) <= alphabet:
                raise ValueError('Dictionary entries must contain only letters of the selected alphabet and at most 100 letters.')
            if word in unique: continue
            unique.add(word)
            if not eligible_length(len(word)): continue
            self.by_length[len(word)].append(word)
            self.by_pattern[(len(word), pattern(word))].append(word)
        self.size = len(unique)
        self.indexed_size = sum(len(bucket) for bucket in self.by_length.values())
        for bucket in self.by_length.values(): bucket.sort()
        for bucket in self.by_pattern.values(): bucket.sort()

    def candidates(self, p, slot, rules, check):
        length = len(slot['cells'])
        if not slot['before'] and not slot['after']:
            numbers = [p['cells'][i].get('number') for i in slot['cells']]
            if all(numbers) and rules['uniqueLetters'] and rules['maxLettersPerNumber'] == 1:
                return self.by_pattern.get((length, pattern(str(int(n)) for n in numbers)), ())
            return self.by_length.get(length, ())
        key = (length, slot['before'], slot['after'])
        if key in self.fragments: return self.fragments[key]
        return self._fragments(key, slot, length, check)

    def _fragments(self, key, slot, length, check):
        found = set()
        for size, words in self.by_length.items():
            if size < length: continue
            for j, word in enumerate(words):
                if j % 128 == 0: check()
                if slot['before'] and slot['after']:
                    pieces = (word[k:k+length] for k in range(size-length+1))
                elif slot['before']: pieces = (word[-length:],)
                else: pieces = (word[:length],)
                for text in pieces:
                    if text in found: continue
                    if len(found) >= MAX_FRAGMENTS:
                        self.truncated = True
                        self.fragments[key] = tuple(sorted(found))
                        return
                    found.add(text)
                    yield text
        self.fragments[key] = tuple(sorted(found))
