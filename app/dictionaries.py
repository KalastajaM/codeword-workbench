"""One local, replaceable word list per supported language."""
import json
import os
import re
import threading
from pathlib import Path
import tempfile
import unicodedata

MAX_WORDS = 1_000_000
MAX_IMPORT_BYTES = 16 * 1024 * 1024

ALPHABETS = {'en': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'fi': 'ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ', 'nl': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'sv': 'ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ'}
DEMO = {
    'sv': 'OCH I ATT DET SOM EN PÅ ÄR AV FÖR MED TILL DEN HAR DE INTE OM ETT MEN VAR JAG SIG FRÅN VI SÅ KAN MAN NÄR ÅR HUS BIL BÅT BOK KATT HUND FISK VATTEN ELD JORD LUFT SOL MÅNE STJÄRNA DAG NATT SKOLA ORD BOKSTAV NUMMER SPRÅK KORSORD SVERIGE BRA RÖD GRÖN BLÅ GUL STOR LITEN ÄPPLE ÖGA ÖRA FÅGEL SJÖ SKOG BRÖD MJÖLK',
    'nl': 'DE HET EEN EN OF IN OP IS IK JE JIJ WIJ HIJ ZIJ U NU JA NEE BIJ MET VAN VOOR NAAR UIT AAN ALS DAT DIT DIE WAT WIE WAAR ZIJN HEBBEN DOEN GAAN HUIS BOOM BOEK FIETS DIJK IJS KAT HOND VIS WATER VUUR AARDE LUCHT ZON MAAN STER DAG NACHT SCHOOL WOORD LETTER NUMMER TAAL PUZZEL NEDERLAND GOED ROOD GROEN BLAUW GEEL',
    'en': 'A I AN AS AT BE BY DO GO HE IF IN IS IT ME MY NO OF ON OR SO TO UP US WE CAT DOG DAD DID MOM SUN SEA SKY CAR BUS MAP PEN RED ART EAT TEA ATE RAT TAR EAR ARE ERA TEN NET ONE TWO BAT BAR TAB BOAT BOOK CODE WORD HOME HOUSE WATER CROSS PUZZLE LETTER NUMBER HELLO WORLD TEST TREE ROAD STAR MOON LIGHT NIGHT DAY PLAY READ WRITE',
    'fi': 'JA ON EI SE NE ME TE HE JO EN ET NYT TAI KUN KUU PUU SUU TIE YÖ TYÖ PÄÄ SÄÄ MAA SAA SANA TALO KOTI ÄITI ISÄ LAPSI KALA KANA KOIRA KISSA AUTO VESI TULI TUULI MERI JOKI JÄRVI SUOMI SAUNA KOULU KIRJA KYNÄ OVI IKKUNA AAMU ILTA PÄIVÄ YKSI KAKSI KOLME NELJÄ VIISI KUUSI',
}


def normalize(text):
    return unicodedata.normalize('NFC', text.strip().upper())


def clean_words(language, words):
    if language not in ALPHABETS: raise ValueError('Unsupported language.')
    if not isinstance(words,list) or len(words)>MAX_WORDS: raise ValueError('Expected a list of at most 1,000,000 words.')
    alphabet=set(ALPHABETS[language]); result=set()
    for word in words:
        if not isinstance(word,str): raise ValueError('Dictionary entries must be strings.')
        word=normalize(word)
        if not word: continue
        if len(word)>100 or not set(word)<=alphabet:
            raise ValueError('Dictionary entries must contain only letters of the selected alphabet and at most 100 letters.')
        result.add(word)
    return sorted(result)


def import_dictionary(language, text, data_dir):
    """Import real-world lists, reporting discarded lines without altering spellings."""
    if language not in ALPHABETS:
        raise ValueError('Unsupported language.')
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_IMPORT_BYTES:
        raise ValueError('Word list must be UTF-8 text of at most 16 MB.')
    lines = text.removeprefix('\ufeff').splitlines()
    if len(lines) > MAX_WORDS:
        raise ValueError('Word list must contain at most 1,000,000 lines.')
    alphabet = set(ALPHABETS[language])
    words = set()
    total = skipped = duplicates = 0
    for line in lines:
        word = normalize(line)
        if not word:
            continue
        total += 1
        if len(word) > 100 or not set(word) <= alphabet:
            skipped += 1
        elif word in words:
            duplicates += 1
        else:
            words.add(word)
    if not words:
        raise ValueError('No usable words found for the selected alphabet. Existing dictionary was kept.')
    result = save_dictionary(language, list(words), data_dir)
    result.update(total=total, skipped=skipped, duplicates=duplicates)
    return result


def get_dictionary(language, data_dir):
    if language not in ALPHABETS: raise ValueError('Unsupported language.')
    path=Path(data_dir)/'dictionaries'/f'{language}.json'
    if path.exists():
        words=clean_words(language,json.loads(path.read_text(encoding='utf-8')))
        return dict(language=language,words=words,source='custom local dictionary')
    return dict(language=language,words=sorted(set(DEMO[language].split())),source='bundled demonstration vocabulary (not comprehensive)')


MAX_EDIT_ENTRIES = 10000
SEARCH_PAGE = 100
_states = {}
_edit_lock = threading.RLock()


def _file_key(path):
    try:
        stat = path.stat()
        return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    except FileNotFoundError:
        return (str(path), None, None)


def _paths(language, data_dir):
    folder = Path(data_dir)/'dictionaries'
    return folder/f'{language}.json', folder/f'{language}.disabled.json'


def get_disabled(language, data_dir):
    """Disabled entries stay in the list but are skipped by every search."""
    if language not in ALPHABETS: raise ValueError('Unsupported language.')
    path = _paths(language, data_dir)[1]
    if not path.exists(): return []
    return clean_words(language, json.loads(path.read_text(encoding='utf-8')))


