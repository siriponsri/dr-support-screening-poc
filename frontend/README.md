# Frontend Foundation + Application Shell (v0.1 → v0.2)

React + Vite + Chakra UI + Lucide icons for the DR Support Screening POC UI.

**Two rounds landed:**

- **Round 1 (v0.1)** — design tokens, lucide icons, AppShell,
  FoundationDemo. No router, no real navigation.
- **Round 2 (v0.2)** — real router, five placeholder routes, collapsible
  sidebar, mobile drawer, page-aware header, honest runtime indicator,
  Vitest + Testing Library suite (14 tests).

The legacy `/ui/` static frontend in `../web/` is preserved during
migration. No model behaviour was changed.

## Stack

| Concern         | Choice                                       |
|-----------------|----------------------------------------------|
| Bundler / dev   | Vite 5 (TypeScript)                          |
| UI components   | Chakra UI v2.10 (`@chakra-ui/react`)         |
| Styling engine  | Emotion 11                                   |
| Icons           | `lucide-react`                               |
| Routing         | `react-router-dom` v6 (HashRouter)           |
| Testing         | Vitest + Testing Library + jsdom             |
| Type system     | TypeScript 5 (strict)                        |
| Type font       | Inter (`@fontsource/inter`)                  |

## Layout

```
frontend/
  index.html              Vite entry
  package.json            React 18 + Vite 5 + Chakra 2.10 + Lucide + Vitest
  tsconfig.json           strict TS, @/ alias → src/
  vite.config.ts          proxies /v1, /ui, /health → :8000; vitest config
  tests/
    setup.ts              matchMedia stub + fetch mock
    testUtils.tsx         renderAppAt(forceTier=...)
    shell.test.tsx        14 Vitest tests covering shell behaviour
  src/
    main.tsx              React root + Inter font injection
    App.tsx               HashRouter + ChakraProvider; AppCore for tests
    routes.tsx            /worklist /datasets /review /models /settings /_foundation
    hooks/
      useRuntimeHealth.ts probes /health, never claims healthy without backend
    theme/                raw palette + extendTheme (semantic tokens / variants)
    lib/
      icons.ts            single Lucide re-export module
    components/
      common/
        BrandMark.tsx     sidebar brand glyph
        Section.tsx       standardised panel card
        StatusBadge.tsx   typed status pill
        PageHeader.tsx    in-content page title/subtitle
        Placeholder.tsx   restrained "reserved" panel
      shell/
        AppShell.tsx      responsive grid: sidebar | topbar | main | footer
        AppHeader.tsx     page-aware title, runtime pill, collapse control
        Sidebar.tsx       collapsible nav + workspace card
        SidebarDrawer.tsx mobile drawer
        SidebarNavList.tsx accessible nav rows
        SidebarCollapseControl.tsx collapse/drawer trigger
        SidebarStateProvider.tsx collapse + drawer + tier context
        WorkspaceCard.tsx CURRENT WORKSPACE panel
        navItems.ts       canonical nav (Worklist, Datasets, Review, Models, Settings)
        routeMeta.ts      pathname → { title, subtitle }
    pages/
      FoundationDemo.tsx  Round 1 design-system preview (route: /_foundation)
      WorklistPage.tsx    placeholder
      DatasetsPage.tsx    placeholder
      ReviewPage.tsx      placeholder
      ModelsPage.tsx      placeholder
      SettingsPage.tsx    placeholder
      NotFoundPage.tsx    404 + recovery actions
```

## Theme tokens (semantic)

Surface / text / border / brand / status tokens are declared once in
`src/theme/index.ts`. The raw palette lives in `src/theme/colors.ts`.

| Role                | Token path                  | Hex     |
|---------------------|-----------------------------|---------|
| Brand anchor        | `brand.500`                 | #A73B24 |
| Brand dark / hover  | `brand.700`                 | #7C291A |
| Brand soft          | `brand.50`                  | #F4E5E0 |
| Warm accent         | (single `accent` / `accentSoft`) | #C99A45 |
| Canvas              | `surface.canvas`            | #FCFBFA |
| Panel               | `surface.panel`             | #FFFFFF |
| Ink                 | `text.primary`              | #202428 |
| Secondary text      | `text.secondary`            | #667085 |
| Border              | `border.subtle`             | #E5E7EB |
| Info                | `status.info`               | #2563EB |
| Success             | `status.success`            | #16865C |
| Warning             | `status.warning`            | #D97706 |
| Danger              | `status.danger`             | #B42318 |

Status tokens ship soft-tinted backgrounds and low-contrast borders for
subtle status pills.

## Breakpoints

Chakra's default breakpoints were replaced with the four-tier responsive
foundation used across the project:

| Name     | Range        | Use                |
|----------|--------------|--------------------|
| `base`   | < 768px      | Mobile (hamburger drawer, single-column) |
| `tablet` | 768–1023px   | Sidebar permanent, condensed (210px) |
| `laptop` | 1024–1279px  | Sidebar at 236px, full topbar |
| `desktop`| ≥ 1280px     | Sidebar at 256px, max-width content |

Mobile < `tablet` collapses the sidebar into a left-hand `Drawer` opened
via the topbar hamburger.

## Install & run

```bash
cd frontend
npm install

# Dev server (proxies /v1, /ui, /health to the FastAPI backend on :8000)
npm run dev           # opens http://127.0.0.1:5173

# Production build
npm run build         # outputs to frontend/dist/

# Preview the built bundle (no backend)
npm run preview       # http://127.0.0.1:5173

# Type check (no emit)
npm run typecheck
```

