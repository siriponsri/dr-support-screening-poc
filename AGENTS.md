# Repository Guidelines

## Project Structure

- `dr_support/` contains the Python/FastAPI backend. Keep profile dispatch in `app.py`, API surfaces under `api/`, deployment services under `services/`, model adapters under `providers/`, and shared schemas under `contracts/`.
- `web/` is the legacy static UI; `frontend/` is the React/Vite migration (`frontend/src/` for application code and `frontend/tests/` for Vitest tests).
- `tests/` contains backend pytest, API, browser, and root UI smoke tests. `docs/` holds runbooks and architecture/deployment notes; `examples/` contains public sample manifests.
- `local-state/` is runtime state and must not be treated as source data. Use `.env.example` as the configuration reference.

## Build, Test, and Development

From the repository root:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m ruff check dr_support tests
python -m dr_support.run
npm ci && npm test
```

The Python command starts the local API; `START.cmd` is the Windows shortcut. Root `npm test` runs the legacy overlay, API-hardening, UI, and preview smoke tests. For the React app:

```bash
cd frontend
npm ci
npm run dev       # Vite development server
npm run build
npm run typecheck
npm test
```

## Coding Style and Naming

Use four spaces in Python and the existing 110-character Ruff limit. Follow PEP 8 naming (`snake_case` functions/modules, `PascalCase` classes). TypeScript is strict: use `PascalCase` React components, `camelCase` variables/functions, and `useX` names for hooks. Prefer existing contracts, profile boundaries, theme tokens, and Lucide icons over new parallel abstractions.

## Testing Guidelines

Name Python tests `test_*.py`, root Node tests `*.test.cjs`, and frontend tests `*.test.tsx`. Backend tests are offline by design and use disposable SQLite state; do not add network-dependent tests. Run the focused suite while iterating, then run the full commands above. Browser smoke tests are optional: `python -m pytest -q tests/test_browser_ui.py`.

## Commits and Pull Requests

Use the established Conventional Commit style, such as `feat(remote): ...`, `fix(review): ...`, `docs: ...`, or `refactor: ...`. Keep commits focused. PRs should describe behavior and affected profile/UI, link the relevant issue or plan, list validation commands, and include screenshots for frontend changes. Call out new environment variables, model/runtime requirements, or security implications.

## Security and Configuration

This is a public/synthetic research POC, not an autonomous diagnostic system. Never commit tokens, model weights, or private patient data. Keep CVAT credentials server-side, use environment variables, and follow `docs/LOCAL_RUNBOOK.md` before exposing the API beyond localhost.
