# Local workflow timing and later user benchmarking

Engineering instrumentation, not clinical UAT or a clinician speed measurement.
Settings → Local workflow timing enables a bounded memory-only recorder for this
tab. It is off by default and uses no localStorage, analytics endpoint or background
upload. Download local timing JSON explicitly saves observations on the operator's
computer; Clear discards them and retires pending callbacks. Closing/reloading the
tab loses observations. No server, DB migration or model request is added.

## Measurement boundaries

All within-tab durations use performance.now. UTC generated_at is correlation only;
never subtract a browser clock from a model-host clock. A route commit begins a
case flow, not the preceding click or network navigation. Related Review and
Clinician Review pages keep that flow; another case or Workspace retires it.
Leaving before confirmed save is INCOMPLETE, never a completed zero-duration case.

| Observation | Start / endpoint | Meaning and limits |
|---|---|---|
| case_to_confirmed_save | Case route commit / successful current CONFIRMED grade response committed | Observed elapsed flow; clinical role, correctness and human thought not certified. Ungradable/second-review saves are separate request observations and do not falsely close a confirmed numeric-grade flow. |
| annotation_to_confirmed_save | Editor route commit / current annotation confirmation | Separate from grading; does not imply every clinical/UAT or training eligibility gate has passed. |
| case_load | Case request start / parsed response or error | Browser HTTP-plus-response-processing wait; no assumption about DB/server subdivisions. |
| image_load | Case/editor route commit / main image onLoad or onError | Image load completion; no guarantee about first compositor paint, zoom work or a clinical image-quality decision. |
| preview_prepare | Preview API start / parsed response | Receipt preparation response, not visible image readiness. |
| preview_assets + preview_ready | Asset verification start / both original and planned-input image onLoad | Verification, decode and mounted image readiness; candidate remains conditional and native ROI stays NOT_RUN. Closing/changing preview can abort this observation. |
| global_submit / lesion_submit / prism_submit | Existing request start / parsed response or error | Client round trip. It includes network, queue, preprocessing, model/proxy and response overhead where present; it is not pure inference time. |
| result_render_commit | Current result-bearing case committed to React | A point event; not a new model run or measured compositor paint. Existing persisted results can also produce it. |
| review_edit | Grade/remark edit or committed annotation edit | Event count only; no selected grade, text, label or geometry is recorded. Not all UI inputs are corrections. |
| review_save / annotation_save | Existing save request / parsed response | Successful HTTP observation alone does not establish current clinical confirmation; explicit committed confirmation events close flows. |
| grading_folder_preview | Existing read-only preview / accepted result or failure | Separate from copying. |
| grading_folder_snapshot | Existing bound copy request / verified current response or failure | Client-observed completion only. Abort/timeout does not prove the server stopped or that no files were created; inspect the existing snapshot receipt before a deliberate retry. |

Human review time is **unknown (null)**. active_observation_ms is a proxy: focused,
visible tab time within30seconds of pointerdown, keydown or wheel. Event contents
and keys are never retained. Remaining foreground time is foreground_idle_ms;
hidden/unfocused time is background_ms. These three partition observed flow time,
but active time can include reading or waiting. System spans overlap activity
classification; do not add them to active/idle totals or call the difference
"physician thinking time". Long reading can fall outside the activity window.

## Exportable schema: local-ux-timing.v1

The implementation contract is frontend/src/lib/localTiming.ts. Download contains:

- opaque_session_id; generated_at; clock and active-window definition; bounded
  capacity/drop counters; clinical_user_benchmark_verified=false.
- flows: generated id, fixed name, monotonic started_ms/ended_ms, outcome or null,
  active/idle/background totals, human_review_ms=null, modality CFP/UWF/UNKNOWN,
  operator-classified cohort/environment/load phase. No original case/Workspace
  identifier is serialized; runtime routing keys are discarded when the flow retires.