## Working with the backend (no coupling)

- In **dev**, Vite proxies `/v1`, `/ui`, and `/health` to
  `http://127.0.0.1:8000`. Start the FastAPI backend in another shell
  (`python -m dr_support.run`) before `npm run dev` if you want API calls
  to resolve.
- In **production**, the backend mount is unchanged — `app.mount('/ui',
  StaticFiles(directory=str(root / 'web')))` continues to serve the
  legacy worklist. The new build output (`frontend/dist/`) is currently
  served only as a standalone static bundle; mounting it under `/app/`
  is recommended for the next migration round (see "Recommended next
  step" below).

## Existing tests — no regression required

The frontend shell does not touch `web/`, `dr_support/`, or the
Python API. Existing tests must continue to pass:

```bash
# From repo root
npm test                     # overlay + api_hardening + ui + preview
pytest                       # 152 backend tests
ruff check dr_support tests  # all checks passed

# Inside frontend/
npm test                     # Round 2 Vitest suite (14 tests)
npm run typecheck            # tsc --noEmit, strict TS
npm run build                # vite build → dist/
```

## Round 2 shell behaviour

### Sidebar
- Two landmarked nav regions (`aria-label="Primary"`, `aria-label="Configuration"`)
  so screen readers and tests can scope queries.
- Brand mark · Worklist · Datasets · Review · Models & Audit · (divider)
  · CURRENT WORKSPACE · Settings · Public/synthetic only footer.
- Workspace card surfaces `April DR Screening · Color fundus photography · 12 cases · 3 reviewed`.
- Collapsed mode keeps the icons and shows tooltips with the label.
- Settings is separated visually with its own heading ("Configuration").

### Top bar
- Sticky, 60/64 px, white panel, single hairline border.
- Left: collapse/menu toggle, page title (h1), subtitle.
- Right: runtime pill that **never claims a healthy state without a
  successful `/health` round-trip** (`useRuntimeHealth` polls every 30 s,
  starts in `checking`, transitions to `online` / `warnings` / `offline`).
- Settings shortcut (icon button) shown only when the permanent sidebar
  is mounted *and* expanded.

### Main content layout
- `AppShell` exports `<Outlet/>` so the routed page renders inside a
  max-width 1440 px column with 16–28 px responsive padding.
- Footer disclaimer preserved verbatim from the legacy shell.

### Routes (Round 2 placeholders only)
- `/worklist`   clinician worklist — placeholder reserved
- `/datasets`   dataset workspace — placeholder reserved
- `/review`     case-review surface — placeholder reserved
- `/models`     provider readiness / audit — placeholder reserved
- `/settings`   preferences — placeholder reserved
- `/_foundation` debug: Round 1 design system preview
- `*`           404 (Recovery actions: Worklist, Datasets)
- `/` (index)   redirects to `/worklist`

No worklist / review / dataset data is migrated yet.

### Responsive behaviour
- `>= 1280px`  full sidebar (256 px), full top bar text.
- `1024–1279`  sidebar (236 px), full top bar text.
- `768–1023`   sidebar starts **collapsed** (64 px icon rail); user can
  expand via the icon button. Tables get the room they need.
- `< 768`      sidebar becomes a left-edge `Drawer`; header shows
  hamburger; secondary subtitle is hidden.

The same collapse control switches modes by using the active
`ViewportTier` from `SidebarStateProvider`. Tests pin the tier via
`forceTier` so the suite doesn't depend on jsdom's missing
`matchMedia`.

## Accessibility

- Visible red-soil focus ring on every interactive control.
- Sidebar collapse/menu trigger has an `aria-label` that reflects the
  action it will take (e.g. `"Expand sidebar"` vs `"Open navigation"`).
- Active route is exposed both visually and via `aria-current="page"` on
  the matching nav row.
- Mobile drawer traps focus, has a labelled `CloseButton`, and auto-closes
  on route change so it never lingers over the destination page.
- Tooltips surface the hidden label for icon-only collapsed rows.

## Migration safety

- `web/`, `dr_support/`, and `dr_support/api/_factory.py` are untouched.
- Existing FastAPI endpoints (`/v1/cases`, `/v1/models`, `/v1/infer/*`,
  `/v1/cases/*`) and the `/ui/` mount remain the production surfaces.
- The new bundle is shipped only via `frontend/dist/`; backend routing
  for it belongs to a later round.

## Recommended next step

Land the **Worklist route** on top of this shell:

1. Add a `useHealth`-backed data hook in `frontend/src/api/health.ts`
   that owns the runtime indicator (move it from the header provider).
2. Mount `frontend/dist/` under `/app/` from `dr_support/api/_factory.py`
   via a second `StaticFiles` mount, returning `index.html` for unknown
   paths (SPA fallback). Keep `/ui/` on the legacy worklist as a
   temporary escape hatch. The `/app/worklist` URL stays canonical.
3. Migrate `web/app.js` Worklist rows to a Chakra `Section` +
   `Table` driven by `/v1/cases`, reusing `StatusBadge`, runtime pill,
   and the page-aware top bar.
4. Then migrate the **Case Review** (image viewer + AI panel + action
   bar), keeping the existing legacy adapter boundary intact.
5. **Datasets** workspace: wire `April DR Screening` and friends into
   the real backend selection surface that already returns cases.
