/** Opt-in, bounded, memory-only diagnostics. Never stores request content or source identifiers. */
export type TimingStep = 'case_load' | 'image_load' | 'preview_prepare' | 'preview_assets' | 'global_submit' | 'lesion_submit' | 'prism_submit' | 'review_save' | 'annotation_save' | 'folder_preview' | 'folder_snapshot';
export type TimingEvent = 'case_open' | 'case_ready' | 'image_ready' | 'image_error' | 'preview_ready' | 'result_render_commit' | 'review_edit' | 'confirmed_save' | 'annotation_confirmed_save' | 'late_response_ignored';
export type Outcome = 'COMPLETED' | 'FAILED' | 'ABORTED' | 'STALE' | 'INCOMPLETE';
type Cohort = 'UNSPECIFIED' | 'SYNTHETIC_AUTOMATION' | 'OBSERVED_USER';
type Environment = 'UNKNOWN' | 'LOCAL_APP_QA_MODEL' | 'HOSPITAL_LOCAL' | 'LIGHTNING';
type Phase = 'UNKNOWN' | 'COLD' | 'WARM';
export interface TimingConfig { cohort: Cohort; environment: Environment; phase: Phase }
interface Flow { id: string; name: 'case_to_confirmed_save' | 'annotation_to_confirmed_save' | 'grading_folder_preview' | 'grading_folder_snapshot'; started_ms: number; ended_ms: number | null; outcome: Outcome | null; active_observation_ms: number; foreground_idle_ms: number; background_ms: number; human_review_ms: null; modality: 'UNKNOWN' | 'CFP' | 'UWF'; config: TimingConfig }
export interface TimingModel { model_id?: string; model_version?: string }
interface Entry { flow_id: string; step_id?: string; name: TimingStep | TimingEvent; at_ms: number; started_ms?: number; duration_ms?: number; outcome?: Outcome; error_code?: 'STEP_FAILED' | 'CLIENT_CANCELLED' | 'CONTEXT_RETIRED' | null; model_id?: string | null; model_version?: string | null; queue_ms?: number | null; preprocessing_ms?: number | null; inference_ms?: number | null }
export interface TimingSpan { end: (outcome: Outcome, serverTiming?: string | null) => void }
const noSpan: TimingSpan = { end: () => undefined };
const STEPS = new Set<TimingStep>(['case_load', 'image_load', 'preview_prepare', 'preview_assets', 'global_submit', 'lesion_submit', 'prism_submit', 'review_save', 'annotation_save', 'folder_preview', 'folder_snapshot']);
const EVENTS = new Set<TimingEvent>(['case_open', 'case_ready', 'image_ready', 'image_error', 'preview_ready', 'result_render_commit', 'review_edit', 'confirmed_save', 'annotation_confirmed_save', 'late_response_ignored']);

export function serverDurations(header?: string | null) {
  const result = { queue_ms: null, preprocessing_ms: null, inference_ms: null } as Record<'queue_ms' | 'preprocessing_ms' | 'inference_ms', number | null>;
  for (const part of (header ?? '').slice(0, 1024).split(',')) {
    const match = /^\s*(queue|preprocessing|inference)\s*;\s*dur=(\d+(?:\.\d+)?)\s*$/.exec(part);
    if (match && Number(match[2]) <= 86_400_000) result[`${match[1]}_ms` as keyof typeof result] = Number(match[2]);
  }
  return result;
}

function opaqueId() {
  try { return crypto.randomUUID(); }
  catch { return `local-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`; }
}

