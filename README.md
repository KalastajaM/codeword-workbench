# Codeword Workbench

A local browser workspace for solving codeword puzzles (number-cipher
crosswords) in English, Finnish, Dutch and Swedish. Import a screenshot, photo
or PDF of a puzzle, or draw the grid yourself; the app reads the grid and
numbers, runs a bounded constraint search over your word lists, and lets you
accept letters one cell, word or mapping at a time.

![Codeword Workbench](docs/workspace-preview.png)

- **Grid recognition:** detects the main grid, cell numbers, black cells and
  picture areas in screenshots, photos and PDFs, with a straighten tool for
  tilted or curled magazine photos.
- **Solver:** indexed, cancellable constraint search with crossing and
  number-mapping propagation; tolerates names and other words missing from
  the dictionary.
- **Without a dictionary:** per-language letter-pattern models suggest likely
  letters and flag implausible words.
- **Honest output:** confirmed letters stay separate from suggestions, and
  every suggested word says what supports it.
- **Local-first:** a Python standard-library server on 127.0.0.1; no
  accounts, external services or CDN assets.

## Quick start

Requires Python 3.10 or newer.

```sh
python3 run.py
```

Open <http://127.0.0.1:8765>, choose **Try a small example**, then
**Solve puzzle**. Use `--port 8766` if the port is taken and
`--data-dir /path` to keep data elsewhere. On macOS, `start.command` starts
the server with a double-click.

Optional extras:

- **Screenshot and photo recognition:** `python3 -m pip install -r requirements.txt`
  (Pillow) and Tesseract with English data from your package manager
  (`brew install tesseract`, `sudo apt install tesseract-ocr`).
- **PDF import:** Poppler's `pdfinfo` and `pdftoppm`
  (`brew install poppler`, `sudo apt install poppler-utils`).

## Dictionaries

The app ships only small demonstration word lists. For real puzzles, import a
full list per language: [docs/dictionaries.md](docs/dictionaries.md) lists
free sources (Kotus, Joukahainen, OpenTaal, SALDO, Webster's) and the scripts
that convert them to the one-word-per-line import format.

## Documentation

- [User guide](docs/user-guide.md): every feature, search controls and limits.
- [Dictionaries](docs/dictionaries.md): sources, conversion, Finnish
  inflected forms, rebuilding the letter models.
- [Hosted mode](docs/railway.md): opt-in Docker/Railway deployment with a
  guest mode and a password-protected user mode.

## Project layout

- `app/server.py`: localhost API, schema checks, persistence and static assets.
- `app/solver.py`: validation and bounded constraint search.
- `app/dictionaries.py`: demonstration and custom vocabularies.
- `app/language_model.py`: character models, soft spelling rules and pattern
  checks; `app/models/` holds the bundled counts.
- `app/ocr.py`, `app/number_reader.py`, `app/straighten.py`: image
  validation, Tesseract adapter, digit consensus and photo flattening.
- `static/`: browser interface and pure state helpers; no build step.
- `scripts/`: dictionary conversion, model building and benchmarks.

User data (puzzles, dictionaries, autosave) lives under `data/`, which is
excluded from source control.

## Tests

```sh
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
```

OCR tests need Pillow; text-recognition tests skip without Tesseract. HTTP
tests use an ephemeral localhost port and a temporary data directory.

## Licence

MIT; see [LICENSE](LICENSE). The bundled letter models are derived from
third-party word lists under CC BY 4.0, Revised BSD / CC BY 3.0 and public
domain terms; credits are in [app/models/README.md](app/models/README.md).
Finnish vowel-harmony guidance follows
[Kielitoimiston ohjepankki](https://kielitoimistonohjepankki.fi/ohje/vierassanojen-taivutuspaatteen-vokaali/).