- entries: fixed event/step name, generated flow/step IDs, started_ms, at_ms,
  duration_ms and outcome for finished spans. Failure codes are coarse fixed values;
  exception text, paths, HTTP bodies and patient data are excluded. Retired pending
  spans are ABORTED; a later callback can record late_response_ignored against the
  original flow without crediting the new case.
- pending: explicit UNFINISHED spans, never silently represented as completed0ms.
- step_summary / flow_summary: n, completed_n, failed_n, aborted_n, stale_n,
  incomplete_n, completed-only mean/median, and nearest-rank p95 only with n>=20.
  Even then p95 is descriptive only. Groups separate operation, flow, cohort,
  environment, phase, modality and available model identity/revision.
  comparison_qualified=false: arithmetic does not validate a benchmark protocol.

Only the four known model IDs are retained, with hash-form revisions where supplied;
unrecognized IDs/free-text versions are null. Bodies are never parsed for telemetry.
Hardware, checkpoint/config hashes, pure network time and other unsupported fields
remain null. queue_ms/preprocessing_ms/inference_ms accept only fixed Server-Timing
durations if explicitly returned. The current app does not provide these headers,
so they remain null. No reported_model/proxy latency is guessed from total wait or
an unrelated historical record. Boundaries can overlap; never subtract reported
stages blindly. No new backend instrumentation or remote transport is introduced.

Capacity is200flows,4000entries and1000pending spans. dropped>0 means an incomplete
diagnostic sample: retain that fact, do not present its summary as a complete study.
Completed system spans can belong to incomplete case flows; report their populations
separately. The recorder retains failures/retries rather than removing slower runs.
Synthetic clocks in regression tests prove ordering/arithmetic only, not latency.

## Later supervised benchmark protocol (NOT_RUN)

1. IT records a separate approved study sheet with app build, browser/OS, CPU/RAM,
   storage, network route, model/config/checkpoint identities and actual hardware.
   Exclude patient and staff names from timing JSON. Have the Workspace fully ready
   before enabling collection. Do not infer consent or clinician privileges from
   an operator selecting the observed-user cohort.
2. Define each endpoint above, image/modality mix, screening versus detailed
   annotation task, first-use versus experienced participants, completion criteria,
   interruptions and stop rules before observing. Keep clinical correctness/UAT
   evaluation separate; no automatic confirmation is added by measurement.
3. Enable diagnostics and select the actual cohort/environment. Cold/Warm labels
   are operator classifications, not verified warmup. If unverified, keep UNKNOWN.
   Run a supervised familiarization flow separately; never label scripted fixtures
   as physician observations. No new inference budget is granted by recording.
4. Observe actual authorized users; record assistance/interruption categories in
   the study sheet without PHI. Export before closing the tab. Failed, aborted,
   incomplete, repeated and unfinished flows remain in the denominator accounting.
   Do not select only successful/fast cases or replace missing data with zeros.
5. Check dropped=0, event sequences and endpoint eligibility. Report participant
   and case sample counts separately; repeated cases/users are not independent.
   Use completed observations for mean/median, with failure/completion rates beside
   them. Do not compare unknown model versions or mixed protocols. Treat p95 from
   small samples as insufficient even if an arithmetic value could be calculated.
6. For QA versus Lightning, join only at matched timing boundaries and verified
   protocol/model/modality/environment strata, using a restricted non-PHI study
   mapping outside this diagnostic export if required. Existing main-lane
   QA_LIGHTNING_PER_CASE_PARAMETERS_AND_TIMING_V2_20261021.json contains42 prior
   outputs, standard/research strata and after-preload measurements; it is not a
   fresh UX benchmark. Keep those model/proxy waits separate from full browser
   round trips and human elapsed flow. No Lightning hardware/cold-load figures,
   new endpoint availability or speedup claim is manufactured here.

Current clinical-user mean, median, p95 and participant count: **NOT_MEASURED**.
Actual backend component attribution, production browser/background behavior and
user-study validity require later qualification. The model allowance is exhausted;
use synthetic fixtures for engineering checks until separately authorized.