export class LocalTiming {
  enabled = false;
  private config: TimingConfig = { cohort: 'UNSPECIFIED', environment: 'UNKNOWN', phase: 'UNKNOWN' };
  private session: string;
  private flows: Flow[] = [];
  private entries: Entry[] = [];
  private current: { key: string; flow: Flow } | null = null; // Runtime routing only; never serialized.
  private pending = new Map<string, { flow: Flow; step: TimingStep; start: number; ended: boolean; cancelled: boolean; late: boolean; model_id: string | null; model_version: string | null }>();
  private dropped = 0;
  private generation = 0;
  private last: number;
  private lastInteraction = -Infinity;
  private foreground = true;
  constructor(private now = () => performance.now(), private id = opaqueId) { this.session = this.id(); this.last = this.now(); }
  configuration() { return { ...this.config }; }
  modality(key: string, value: string) {
    if (this.current?.key === key && (value === 'CFP' || value === 'UWF')) this.current.flow.modality = value;
  }
  configure(enabled: boolean, config: TimingConfig = this.config) {
    const valid = ['UNSPECIFIED', 'SYNTHETIC_AUTOMATION', 'OBSERVED_USER'].includes(config.cohort)
      && ['UNKNOWN', 'LOCAL_APP_QA_MODEL', 'HOSPITAL_LOCAL', 'LIGHTNING'].includes(config.environment)
      && ['UNKNOWN', 'COLD', 'WARM'].includes(config.phase);
    if (!valid) return;
    if (!enabled || JSON.stringify(config) !== JSON.stringify(this.config)) {
      this.leave();
      for (const flow of this.flows) this.close(flow, 'ABORTED');
    }
    this.enabled = enabled;
    this.config = { ...config };
    this.last = this.now();
  }
  private tick() {
    const at = this.now();
    const elapsed = Math.max(0, at - this.last);
    for (const flow of this.flows.filter((value) => value.ended_ms === null)) {
      if (!this.foreground) flow.background_ms += elapsed;
      else {
        const active = Math.max(0, Math.min(at, this.lastInteraction + 30_000) - this.last);
        flow.active_observation_ms += Math.min(elapsed, active);
        flow.foreground_idle_ms += elapsed - Math.min(elapsed, active);
      }
    }
    this.last = at;
    return at;
  }
  interact() { this.tick(); this.lastInteraction = this.now(); }
  visibility(foreground: boolean) { this.tick(); this.foreground = foreground; }
  private record(entry: Entry) {
    if (this.entries.length >= 4000) { this.dropped++; return; }
    this.entries.push(entry);
  }
  private create(name: Flow['name']) {
    this.tick();
    if (!this.enabled || this.flows.length >= 200) { if (this.enabled) this.dropped++; return null; }
    const flow: Flow = { id: this.id(), name, started_ms: this.now(), ended_ms: null, outcome: null,
      active_observation_ms: 0, foreground_idle_ms: 0, background_ms: 0, human_review_ms: null, modality: 'UNKNOWN', config: { ...this.config } };
    this.flows.push(flow);
    return flow;
  }
  enter(key: string | null, annotation = false) {
    const name = annotation ? 'annotation_to_confirmed_save' : 'case_to_confirmed_save';
    if (this.current?.key === key && this.current.flow.name === name && this.current.flow.ended_ms === null) return;
    this.leave();
    if (key) {
      const flow = this.create(name);
      if (flow) { this.current = { key, flow }; this.event('case_open', key); this.start('image_load', key); }
    }
  }
  leave() {
    if (this.current) this.close(this.current.flow, 'INCOMPLETE');
    this.current = null;
  }
  private close(flow: Flow, outcome: Outcome) {
    if (flow.ended_ms !== null) return;
    flow.ended_ms = this.tick();
    flow.outcome = outcome;
    for (const [id, item] of this.pending) if (item.flow === flow && !item.ended) {
      item.ended = true;
      item.cancelled = true;
      this.record({ flow_id: flow.id, step_id: id, name: item.step, started_ms: item.start,
        at_ms: flow.ended_ms, duration_ms: Math.max(0, flow.ended_ms - item.start), outcome: 'ABORTED',
        error_code: 'CONTEXT_RETIRED', model_id: item.model_id, model_version: item.model_version });
      this.pending.delete(id);
    }
  }
  event(name: TimingEvent, key?: string) {
    if (!this.enabled || !EVENTS.has(name) || !this.current || this.current.flow.ended_ms !== null || (key !== undefined && key !== this.current.key)) return;
    this.record({ flow_id: this.current.flow.id, name, at_ms: this.tick() });
    if (name === 'image_ready' || name === 'image_error') {
      for (const [id, item] of this.pending) if (item.flow === this.current.flow && item.step === 'image_load') {
        item.ended = true;
        this.record({ flow_id: item.flow.id, name: item.step, step_id: id, started_ms: item.start,
          at_ms: this.now(), duration_ms: Math.max(0, this.now() - item.start), outcome: name === 'image_ready' ? 'COMPLETED' : 'FAILED' });
        this.pending.delete(id);
      }
    }
    if (name === 'confirmed_save' || name === 'annotation_confirmed_save') this.close(this.current.flow, 'COMPLETED');
  }
  private span(flow: Flow | null, step: TimingStep, ownFlow = false, parameters?: TimingModel): TimingSpan {
    if (!flow || !this.enabled || !STEPS.has(step)) return noSpan;
    if (this.pending.size >= 1000) { this.dropped++; return noSpan; }
    const id = this.id();
    const generation = this.generation;
    const model_id = ['uspec-uwf-grading', 'NBeye-research/USPEC', 'retfound-aptos5', 'prism-dr-5fold'].includes(parameters?.model_id ?? '') ? parameters!.model_id! : null;
    const model_version = model_id && /^[a-f0-9]{7,64}$/.test(parameters?.model_version ?? '') ? parameters!.model_version! : null;
    const pending = { flow, step, start: this.tick(), ended: false, cancelled: false, late: false, model_id, model_version };
    this.pending.set(id, pending);
    return { end: (outcome, header) => {
      if (!this.enabled || generation !== this.generation) return;
      if (pending.ended) {
        if (pending.cancelled && flow.ended_ms !== null && !pending.late) {
          pending.late = true;
          this.record({ flow_id: flow.id, name: 'late_response_ignored', at_ms: this.tick(), outcome: 'STALE' });
        }
        return;
      }
      pending.ended = true;
      const at = this.tick();
      this.record({ flow_id: flow.id, step_id: id, name: step, started_ms: pending.start, at_ms: at, duration_ms: Math.max(0, at - pending.start),
        outcome: flow.ended_ms === null ? outcome : 'STALE',
        error_code: outcome === 'FAILED' ? 'STEP_FAILED' : outcome === 'ABORTED' ? 'CLIENT_CANCELLED' : outcome === 'STALE' ? 'CONTEXT_RETIRED' : null,
        model_id, model_version, ...serverDurations(header) });
      this.pending.delete(id);
      if (ownFlow) this.close(flow, outcome);
    } };
  }
  start(step: TimingStep, key?: string, parameters?: TimingModel) {
    return this.span(this.current && (key === undefined || key === this.current.key) && this.current.flow.ended_ms === null ? this.current.flow : null, step, false, parameters);
  }
  folder(step: 'folder_preview' | 'folder_snapshot') { return this.span(this.create(step === 'folder_preview' ? 'grading_folder_preview' : 'grading_folder_snapshot'), step, true); }
  clear() { this.leave(); this.generation++; this.flows = []; this.entries = []; this.pending.clear(); this.dropped = 0; this.session = this.id(); this.last = this.now(); }
  export() {
    this.tick();
    return JSON.parse(JSON.stringify({ schema_version: 'local-ux-timing.v1', opaque_session_id: this.session,
      generated_at: new Date().toISOString(), clock: 'performance.now', active_window_ms: 30_000,
      active_observation_is_not_human_review: true, flow_limit: 200, event_limit: 4000, dropped: this.dropped,
      backend_components: 'Only explicitly reported Server-Timing durations; missing means null; never subtract host clocks.',
      model_id: null, model_version: null, config_sha256: null, checkpoint_sha256: null,
      hardware: null, backend_network_only_ms: null, clinical_user_benchmark_verified: false,
      pending: [...this.pending].map(([step_id, value]) => ({ step_id, flow_id: value.flow.id, name: value.step, started_ms: value.start, outcome: 'UNFINISHED' })),
      flows: this.flows, entries: this.entries, step_summary: summarize(this.entries, this.flows),
      flow_summary: summarize(this.flows.filter((flow) => flow.ended_ms !== null).map((flow) => ({
        flow_id: flow.id, name: flow.name, outcome: flow.outcome!, duration_ms: flow.ended_ms! - flow.started_ms })), this.flows) }));
  }
}

