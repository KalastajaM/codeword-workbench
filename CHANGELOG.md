# Changelog

Versions follow [semantic versioning](https://semver.org/). The version
number is in `app/__init__.py`; `python3 run.py --version` prints it.

## 1.0.0 (2026-10-17)

First release. Everything below is described in full in the
[user guide](docs/user-guide.md).

### Import and recognition

- Import a screenshot, photo or PDF of a codeword puzzle, or draw the grid by
  hand. The app finds the main grid, cell numbers, black cells, shaded cells
  and picture areas, with numbers it may have misread marked for review.
- **Straighten photo** finds the printed border of a tilted or curled page,
  with extra edge points for curved spines, and follows wavy grid lines cell
  by cell.
- Image import, recognition and straightening run in a progress window that
  can be cancelled without changing the workspace.

### Solving

- Indexed, cancellable constraint search with crossing and number-mapping
  propagation, tolerant of names and other words missing from the
  dictionary.
- Without a dictionary, per-language letter-pattern models for English,
  Finnish, Dutch and Swedish score whole number-to-letter mappings. Deep
  search solved full-size printed puzzles in testing; this is not a
  guarantee for every grid.
- Live best guess during the search, shaded by how clearly each letter beats
  its best rival, also after dictionary searches; a replay with a score chart
  shows how the grid settled.
- Confirmed letters stay separate from suggestions. Rule out letters,
  look up words, find candidates for selected words and review suggested
  eliminations before confirming anything.

### Making puzzles

- Generate a codeword from a drawn grid and your word list, with Easy,
  Medium or Hard difficulty, words to include and an optional check that
  only one answer fits within that dictionary.
- **Place black cells** lays out a grid for a target number of words and
  word lengths, with mirrored black cells by default.
- Solve generated puzzles in the app with an answer check, or print them
  with their number key and solution.

### Workspace

- Local-first Python standard-library server bound to 127.0.0.1, with
  autosave, saved puzzles, JSON import and export and custom dictionaries
  under `data/`.
- Optional hosted mode (Docker or Railway) with an explicit HTTPS origin,
  a guest mode and a password-protected user mode.
- Guided **Watch it solve** demo, sample printed page and an in-app
  **How it works** walkthrough of the solver.
