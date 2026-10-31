# Phase 1 program specification (normative)

Status: owner-directed, 31 October 2026. Source plan:
[PHASE1_ALL_IN_ONE_PLAN_20261031.md](../../planning/PHASE1_ALL_IN_ONE_PLAN_20261031.md).
Screening and research support only; not a diagnostic device. Every model
output stays a suggestion; the person's grade is authoritative.

## 1. Owner decisions recorded (chat, 31 October 2026)

| # | Decision (owner's words, Thai) | Effect |
| --- | --- | --- |
| D1 | "ในขั้นแรกยังไม่ต้องทำระบบส่งต่อครับ ออกมาแค่เป็น report pdf ได้ก่อนครับ และรายงานว่า refer, not-refer" | Phase 1 makes a PDF report with a Refer / Not refer field chosen by the person who grades. This amends the earlier rule that the Workbench stores no hospital Refer/Not-refer label: the field is stored only as part of the screening report, labelled as the grader's decision. No automatic referral rule is added; `M1_DR_GRADE_4_REFERRAL` is unchanged. |
| D2 | Report form approved ("ผ่านครับ"), no logo, formal light KKU Faculty of Medicine green | The report follows the reviewed A4 form (artifact `6MsbQJ9J1NFdGzytrRkUMD`, version 4). |
| D3 | Inputs: both new patients and archive folders; modes 1 and 2 combined | One screening work area with two entry points. |
| D4 | Images may not leave the hospital except consented images; dr-train is for development and emergencies | dr-train mode is allowed only for workspaces whose images are public or consented (section 5). |
| D5 | "Vein" means vessel segmentation | Phase 2; not in this program. |
| D6 | Two Docker packages (web app; hospital local server) and a one-click start of the dr-train server with warm-up; server mode chosen in the admin page | Sections 4 and 5. |
| D7 | Web app English by default with an EN/TH switch; headings and technical terms stay English; Thai text reviewed with the `thai-natural-writing` skill | Section 3.2. |
| D8 | The ophthalmologist selects the Gold-100 images; the program must be respectful | Section 3.5. |
| D9 | Regular Model API budget may be extended; this is a development period | No authority config change unless needed; a change needs a new authority record. |

## 2. Unchanged safety rules

- Original images are never moved, renamed, rewritten or deleted; outputs are copies.
- An empty AI result or an empty human set means "reviewed", not "no lesions".
- AI scores are not calibrated probabilities and are never shown as such.
- An ungradable image is never reported or filed as normal.
- AI-predicted grade folders are named and labelled as unverified and never count
  as clinical grades or training labels.
- Model identities, pins and remote inference contracts are not changed.
- No secrets, tokens, patient data, weights or databases in Git, logs, chat or
  the browser.

## 3. Web app features

### 3.1 Roles

`admin`, `physician`, `nurse`, `expert`, `researcher` (existing `user` maps to
`physician`). Every change records the signed-in user and role.

| Action | nurse | physician | expert | researcher | admin |
| --- | --- | --- | --- | --- | --- |
| Import, run AI, grade | yes (preliminary) | yes | yes | no | no |
| Confirm a grade, sign a report | no | yes | yes | no | no |
| Sort an archive, export folders | no | yes | yes | no | no |
| Gold-100 labelling | no | no | yes | no | no |
| Research exports | no | no | yes | yes | no |
| Accounts, policy, server mode, database view | no | no | no | no | yes |

A nurse's grade is shown as "Preliminary, waiting for physician confirmation"
until a physician confirms it; the report shows both names.

### 3.2 Language

English by default; a per-user EN/TH switch. In Thai, headings and technical
terms (DR grade, ICDR, NPDR, PDR, DME, ROI, Refer, PRISM, Confirm Image) stay
English. No middle dot or em dash in UI text.

### 3.3 Screening work area

Entry A, new patient: import one patient's images, confirm image type, AI
suggestion, grade per eye, report.
Entry B, archive: choose a folder, batch AI, grade folders as copies:
`ai_predicted_unverified/{grade_0..4,ungradable,low_confidence}/` and
`confirmed/{grade_0..4,ungradable}/`, each with a CSV manifest.

### 3.4 Screening report (PDF)

Fields as in the approved form: patient and exam, per-eye quality, ICDR grade,
suspected DME (confirm with OCT), signs, previous laser, other findings, AI
suggestion box (model, grades, agreed or changed), screening result based on
the worse eye (Not refer with rescreen interval; Refer with destination and
urgency), ungradable handling, graded by (name, role), confirmed by physician,
disclaimer and references. The Refer / Not refer choice is the grader's; the app
does not pre-select it.

### 3.5 Gold-100 research labelling

- The expert grades before any AI suggestion is visible; then may view the AI
  suggestion and change the grade; both grades are kept.
- Fields: ICDR grade, gradable, main quality issue, laterality, confidence (sure
  or unsure), signs per quadrant (superior, inferior, nasal, temporal:
  haemorrhages, venous beading, IRMA, new vessels, hard exudates near the fovea),
  suspected DME, time spent (automatic), selection reason (typical, hard, severe,
  rare).
- Wording: "Your grade is the reference"; "AI suggestion (optional)"; only grade
  and gradability are required; no "AI disagrees" messages.
- Gold labels are stored apart from screening grades and exported with
  provenance (`clinician_verified`, `model_suggestion`).

## 4. Server packages

### 4.1 One-click dr-train start (demo, development, emergencies)

One command on the owner's workstation: checks the SSH route (existing key,
strict host key), starts the regular gateway on dr-train if it is not running
(current deployment), waits for it, starts the local review app, which warms the
GPU child, and opens the browser. Inside AI hours only (06:00 to 22:00 Thai)
unless the authority is reconfigured with a new record. Never prints a token.

### 4.2 Docker package 1: web app

Images: `web` (FastAPI app with the built frontend, review profile, remote model
runtime) and `postgres`. Model server reached by URL. Sign-in required. Data on
host folders. Runs on Linux with Docker Engine.

### 4.3 Docker package 2: hospital local server

Package 1 plus `model-api` (GPU, `APP_PROFILE=model_api`, `MODEL_RUNTIME=local`)
on the hospital network, weights mounted read-only and checked against pinned
hashes at start, plus an internal HTTPS front (`caddy`, internal certificate).
Offline install from saved image files, nightly database backup, rollback by
image tag. No internet needed in normal operation.

## 5. Server mode (admin page)

| Mode | Model server | Allowed images |
| --- | --- | --- |
| Hospital local | the hospital `model-api` | all admitted images |
| Team server (dr-train) | the regular gateway through the SSH route | only workspaces whose images are public or consented; anything else is refused before sending |

The admin chooses the mode; it applies at the next app start. The page shows the
current mode, the model server's health and, for dr-train, the daily calls and
GPU-seconds left.

## 6. Acceptance

Each part lands on its own branch with focused tests, then full backend and
frontend suites before merge, `frontend/dist` rebuilt on main, and a browser
check with public or consented images. Docker images build locally and the web
package starts and serves sign-in; the GPU service of package 2 needs a Linux GPU
host where the account may run Docker (not available on dr-train without an
administrator), which is reported as not run until then.

## 7. Deferred

Automatic referral suggestions (need the signed table), vessel segmentation and
model training (phase 2), DME diagnosis, hospital login integration.