export function summarize(entries: Array<{ flow_id: string; name: string; duration_ms?: number; outcome?: Outcome; model_id?: string | null; model_version?: string | null }>, flows: Flow[]) {
  const groups = new Map<string, { n: number; completed: number[]; failed: number; aborted: number; stale: number; incomplete: number }>();
  for (const entry of entries) if (entry.duration_ms !== undefined) {
    const config = flows.find((flow) => flow.id === entry.flow_id)?.config;
    const parent = flows.find((flow) => flow.id === entry.flow_id);
    const key = JSON.stringify([entry.name, config?.cohort, config?.environment, config?.phase, parent?.modality, entry.model_id ?? null, entry.model_version ?? null, parent?.name]);
    const group = groups.get(key) ?? { n: 0, completed: [], failed: 0, aborted: 0, stale: 0, incomplete: 0 };
    group.n++;
    if (entry.outcome === 'COMPLETED') group.completed.push(entry.duration_ms);
    else if (entry.outcome === 'FAILED') group.failed++;
    else if (entry.outcome === 'ABORTED') group.aborted++;
    else if (entry.outcome === 'INCOMPLETE') group.incomplete++;
    else group.stale++;
    groups.set(key, group);
  }
  return [...groups].map(([key, value]) => {
    const [step, cohort, environment, phase, modality, model_id, model_version, flow_name] = JSON.parse(key) as Array<string | null>;
    const sorted = value.completed.sort((a, b) => a - b);
    const n = sorted.length;
    return { step, flow_name, cohort, environment, phase, modality, model_id, model_version, comparison_qualified: false, n: value.n, completed_n: n, failed_n: value.failed, aborted_n: value.aborted, stale_n: value.stale, incomplete_n: value.incomplete,
      mean_ms: n ? sorted.reduce((a, b) => a + b, 0) / n : null,
      median_ms: n ? (sorted[Math.floor((n - 1) / 2)] + sorted[Math.floor(n / 2)]) / 2 : null,
      p95_ms: n >= 20 ? sorted[Math.ceil(n * .95) - 1] : null, p95_status: n >= 20 ? 'DESCRIPTIVE_ONLY' : 'INSUFFICIENT_SAMPLES' };
  });
}

export const localTiming = new LocalTiming();

/** Whitelist operation class only. URLs, bodies, response objects and error messages never enter logs. */
export function requestTiming(input: RequestInfo | URL, method = 'GET', parameters?: TimingModel) {
  if (!localTiming.enabled) return noSpan;
  const path = typeof input === 'string' ? input.split('?')[0] : input instanceof URL ? input.pathname : '';
  const match = /^\/v1\/cases\/([^/]+)(.*)$/.exec(path);
  if (match) {
    let key: string;
    try { key = decodeURIComponent(match[1]); } catch { return noSpan; }
    const suffix = match[2];
    const step = suffix === '' ? 'case_load' : suffix === '/prism-input-preview' ? 'preview_prepare'
      : /^\/prism-input-preview\/[^/]+\/infer$/.test(suffix) ? 'prism_submit' : suffix === '/review' ? 'review_save' : suffix === '/annotations' ? 'annotation_save' : null;
    if (step) return localTiming.start(step, key, parameters);
  }
  if (path === '/v1/infer/global' && method === 'POST') return localTiming.start('global_submit', undefined, parameters);
  if (path === '/v1/infer/lesion-roi' && method === 'POST') return localTiming.start('lesion_submit', undefined, parameters);
  return noSpan;
}
