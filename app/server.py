"""Local-first HTTP API with explicit authenticated hosted mode."""
import base64
import binascii
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

from . import ocr
from .dictionaries import ALPHABETS, MAX_WORDS

ROOT = Path(__file__).resolve().parent.parent
MAX_BODY = 20_000_000
ID_RE = re.compile(r'^[a-f0-9]{32}$')


def check_puzzle(p):
    if not isinstance(p, dict):
        raise ValueError('A puzzle must be a JSON object.')
    rows, cols = p.get('rows'), p.get('cols')
    if type(rows) is not int or type(cols) is not int or not (1 <= rows <= 40 and 1 <= cols <= 40):
        raise ValueError('Grid dimensions must be whole numbers from 1 to 40.')
    lang = p.get('language')
    if lang not in ALPHABETS:
        raise ValueError('Select English, Finnish, Dutch or Swedish.')
    alphabet = ALPHABETS[lang]
    cells = p.get('cells')
    if not isinstance(cells, list) or len(cells) != rows*cols:
        raise ValueError('The number of cells must match the grid dimensions.')
    for cell in cells:
        if not isinstance(cell, dict) or type(cell.get('black', False)) is not bool:
            raise ValueError('Each cell must have a valid black-cell state.')
        number = cell.get('number', '')
        if not isinstance(number, str) or (number and not re.fullmatch(r'[1-9][0-9]{0,2}', number)):
            raise ValueError('Cell numbers must be empty or integers from 1 to 999.')
        letter = cell.get('letter', '')
        if not isinstance(letter, str):
            raise ValueError('Cell letters must be text.')
        letter = unicodedata.normalize('NFC', letter).upper().strip()
        if letter and (len(letter) != 1 or letter not in alphabet):
            raise ValueError('Each cell holds one letter from the selected language.')
        cell['letter'] = letter
        if 'guess' in cell:
            guess = cell['guess']
            if not isinstance(guess, str):
                raise ValueError('Provisional guesses must be text.')
            guess = unicodedata.normalize('NFC', guess).upper().strip()
            if guess and (len(guess) != 1 or guess not in alphabet):
                raise ValueError('Each provisional guess holds one letter from the selected language.')
            cell['guess'] = '' if cell.get('black') else guess
        for flag in ('clue', 'highlight', 'prefilled', 'mappingAnchor'):
            if flag in cell and type(cell[flag]) is not bool:
                raise ValueError('Cell metadata settings must be true or false.')
        if cell.get('numberReview') not in (None, 'check', 'missing'):
            raise ValueError('Number review marks are check or missing.')
        if cell.get('black'):
            # A cell turned into a block or picture area keeps no review mark.
            cell.pop('numberReview', None)
        if cell.get('clue') and not cell.get('black'):
            raise ValueError('Image clue areas cannot also be letter cells.')
        for flag in ('openBeforeAcross', 'openAfterAcross', 'openBeforeDown', 'openAfterDown'):
            if flag in cell and type(cell[flag]) is not bool:
                raise ValueError('Word boundary settings must be true or false.')
    if p.get('searchMode', 'quick') not in ('quick', 'deep', 'extended'):
        raise ValueError('Search mode must be quick, deep or extended.')
    if type(p.get('allowUnknownWords', False)) is not bool:
        raise ValueError('Unknown-word selection must be a boolean.')
    if type(p.get('useMorphology', True)) is not bool:
        raise ValueError('Morphology selection must be a boolean.')
    if type(p.get('useDictionary', True)) is not bool:
        raise ValueError('Dictionary selection must be true or false.')
    rules = p.get('rules', {})
    if not isinstance(rules, dict):
        raise ValueError('Rules must be an object.')
    capacity = rules.get('maxLettersPerNumber', 1)
    if type(capacity) is not int or not 1 <= capacity <= len(alphabet):
        raise ValueError('Letters per number must be between 1 and the alphabet size.')
    if type(rules.get('uniqueLetters', True)) is not bool:
        raise ValueError('Unique letters must be true or false.')
    for key in ('forbiddenPatterns', 'discouragedPatterns'):
        patterns = rules.get(key, [])
        if not isinstance(patterns, list) or len(patterns) > 100 or any(not isinstance(v, str) or not 1 <= len(v) <= 40 for v in patterns):
            raise ValueError('Pattern rules must be a list of up to 100 non-empty literal patterns.')
        normalized = [unicodedata.normalize('NFC', value.strip().upper()) for value in patterns]
        if any(not value or not set(value) <= set(alphabet) for value in normalized):
            raise ValueError('Rule patterns must contain only letters from the selected language.')
        rules[key] = normalized
    from .eliminations import check as check_eliminations
    check_eliminations(p, lang)
    name = p.get('name', 'Untitled puzzle')
    if not isinstance(name, str) or len(name) > 200:
        raise ValueError('Puzzle names must be text of at most 200 characters.')
    if 'image' in p and not isinstance(p['image'], str):
        raise ValueError('Puzzle image must be an image data URL string.')
    if p.get('image'):
        image = p['image']
        if not isinstance(image, str) or not re.fullmatch(r'data:image/(png|jpeg|webp|bmp);base64,[A-Za-z0-9+/=\r\n]+', image):
            raise ValueError('Puzzle image must be a PNG, JPEG, WebP or BMP data URL.')
        if len(image) > 16_100_000:
            raise ValueError('Image exceeds the 12 MB limit.')
        ocr.decode_image(image)
    if p.get('imageBounds') is not None:
        ocr.image_bounds(p['imageBounds'])
    if not isinstance(p.get('straightenedPhoto', False), bool):
        raise ValueError('straightenedPhoto must be true or false.')
    return p


