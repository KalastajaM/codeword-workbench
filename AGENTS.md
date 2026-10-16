# Codeword Workbench

Guidance for coding assistants and contributors.

- A local-first browser application for codeword puzzles. The user guide
  (`docs/user-guide.md`) describes the intended behaviour; keep it current
  when behaviour changes.
- Work in English. Each cell holds exactly one letter.
- Keep confirmed letters separate from provisional suggestions; never confirm
  a suggestion without an explicit user action.
- Do not present heuristic candidates as verified words or searches as
  exhaustive.
- `static/how-it-works.html` explains the solver to users. When solver
  behaviour, limits or validation change, update that page and its search
  port (`static/how-it-works-engine.js`) together with the user guide.
  `tests/test_how_it_works.py` checks every figure the page states and runs
  the port against `app/solver.py`; tag new figures with `data-fact`.
- No external services or CDN assets. Local mode stays bound to localhost;
  hosted mode must be explicitly configured with an HTTPS origin and an
  explicit access policy (`docs/railway.md`).
- Keep user data, word lists and credentials in `data/` and out of source
  control. Do not commit third-party word lists; document how to obtain them
  in `docs/dictionaries.md`.
- Before reporting completion, run:

  ```sh
  python3 -m unittest discover -s tests
  node --test tests/*.cjs
  ```

- Trunk is `main`; use short-lived feature branches and never force-push.
