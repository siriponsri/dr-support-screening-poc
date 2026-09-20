# S2 Workspace Manager Contract

Status: frozen orchestration contract for S2 backend and frontend work.

This contract adds local workspace selection around the existing review
workstation. It does not change inference, model providers, admitted-image
semantics, CVAT behavior, annotation payloads, clinician-review semantics, or
the S1 viewer.

## Workspace profile

The profile is the durable local identity for one review workspace:

```json
{
  "id": "ws_01J...",
  "name": "April DR Screening",
  "input_folder": "C:\\Data\\April-DR\\input",
  "output_folder": "C:\\Data\\April-DR\\output",
  "database_path": "C:\\Data\\April-DR\\review.sqlite",
  "note": "Mobile screening unit - Sept 2026",
  "created_at": "2026-09-20T05:00:00+00:00",
  "updated_at": "2026-09-20T05:00:00+00:00",
  "last_opened": "2026-09-20T05:00:00+00:00"
}
```

Rules:

- `id` is an opaque server-generated stable identifier.
- `name` is required, trimmed, and limited to 120 characters.
- `input_folder` and `output_folder` are required absolute local directory
  paths. They are configuration/context only in S2; image ingestion is not
  added by this milestone.
- `database_path` is a required absolute local SQLite file path. The save
  operation creates/initializes the file when it does not exist and preserves
  existing case data when it does.
- Timestamps are UTC RFC 3339 strings. `created_at` is immutable;
  `updated_at` changes on profile edits; `last_opened` changes on activation
  and may be `null` before the first activation.
- Paths remain local values. They are never sent to a model service or cloud
  database.

- `note` is optional, trimmed, and limited to 500 characters. An empty note is
  represented as `null`; legacy profiles without the field remain readable.

## Persistence and startup

- Workspace profiles and the active/last-opened selection live in a local
  catalog SQLite database. Its path is `DR_SUPPORT_WORKSPACE_CATALOG` when set,
  otherwise `local-state/bridge/workspaces.sqlite`.
- A profile's `database_path` is the existing `Store` database for cases,
  review history, annotations, and CVAT task state. The catalog is not the
  active review database.
- On review-app startup, active database precedence is:
  1. an explicit `create_app(state_path=...)` argument (legacy/tests);
  2. the last-opened profile whose database can be opened;
  3. `DR_SUPPORT_STATE`;
  4. `local-state/bridge/reviews.sqlite`.
- The legacy `dr_support.api:app` factory and `DR_SUPPORT_STATE` behavior stay
  valid. Opening a workspace changes the in-process active store without
  editing environment variables. On restart, the last-opened profile is
  restored automatically.
- A missing/unreadable last-opened profile or database does not discard the
  profile or prevent the review app from serving the fallback store. The
  active-workspace response reports a warning and the UI provides a recovery
  action.
- Only one local runtime worker/process should use a given review database,
  preserving the existing SQLite invariant.

## API surface

All endpoints are on the review app and use the existing same-origin mutation
guard. Dates and paths use the JSON representations above.

### List and inspect

`GET /v1/workspaces` returns:

```json
{
  "workspaces": [/* WorkspaceProfile[] */],
  "active_workspace_id": "ws_01J...",
  "active_workspace": {/* WorkspaceProfile */},
  "warnings": []
}
```

`GET /v1/workspaces/active` returns:

```json
{
  "workspace": {/* WorkspaceProfile */},
  "database": {"path": "C:\\Data\\April-DR\\review.sqlite", "status": "ready"},
  "warnings": []
}
```

`workspace` may be `null`; `database.status` is one of `ready`, `fallback`,
or `unavailable`. A fallback response includes a human-readable warning and
does not claim that a workspace is active when it is not.

The workspace manager UI shows the active workspace note below its name when
present. The shell sidebar shows only the active workspace name, optional note,
and a `Manage workspace` link; local folder and database paths remain in
Settings.

### Save and open

`POST /v1/workspaces` creates and activates a profile. Request:

```json
{
  "name": "April DR Screening",
  "input_folder": "C:\\Data\\April-DR\\input",
  "output_folder": "C:\\Data\\April-DR\\output",
  "database_path": "C:\\Data\\April-DR\\review.sqlite",
  "note": "Mobile screening unit - Sept 2026"
}
```

`note` is optional, is limited to 500 characters, and is returned on every
`WorkspaceProfile` response. Whitespace-only notes are normalized to `null`.
Existing catalog rows without a note remain valid and read as `null`. Create
and update requests may set, replace, or clear the note.

`PUT /v1/workspaces/{id}` accepts the same fields and updates the existing
profile. It activates the profile after a successful database open.

Both endpoints return:

```json
{"workspace": {/* WorkspaceProfile */}, "active": true, "warnings": []}
```

`POST /v1/workspaces/{id}/open` activates an existing profile and returns the
same response shape. The database is opened before the active pointer changes;
on failure, the previous active store remains in use.

`DELETE /v1/workspaces/{id}` removes an inactive profile from the workspace
catalog and returns:

```json
{"deleted": true, "workspace_id": "ws_01J...", "warnings": []}
```

Deletion removes only the catalog profile. It never deletes or changes the
profile's input folder, output folder, retinal images, SQLite review database,
or model result/data files. The active profile cannot be deleted and returns
HTTP 409; the client must switch to another workspace first. Unknown profiles
return HTTP 404. A failed deletion leaves the active workspace and store
unchanged.

### Native pickers

The browser never supplies a fake path and `webkitdirectory` is not the primary
workflow. The local FastAPI process owns native dialogs.

`POST /v1/workspaces/pickers/folder` request:

```json
{"purpose": "input", "initial_path": "C:\\Data"}
```

`purpose` is `input` or `output`. `POST /v1/workspaces/pickers/database`
request:

```json
{
  "mode": "open",
  "initial_path": "C:\\Data",
  "suggested_name": "review.sqlite"
}
```

`mode` is `open` or `create`. Both endpoints return:

```json
{
  "status": "selected",
  "path": "C:\\Data\\April-DR\\review.sqlite",
  "code": null,
  "message": null
}
```

`status` is `selected`, `cancelled`, or `unavailable`. Cancellation is a
normal non-error result and leaves the form unchanged. A headless/non-Windows
environment returns `unavailable` with a recovery message; it must not invent
a browser path. A `create` selection is initialized only when the profile is
saved.

## Errors and degraded behavior

- Invalid profile fields or non-local paths: HTTP 422 with FastAPI `detail`.
- Unknown profile: HTTP 404.
- Database parent missing, inaccessible, or not a usable SQLite file: HTTP
  409/503 with `detail`; the previous active workspace/store remains active.
- Native dialog unavailable: HTTP 200 with `status: "unavailable"` for a
  picker operation, so cancellation and capability degradation are distinct.
- Catalog read/write failure: the review API falls back to the legacy store
  and reports a warning from the workspace endpoints; it must not silently
  overwrite the catalog or review database.

## Ownership boundary

Backend owns the catalog/profile schema, SQLite persistence, active-store
switching, startup fallback, native picker boundary, and backend tests.

Frontend owns Settings/Workspace Manager presentation, path fields, browse and
save/open interactions, active shell context, responsive/accessibility states,
and frontend tests. It consumes only this contract and does not access the
filesystem directly.

Integration owns this contract document, merge review, and post-merge
regression validation. Neither implementation branch edits `DESIGN.md`, S1
viewer code, model/provider code, or legacy `/ui/` behavior.
