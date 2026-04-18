# Repository Guidelines

## Agent Instructions (Claude)
When Claude is implementing tasks in this repo:
- Read [`Implementation.md`](/D:/Web%20Scraping/Implementation.md) before coding and align output to its phase goals.
- Treat this as a two-part system: `scraper/` (Python pipeline) and `frontend/` (React app); avoid mixing concerns across folders.
- Prefer small, reviewable commits/PRs that change one concern at a time (schema, scraper source adapter, UI feature, tests).
- Never hardcode site-specific brittle selectors without a fallback parser path and clear comments.
- If data schema changes, update extractor, normalizer, fixtures, and UI mapping in the same PR.
- For any scraping task, include rate-limit delays, retry/backoff, and explicit error handling for blocked/changed pages.

## Project Structure & Module Organization
This repository is currently planning-first and contains [`Implementation.md`](/D:/Web%20Scraping/Implementation.md). As implementation begins, keep a clear split between scraping and UI:
- `scraper/`: Python extraction pipeline (`collect.py`, `normalize.py`, `outputs/products.json`).
- `frontend/`: React + Vite app (`src/components`, `src/pages`, `src/assets`).
- `data/`: Optional shared snapshots and fixtures.
- `tests/`: Python tests (`tests/scraper`) and frontend tests (`frontend/src/__tests__`).

Keep generated files (`products.json`, logs, browser traces) out of source folders.

## Build, Test, and Development Commands
Use the commands below once the modules are scaffolded:
- `python -m venv .venv` then `.venv\Scripts\Activate.ps1`: create and activate local Python env.
- `pip install -r scraper/requirements.txt`: install scraper dependencies.
- `playwright install`: install browser binaries for JS-rendered pages.
- `python scraper/collect.py`: run scraping job and update `outputs/products.json`.
- `npm --prefix frontend install`: install frontend dependencies.
- `npm --prefix frontend run dev`: run local React app.
- `npm --prefix frontend run build`: production build output.
- `npm --prefix frontend test`: run frontend tests.

## Coding Style & Naming Conventions
- Python: 4-space indentation, `snake_case` for functions/files, `PascalCase` for classes.
- React: `PascalCase` component filenames (example: `ProductCard.jsx`), hooks in `camelCase`.
- Prefer small, single-purpose modules over large scripts.
- Formatters/linters (recommended): `black`, `ruff` for Python; `prettier`, `eslint` for frontend.

## Testing Guidelines
- Python: use `pytest`; name files `test_*.py`.
- Frontend: use Vitest + Testing Library; name tests `*.test.jsx`.
- Add at least one test for each parser, normalizer, and filter/sort behavior.
- Run all tests before opening a PR.
- Minimum gate before merge: scraper tests + frontend tests both pass locally.

## Commit & Pull Request Guidelines
Git history is not available in this workspace, so use Conventional Commits:
- `feat: add myntra product parser`
- `fix: handle missing price fields`

PRs should include:
- What changed and why.
- Data-impact notes (schema changes, new fields, removed fields).
- UI screenshots for frontend changes.
- Linked issue/ticket when applicable.
