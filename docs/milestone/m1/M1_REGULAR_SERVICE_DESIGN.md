# Regular service: design decisions and contracts

Status: Claude design record for the owner-approved regular service (owner
packet `docs/long-runs/20261031-local-app-real-api/`, README and
REGULAR_SERVICE_SPEC; kept as the owner's local files, not yet tracked).
It fixes the shared contracts before implementation depends on them. It grants
no credential, device, data or quota permission beyond the packet. Historical
finite ledgers, windows and routes stay closed and unchanged.

## 1. Topology

```text
user workstation (one per user)          dr-train (shared, DR account only)
review app 127.0.0.1:<port>/app/         control service 127.0.0.1:7860 (CPU, owned)
  own PostgreSQL workspace / batch    ->   authenticated gateway
  local batch runner (background)     SSH  daily authority (SQLite, one writer)
  backend-held token, never in React  tunnel  scheduler 1 running + 4 waiting
                                           owned GPU child 127.0.0.1:7861 (on demand)
                                             RETFound, USPEC, PRISM on RTX UUID only
```

- The control service owns port 7860, the daily authority and the scheduler.
  It runs on CPU and is the only path to the GPU child. The child is started
  only for funded work inside AI hours and stopped when idle.
- Model calls keep their existing routes and contracts (`/v1/predict/dr`,
  `/v1/prism-bound/*`). The control service forwards them to the child only
  after admission. No raw PRISM prediction route is added.
- Each review app keeps its own workspace and store. There is no shared,
  process-global multiuser web app.
- Route per workstation: the tested topology runs every app context on the
  owner's workstation, which already holds the DR route. Giving other
  workstations a route (gateway host, firewall, TLS) is a separate security
  action; the SSH key is never distributed.

## 2. Identity

The control service maps the bearer token to a principal through an
operator-only private file on dr-train (`token_sha256 -> principal_id,
workstation_ids, scopes`). Request JSON, headers or reviewer names never create
a principal. Jobs, holds, intents and audit rows carry the principal and the
workstation ID the principal is allowed to use.

Until separate per-user credentials are approved (a concrete security action),
only the existing backend principal exists. Several app contexts then share
that principal: per-workstation fairness and attribution use a declared
workstation ID that is **not** authenticated. This is reported as a limitation,
and live multiuser acceptance stays BLOCKED until per-user principals exist.

## 3. Daily authority

One SQLite database on dr-train, written only by the control service
(`BEGIN IMMEDIATE`, `synchronous=FULL`, WAL). It is a new lineage: its first row
records the hashes of the closed historical service journal, head and
COMPLETE receipt, and the configuration digest. Nothing in an old accounting
directory is read for allowance or written.

| Approved constant | Value |
| --- | --- |
| Admitted model invocations per Thai day | 1500 |
| GPU reservation seconds per Thai day | 43200 |
| Calendar | Asia/Bangkok, 00:00 inclusive to next 00:00 exclusive |
| AI hours | 06:00 inclusive to 22:00 exclusive |
| Device | RTX `GPU-044a8b11-4729-458b-a07b-297e45439419` only |

Rows: `authority`, `clock_highwater`, `holds`, `intents`, `gpu_segments`,
`events` (hash-chained audit). Day usage is derived from immutable intent rows.

- **Pair hold.** Before an image's grader stage is scheduled, two slots are held
  on the current day. Each stage converts one hold to an intent exactly once,
  durably, before the call is forwarded. A hold is released only when its stage
  is proven never forwarded (cancel before admission, stale plan). An intent is
  never refunded, including failed, persistence-error and unknown outcomes.
- **Midnight.** An intent stays on its admission day. An unconsumed hold is
  valid only on its day; the next day needs a new hold before dispatch. No
  borrowing across days.
- **Idempotency.** `(principal, idempotency_key)` with the request digest:
  same key and digest returns the existing ticket or intent; a different digest
  is refused. A new explicit attempt needs a new key and is charged once.
- **Clock.** UTC high-water and boot/monotonic origin are stored. Rollback,
  incompatible origin, an unexplained forward jump or a damaged chain stops new
  AI admission (fail closed) until reconciled. The OS clock is never changed.

## 4. Scheduler

- At most 5 active stages: 1 executing and 4 waiting; at most 1 outstanding
  stage per workstation; round-robin over workstations with waiting work.
- A ticket moves `QUEUED -> READY` when it gets a slot. READY opens a bounded
  dispatch window (the client must send the call within 60 s) and keeps the
  slot. The client then uses the existing protocol for that stage. The call
  carries `X-DR-Ticket`; the control service checks principal, workstation,
  model, modality and source digest against the ticket, converts the hold to
  an intent, then forwards.
- Ticket states: `QUEUED`, `READY`, `ADMITTED`, `DONE`, `FAILED`, `UNKNOWN`,
  `CANCELLED`, `EXPIRED`. Cancel before admission releases the hold. After
  admission, cancel is not proof of anything and changes no accounting.
- Queue wait, upload, prepare, execution and readback have separate bounds. The
  native 30 s request limit and PRISM sub-deadlines are unchanged.

## 5. GPU lifecycle

- The child starts only when a READY ticket needs it, inside AI hours, with
  budget. Before start, and before each further segment, the control service
  funds a non-overlapping 300 s segment against the day's 43200 s. A segment
  is charged in full; three models resident together share it (one charge).
- Idle: when no ticket is READY or waiting for 300 s, the child is stopped at
  most at the end of its funded segment and cleanup is confirmed.
- Healthy retirement after the existing child limits (42 jobs or 2700 s) is a
  normal stop under the new authority, followed by a newly funded child.
- Unknown cleanup keeps the segment charged and quarantines new GPU work until
  owned terminal proof. No PID guessing or TTL unlock.
- A segment crossing Thai midnight is split and funded on both days, or not
  started. New admission stops at 21:55 so funded work drains before 22:00.
- Existing ceilings stay: one child, GPU concurrency 1, VRAM 10240 MiB,
  RSS 24 GiB, project 40 GiB, CPU threads 2, 0-forward load, pinned
  environments.

## 6. Review app batch

- **Amended 2026-10-31 (implementation):** no schema migration. A batch is one
  JSON file per batch in the app's private local state
  (`M1PrivateConfig\regular-batches\<workspace_id>\`), replaced atomically. This
  avoids changing the M1 database, its roles and its entry fence, and adds no
  case revisions while clinicians work. The ticket queue itself is durable on
  the host authority; the app keeps one outstanding ticket at a time.
- Per item: grader stage state (`PENDING`, `RUNNING`, `SAVED`, `NEEDS_ACTION`,
  `NEEDS_CONFIRM_IMAGE`, `CANCELLED`); the PRISM stage is derived from the saved
  case (PRISM result present or waiting for Review). Analysis complete and
  clinician review complete stay separate.
- A stage refused by the queue before sending (outside AI hours, daily limit,
  queue wait) stays waiting and is tried later. Any other failure, and a stage
  interrupted while it may have been sent, needs action: never resent
  automatically.
- **Grader stages** run in the background for every item whose image type is
  resolved and eligible. Items without a resolved type show "needs Confirm
  Image".
- **PRISM stages** keep the existing preview, one-use receipt and the
  clinician's input acknowledgement. The runner never submits a PRISM stage
  without that acknowledgement. Because the receipt and host ticket last at
  most 300 s, the PRISM stage is armed when the clinician acknowledges the
  input in Review and is then scheduled; if it expires in the queue it returns
  to "needs action" (prepare again), never regenerated silently.
- Results go through the existing validation, raw history and save path, then a
  trusted readback before the stage is marked saved. A later AI result never
  changes the clinician's grade or findings.

## 7. Wire contract (control service, 2026-10-31)

All routes need the existing backend bearer token. `/v1/regular/*` and charged
calls also need `X-DR-Workstation` (`[A-Za-z0-9_.:-]{1,120}`, not
authenticated while only the shared principal exists).

| Route | Purpose |
| --- | --- |
| `GET /v1/regular/status` | Day, AI hours, invocations and GPU seconds used/held/available, queue counts, model server state (`STOPPED`, `STARTING`, `READY`, `STOPPING`, `UNCONFIRMED`), live child epoch, own open tickets only |
| `POST /v1/regular/tickets` | `{idempotency_key, request_digest, kind: grader or prism, model_id, modality, source_sha256, pair_key}`; same key and digest returns the same ticket |
| `GET /v1/regular/tickets/{id}`, `POST .../cancel` | Own workstation only; cancel after admission is refused |
| `POST /v1/regular/images/release` | Give back an image's unused slots |
| `POST /v1/regular/warm` | Keep or start the child for 300 s (PRISM preparation) |
| `GET /health`, `GET /v1/models` | Live from the child, or the last loaded child's copy with an on-demand warning |
| `POST /v1/predict/dr`, `POST /v1/prism-bound/execute` | Charged; need `X-DR-Ticket` of a READY ticket of the same stage, model, modality and source digest |
| other `/v1/prism-bound/*` | Uncharged control routes, only while the child is READY |

`source_sha256` is what the stage sends (grader: analysis bytes; PRISM: the
bound source). `pair_key` is the admitted image's content SHA-256 for both
stages. Refusals carry a fixed `code`; the review app turns them into plain
wording that says nothing was sent.

## 8. What this does not claim

No clinical accuracy, no continuous 16 h readiness, no 500-image/day
throughput until measured, no live multiuser acceptance without per-user
principals, and no guard-aware recovery.