def dictionary_state(language, data_dir):
    """Cached {words, word_set, disabled, active, active_set} until either file changes.

    Lookups run on every word selection; reloading an 870k-word list each
    time would take about a second.
    """
    if language not in ALPHABETS: raise ValueError('Unsupported language.')
    key = tuple(_file_key(path) for path in _paths(language, data_dir))
    cached = _states.get(language)
    if cached and cached[0] == key: return cached[1]
    words = get_dictionary(language, data_dir)['words']
    return _store_state(language, data_dir, words, frozenset(get_disabled(language, data_dir)))


def _store_state(language, data_dir, words, disabled, word_set=None):
    """Cache a state for the files as they are now (after a load or a write)."""
    word_set = word_set if word_set is not None else frozenset(words)
    disabled = frozenset(disabled) & word_set
    active = [w for w in words if w not in disabled] if disabled else words
    state = dict(words=words, word_set=word_set, disabled=disabled, active=active,
                 active_set=word_set - disabled if disabled else word_set)
    _states[language] = (tuple(_file_key(path) for path in _paths(language, data_dir)), state)
    return state


def active_words(language, data_dir):
    """Entries used for solving and searching: the list minus disabled words."""
    return dictionary_state(language, data_dir)['active']


def dictionary_word_set(language, data_dir):
    """(active words, active set), cached until the dictionary changes."""
    state = dictionary_state(language, data_dir)
    return state['active'], state['active_set']


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.dictionary-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(value, out, ensure_ascii=False); out.flush(); os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def save_dictionary(language, words, data_dir):
    words=clean_words(language,words)
    with _edit_lock:
        path, disabled_path = _paths(language, data_dir)
        _write_json(path, words)
        # Disabled marks only apply to entries that are still listed.
        disabled = get_disabled(language, data_dir)
        if disabled:
            kept = sorted(set(disabled) & set(words))
            if kept != disabled: _write_json(disabled_path, kept)
    return dict(language=language,count=len(words),source='custom local dictionary')


def _search_pattern(language, query):
    alphabet = set(ALPHABETS[language])
    query = normalize(query or '')
    if not set(query) <= alphabet | set('?*'):
        raise ValueError('Search with letters of the selected alphabet, ? for one letter and * for any letters.')
    if not query: return None
    if '?' not in query and '*' not in query: query += '*'
    return re.compile(''.join('.' if c == '?' else '.*' if c == '*' else re.escape(c) for c in query))


def search_dictionary(language, data_dir, query='', status='all', offset=0, limit=SEARCH_PAGE):
    """Filtered page of entries. Plain text is a prefix; ? is one letter, * any letters."""
    if status not in ('all', 'enabled', 'disabled'): raise ValueError('Filter must be all, enabled or disabled.')
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Invalid result page.')
    state = dictionary_state(language, data_dir)
    pattern = _search_pattern(language, query)
    pool = sorted(state['disabled']) if status == 'disabled' else state['active'] if status == 'enabled' else state['words']
    matches = [w for w in pool if pattern.fullmatch(w)] if pattern else pool
    page = [dict(word=w, enabled=w not in state['disabled']) for w in matches[offset:offset + limit]]
    return dict(language=language, query=normalize(query or ''), status=status, total=len(matches), offset=offset,
                limit=limit, words=page, count=len(state['words']), disabledCount=len(state['disabled']),
                custom=_paths(language, data_dir)[0].exists())


def edit_dictionary(language, data_dir, add=None, remove=None, enable=None, disable=None):
    """Apply small edits immediately. A demonstration list becomes a custom list."""
    if language not in ALPHABETS: raise ValueError('Unsupported language.')
    lists = {name: [] if items is None else items for name, items in dict(add=add, remove=remove, enable=enable, disable=disable).items()}
    for name, items in lists.items():
        if not isinstance(items, list) or len(items) > MAX_EDIT_ENTRIES or any(not isinstance(w, str) or len(w) > 100 for w in items):
            raise ValueError(f'{name} must be a list of at most {MAX_EDIT_ENTRIES:,} words.')
    alphabet = set(ALPHABETS[language])
    cleaned = {}
    for name, items in lists.items():
        words = [normalize(w) for w in items]
        bad = [w for w in words if not w or not set(w) <= alphabet]
        if bad:
            raise ValueError('Not a word in the selected alphabet: ' + ', '.join(bad[:5]) + ('…' if len(bad) > 5 else ''))
        cleaned[name] = set(words)
    with _edit_lock:
        state = dictionary_state(language, data_dir)
        words = set(state['words'])
        disabled = set(state['disabled'])
        added = cleaned['add'] - words
        removed = cleaned['remove'] & words
        words = (words | added) - removed
        enabled_now = cleaned['enable'] & disabled
        disabled_now = (cleaned['disable'] & words) - disabled
        disabled = ((disabled | disabled_now) - enabled_now) & words
        path, disabled_path = _paths(language, data_dir)
        listed = state['words']
        if added or removed or not path.exists():
            if len(words) > MAX_WORDS: raise ValueError('A dictionary can hold at most 1,000,000 entries.')
            listed = sorted(words)
            _write_json(path, listed)
        if disabled != set(state['disabled']):
            _write_json(disabled_path, sorted(disabled))
        # Reuse the edited list instead of reloading it from disk.
        _store_state(language, data_dir, listed, disabled, None if listed is not state['words'] else state['word_set'])
    return dict(language=language, count=len(words), disabledCount=len(disabled), added=len(added),
                removed=len(removed), enabled=len(enabled_now), disabled=len(disabled_now),
                skipped=len(cleaned['add']) - len(added) + len(cleaned['remove']) - len(removed),
                source='custom local dictionary')