class PuzzleStore:
    def __init__(self, data_dir):
        self.directory = Path(data_dir)/'puzzles'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def path(self, key):
        if not isinstance(key, str) or not ID_RE.fullmatch(key):
            raise ValueError('Invalid puzzle identifier.')
        return self.directory / (key + '.json')

    def list(self):
        result = []
        for path in self.directory.glob('*.json'):
            try:
                p = json.loads(path.read_text(encoding='utf-8'))
                result.append({k: p[k] for k in ('id', 'name', 'updatedAt')})
            except (ValueError, OSError, KeyError, TypeError):
                continue
        return sorted(result, key=lambda item: item['updatedAt'], reverse=True)

    def get(self, key):
        return json.loads(self.path(key).read_text(encoding='utf-8'))

    def save(self, p):
        check_puzzle(p)
        key = p.get('id') or uuid.uuid4().hex
        path = self.path(key)
        saved = dict(p, id=key, name=p.get('name', '').strip() or 'Untitled puzzle', updatedAt=datetime.now(timezone.utc).isoformat())
        encoded = json.dumps(saved, ensure_ascii=False, allow_nan=False)
        with self.lock:
            if p.get('id') and not path.is_file():
                raise FileNotFoundError('This saved puzzle no longer exists.')
            temp = path.with_suffix('.tmp')
            temp.write_text(encoded, encoding='utf-8')
            os.replace(temp, path)
        return {k: saved[k] for k in ('id', 'name', 'updatedAt')}

    def rename(self, key, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError('Enter a puzzle name of 1 to 200 characters.')
        path = self.path(key)
        with self.lock:
            saved = json.loads(path.read_text(encoding='utf-8'))
            saved['name'] = name.strip()
            saved['updatedAt'] = datetime.now(timezone.utc).isoformat()
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(saved, ensure_ascii=False, allow_nan=False), encoding='utf-8')
            os.replace(temp, path)
        return {k: saved[k] for k in ('id', 'name', 'updatedAt')}

    def delete(self, key):
        path = self.path(key)
        with self.lock:
            if not path.is_file():
                raise FileNotFoundError()
            trash = self.directory.parent / 'trash' / 'puzzles'
            trash.mkdir(parents=True, exist_ok=True)
            os.replace(path, trash / f'{key}.{uuid.uuid4().hex}.json')
        return {'deleted': True, 'id': key}


class AutosaveStore:
    """One recoverable copy of the current workspace, so a reload loses nothing."""

    def __init__(self, data_dir):
        self.path = Path(data_dir)/'autosave.json'
        self.lock = threading.Lock()

    def get(self):
        try:
            return json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return None
        except (ValueError, OSError):
            # A damaged autosave must not block starting a fresh workspace.
            return None

    def put(self, value):
        if not isinstance(value, dict) or type(value.get('unsaved')) is not bool:
            raise ValueError('Autosave needs a puzzle and an unsaved flag.')
        check_puzzle(value.get('puzzle'))
        saved = {'puzzle': value['puzzle'], 'unsaved': value['unsaved'],
                 'savedAt': datetime.now(timezone.utc).isoformat()}
        encoded = json.dumps(saved, ensure_ascii=False, allow_nan=False)
        with self.lock:
            temp = self.path.with_suffix('.tmp')
            temp.write_text(encoded, encoding='utf-8')
            os.replace(temp, self.path)
        return {'savedAt': saved['savedAt']}


def hosted_configuration(host, public_origin, access_password, allow_public):
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == 'localhost'
    hosted = not loopback or public_origin is not None or access_password is not None or allow_public
    if not hosted:
        return None
    if not isinstance(public_origin, str) or any(char.isspace() for char in public_origin):
        raise ValueError('Hosted mode requires a valid HTTPS public origin.')
    try:
        origin = urlsplit(public_origin)
        port = origin.port
        hostname = origin.hostname or ''
        try:
            ipaddress.ip_address(hostname)
            valid_hostname = True
        except ValueError:
            valid_hostname = bool(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', hostname))
            valid_hostname = valid_hostname and all(label and len(label) <= 63 and not label.startswith('-') and not label.endswith('-') for label in hostname.split('.'))
        valid = (origin.scheme == 'https' and valid_hostname and origin.username is None and
                 origin.password is None and public_origin == 'https://' + origin.netloc and
                 not origin.path and not origin.query and not origin.fragment and
                 not any(char in origin.netloc for char in '\\?#') and
                 (port is None or 1 <= port <= 65535))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Hosted public origin must be a bare HTTPS origin without credentials, path, query or fragment.')
    if access_password is not None:
        if not isinstance(access_password, str) or sum(not char.isspace() for char in access_password) < 16:
            raise ValueError('Hosted access password must contain at least 16 non-whitespace characters.')
    elif allow_public is not True:
        raise ValueError('Hosted mode requires an access password or explicit public access opt-in.')
    return origin.netloc


def make_server(port=8765, data_dir=None, *, host='127.0.0.1', public_origin=None, access_password=None, allow_public=False):
    hosted_host = hosted_configuration(host, public_origin, access_password, allow_public)
    store = PuzzleStore(data_dir or ROOT/'data')
    autosave = AutosaveStore(data_dir or ROOT/'data')
    data_dir = Path(data_dir or ROOT/'data')
    expensive = threading.BoundedSemaphore(2)

    def morphology_for(puzzle):
        from .morphology import MorphologyIndex
        requested = puzzle['language']=='fi' and puzzle.get('useDictionary',True) and puzzle.get('useMorphology',True)
        path = data_dir/'morphology'/'fi.sqlite'
        return (MorphologyIndex(path) if requested and path.exists() else None), requested

    def run_lookup(puzzle, query, use_mappings):
        """Word lookup always checks the dictionary; pattern search follows the puzzle setting."""
        from .dictionaries import active_words
        from .lookup import parse_pattern, pattern_search
        from .morphology import MorphologyIndex
        from .dictionaries import dictionary_state
        from .lookup import lookup_word
        tokens = parse_pattern(puzzle['language'], query)
        word_only = all(kind == 'letter' for kind, _ in tokens)
        use_words = word_only or puzzle.get('useDictionary', True)
        path = data_dir/'morphology'/'fi.sqlite'
        wants_morphology = puzzle['language'] == 'fi' and puzzle.get('useMorphology', True) and use_words
        index = MorphologyIndex(path) if wants_morphology and path.exists() else None
        if word_only:
            state = dictionary_state(puzzle['language'], data_dir)
            word = ''.join(value for _, value in tokens)
            result = lookup_word(puzzle, word, state['active'], index, state['active_set'])
            result['disabled'] = word in state['disabled']
        else:
            words = active_words(puzzle['language'], data_dir) if use_words else []
            result = pattern_search(dict(puzzle, useDictionary=use_words), query, words, morphology=index, use_mappings=use_mappings)
        if wants_morphology and index is None:
            result['diagnostics'].append('Local Finnish morphology index is unavailable; searched the word list only.')
        return result

    def run_solve(puzzle, **options):
        from .solver import solve
        from .dictionaries import active_words
        words = active_words(puzzle['language'], data_dir) if puzzle.get('useDictionary',True) else []
        index, requested = morphology_for(puzzle)
        result = solve(puzzle, words, morphology=index, **options)
        if requested and index is None:
            result['diagnostics'].append('Local Finnish morphology index is unavailable; searched the word list only.')
        return result

    from .solve_jobs import SolveJobs, JobCapacityError
    jobs = SolveJobs(run_solve, expensive)

    class Handler(BaseHTTPRequestHandler):
        server_version = 'CodewordWorkbench/0.1'

        def setup(self):
            super().setup()
            self.connection.settimeout(30)


        def send_data(self, code, data, content_type='application/json; charset=utf-8', challenge=False):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            if challenge:
                self.send_header('WWW-Authenticate', 'Basic realm="Codeword Workbench", charset="UTF-8"')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(data)

        def trusted_request(self):
            port = self.server.server_port
            hosts = {hosted_host} if hosted_host else {f'127.0.0.1:{port}', f'localhost:{port}'}
            if len(self.headers.get_all('Host', [])) != 1 or self.headers.get('Host') not in hosts:
                self.send_data(403, {'error': 'Request host is not accepted.'})
                return False
            origins = {public_origin} if hosted_host else {'http://' + h for h in hosts}
            origin = self.headers.get('Origin')
            if len(self.headers.get_all('Origin', [])) > 1 or (origin is not None and origin not in origins):
                self.send_data(403, {'error': 'Cross-origin requests are not accepted.'})
                return False
            if hosted_host and access_password is not None:
                authorization = self.headers.get('Authorization', '')
                authenticated = False
                try:
                    scheme, encoded = authorization.split(' ', 1)
                    decoded = base64.b64decode(encoded, validate=True)
                    username, password = decoded.split(b':', 1)
                    authenticated = (scheme.lower() == 'basic' and
                                     hmac.compare_digest(username, b'codeword') and
                                     hmac.compare_digest(password, access_password.encode('utf-8')) and
                                     len(self.headers.get_all('Authorization', [])) == 1)
                except (ValueError, binascii.Error):
                    pass
                if not authenticated:
                    self.send_data(401, {'error': 'Authentication required.'}, challenge=True)
                    return False
            return True

        def payload(self):
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise ValueError('Request content type must be application/json.')
            try:
                size = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                raise ValueError('Invalid request length.') from None
            if not 0 < size <= MAX_BODY:
                raise ValueError('Request is empty or exceeds the 20 MB limit.')
            def reject_constant(value):
                raise ValueError('JSON numbers must be finite.')
            value = json.loads(self.rfile.read(size), parse_constant=reject_constant)
            if not isinstance(value, dict):
                raise ValueError('Request must be a JSON object.')
            return value

        def do_GET(self):
            self.dispatch('GET')

        def do_POST(self):
            self.dispatch('POST')

        def do_PUT(self):
            self.dispatch('PUT')

        def do_PATCH(self):
            self.dispatch('PATCH')

        def do_DELETE(self):
            self.dispatch('DELETE')

        def do_HEAD(self):
            self.dispatch('HEAD')

        def do_OPTIONS(self):
            self.dispatch('OPTIONS')

        def dispatch(self, method):
            # Railway probes use their own Host header. This exact endpoint discloses
            # no puzzle data, configuration, paths or optional runtime capabilities.
            if method == 'GET' and self.path == '/healthz':
                self.send_data(200, {'ok': True})
                return
            if not self.trusted_request():
                return
            path = urlsplit(self.path).path
            try:
                if method == 'GET' and path == '/api/health':
                    self.send_data(200, {'ok': True, 'ocrAvailable': ocr.available()})
                elif method == 'GET' and path == '/api/autosave':
                    self.send_data(200, {'autosave': autosave.get()})
                elif method == 'PUT' and path == '/api/autosave':
                    self.send_data(200, autosave.put(self.payload()))
                elif method == 'GET' and path == '/api/puzzles':
                    self.send_data(200, {'puzzles': store.list()})
                elif method == 'GET' and path.startswith('/api/puzzles/'):
                    self.send_data(200, store.get(path.rsplit('/', 1)[1]))
                elif method == 'PATCH' and path.startswith('/api/puzzles/'):
                    self.send_data(200, store.rename(path.rsplit('/', 1)[1], self.payload().get('name')))
                elif method == 'DELETE' and path.startswith('/api/puzzles/'):
                    self.send_data(200, store.delete(path.rsplit('/', 1)[1]))
                elif method == 'POST' and path == '/api/puzzles':
                    self.send_data(200, store.save(self.payload()))
                elif method == 'POST' and re.fullmatch(r'/api/dictionaries/[^/]+/import', path):
                    from .dictionaries import import_dictionary
                    self.send_data(200, import_dictionary(path.split('/')[3], self.payload().get('text'), data_dir))
                elif method == 'GET' and re.fullmatch(r'/api/dictionaries/[^/]+/search', path):
                    from .dictionaries import search_dictionary
                    from urllib.parse import parse_qs
                    query = parse_qs(urlsplit(self.path).query)
                    first = lambda name, default='': query.get(name, [default])[0]
                    if not first('offset', '0').isdigit():
                        raise ValueError('Invalid result page.')
                    self.send_data(200, search_dictionary(path.split('/')[3], data_dir, first('q'), first('status', 'all'),
                                                          int(first('offset', '0'))))
                elif method == 'POST' and re.fullmatch(r'/api/dictionaries/[^/]+/entries', path):
                    from .dictionaries import edit_dictionary
                    edits = self.payload()
                    if not isinstance(edits, dict):
                        raise ValueError('Dictionary edits must be a JSON object.')
                    self.send_data(200, edit_dictionary(path.split('/')[3], data_dir, **{k: edits.get(k, []) for k in ('add', 'remove', 'enable', 'disable')}))
                elif path.startswith('/api/dictionaries/') and method in ('GET', 'PUT'):
                    from .dictionaries import get_dictionary, save_dictionary
                    language = path.rsplit('/', 1)[1]
                    if language not in ALPHABETS:
                        raise ValueError('Select English, Finnish, Dutch or Swedish.')
                    if method == 'GET':
                        from .dictionaries import get_disabled
                        self.send_data(200, dict(get_dictionary(language, data_dir), disabled=get_disabled(language, data_dir)))
                    else:
                        words = self.payload().get('words')
                        if not isinstance(words, list) or len(words) > MAX_WORDS or any(not isinstance(w, str) or len(w) > 100 for w in words):
                            raise ValueError('Dictionary must contain up to 1,000,000 text entries of at most 100 characters each.')
                        self.send_data(200, save_dictionary(language, words, data_dir))
                elif method == 'POST' and path == '/api/solve-jobs':
                    self.send_data(202, jobs.start(check_puzzle(self.payload())))
                elif method in ('GET', 'DELETE') and path.startswith('/api/solve-jobs/'):
                    key = path.rsplit('/',1)[1]
                    if not ID_RE.fullmatch(key):
                        raise ValueError('Invalid search job identifier.')
                    self.send_data(200, jobs.get(key, cancel=method=='DELETE'))
                elif method == 'POST' and path == '/api/pdf':
                    from .pdf_import import convert
                    payload = self.payload()
                    if not expensive.acquire(blocking=False):
                        self.send_data(429, {'error': 'Another import or solve is running. Try again shortly.'})
                        return
                    try:
                        self.send_data(200, convert(payload))
                    finally:
                        expensive.release()
                elif method == 'POST' and path == '/api/lookup':
                    payload = self.payload()
                    if not isinstance(payload, dict) or not isinstance(payload.get('query'), str):
                        raise ValueError('Lookup needs a puzzle and a query.')
                    if len(payload['query']) > 200:
                        raise ValueError('Lookup query is too long.')
                    p = check_puzzle(payload.get('puzzle'))
                    if re.fullmatch(r'[^\d?._*]*', payload['query']):
                        # Single-word checks are cheap (cached word set) and run
                        # on every selection, so they never wait for a search.
                        self.send_data(200, run_lookup(p, payload['query'], True))
                        return
                    if not expensive.acquire(blocking=False):
                        self.send_data(429, {'error': 'Another search is running. Try again shortly.'})
                        return
                    try:
                        self.send_data(200, run_lookup(p, payload['query'], payload.get('useMappings', True) is not False))
                    finally:
                        expensive.release()
                elif method == 'POST' and path in ('/api/validate', '/api/solve', '/api/ocr', '/api/candidates'):
                    p = self.payload()
                    slot_ids = None
                    if path == '/api/candidates':
                        if not isinstance(p, dict):
                            raise ValueError('Candidate search must be a JSON object.')
                        slot_ids = p.get('slotIds')
                        p = p.get('puzzle')
                    if path != '/api/ocr':
                        check_puzzle(p)
                    if path == '/api/validate':
                        from .solver import validate, suggested_eliminations
                        result = validate(p)
                        if result['valid']:
                            result['suggestedEliminations'] = suggested_eliminations(p)
                        self.send_data(200, result)
                    else:
                        if not expensive.acquire(blocking=False):
                            self.send_data(429, {'error': 'Another solve or recognition is running. Try again shortly.'})
                            return
                        try:
                            if path == '/api/ocr':
                                result = ocr.recognize(p)
                            else:
                                if path == '/api/candidates':
                                    from .dictionaries import active_words
                                    words = active_words(p['language'], data_dir) if p.get('useDictionary', True) else []
                                    from .candidates import find_candidates
                                    from .morphology import MorphologyIndex
                                    index_path = data_dir/'morphology'/'fi.sqlite'
                                    use_morphology = p['language']=='fi' and p.get('useDictionary',True) and p.get('useMorphology',True)
                                    index = MorphologyIndex(index_path) if use_morphology and index_path.exists() else None
                                    result = find_candidates(p, words, slot_ids, morphology=index)
                                    if use_morphology and index is None:
                                        result['diagnostics'].append('Local Finnish morphology index is unavailable; searched the word list only.')
                                else:
                                    result = run_solve(p)
                            self.send_data(200, result)
                        finally:
                            expensive.release()
                elif method == 'POST' and path == '/api/straighten/detect':
                    p = self.payload()
                    if not expensive.acquire(blocking=False):
                        self.send_data(429, {'error': 'Another solve or recognition is running. Try again shortly.'})
                        return
                    try:
                        from .straighten import detect
                        self.send_data(200, detect(p))
                    finally:
                        expensive.release()
                elif method == 'POST' and path == '/api/straighten':
                    p = self.payload()
                    if not expensive.acquire(blocking=False):
                        self.send_data(429, {'error': 'Another solve or recognition is running. Try again shortly.'})
                        return
                    try:
                        from .straighten import straighten
                        self.send_data(200, straighten(p))
                    finally:
                        expensive.release()
                elif method == 'GET' and not path.startswith('/api/'):
                    relative = unquote(path).lstrip('/') or 'index.html'
                    target = (ROOT/'static'/relative).resolve()
                    if not target.is_relative_to((ROOT/'static').resolve()) or not target.is_file():
                        raise FileNotFoundError()
                    mime = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
                    self.send_data(200, target.read_bytes(), mime)
                else:
                    self.send_data(404, {'error': 'Endpoint not found.'})
            except JobCapacityError as exc:
                self.send_data(429, {'error': str(exc)})
            except FileNotFoundError:
                self.send_data(404, {'error': 'File or puzzle not found.'})
            except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                self.send_data(400, {'error': str(exc) or 'Invalid request.'})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                import traceback
                traceback.print_exc()
                self.send_data(500, {'error': 'The local server could not complete the request. See its terminal output.'})

    class LocalServer(ThreadingHTTPServer):
        def server_close(self):
            jobs.close()
            super().server_close()

    server = LocalServer((host, port), Handler)
    server.daemon_threads = True
    return server
