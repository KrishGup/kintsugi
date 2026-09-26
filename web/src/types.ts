// Shapes returned by the Kintsugi FastAPI backend (kintsugi/server/app.py).

export type Stage = "intake" | "capture" | "spec" | "design" | "review" | "export";

export interface LlmStatus {
  provider: "openai" | "agent" | "fake" | string;
  models: { designer?: string; critic?: string; vision?: string; fast?: string; [k: string]: string | undefined };
  effort: string;
  ready: boolean;
  reason: string;
}

export interface Health {
  ok: boolean;
  version: string;
  openscad?: string | null;
  sessions_dir?: string;
  llm?: LlmStatus;
}

export interface SettingsInfo {
  llm: LlmStatus;
  openai_key_masked: string;
  defaults: Record<string, Record<string, string>>;
  providers: string[];
}

export interface SettingsBody {
  openai_api_key?: string;
  provider?: string;
  designer_model?: string;
  critic_model?: string;
  vision_model?: string;
  effort?: string;
  persist?: boolean;
}

export interface SessionMeta {
  id: string;
  name: string;
  created: number;
  updated?: number;
  status: string; // new | intake_done | running | iterating | waiting_user | done | budget_exhausted | stopped | error
  stage?: Stage | string;
  iteration: number;
  critic_rounds?: number;
  model?: string;
  last_ok?: boolean;
  question?: { question: string; options: string[]; photos?: Array<{ label: string; dims: string[]; instructions: string }> } | null;
  narration?: string;
  cost_usd?: number;
  exported_iteration?: number;
  exported_at?: number;
}

export interface Estimate {
  value: number;
  source: string;
  conf?: number;
  photo?: string | null;
  note?: string | null;
}

export interface MeasureRecipe {
  recipe: string;
  at_z?: number | null;
  axis?: string;
  plane_axis?: string;
  near?: number[] | null;
  region?: number[][] | null;
  expect?: number[][] | null;
  feature?: string | null;
}

export interface Dim {
  target?: number | null;
  tol?: number;
  min?: number | null;
  max?: number | null;
  status?: "unknown" | "estimated" | "confirmed";
  estimates?: Estimate[];
  measure?: MeasureRecipe | null;
  unit?: string;
  note?: string | null;
}

export interface Interface {
  id: string;
  type?: string;
  mates_with?: string;
  fit?: string;
  clearance?: number | null;
  dims?: Record<string, Dim>;
  note?: string | null;
}

export interface Requirement {
  id: string;
  text: string;
  derived?: Record<string, Dim>;
}

export interface PartSpec {
  part?: { name?: string; role?: string; object?: string; design_intent?: string; notes?: string };
  interfaces?: Interface[];
  requirements?: Requirement[];
  context?: Array<Record<string, unknown>>;
  print?: {
    material?: string;
    nozzle?: number;
    layer_height?: number;
    min_wall?: number;
    orientation_hint?: string | null;
    supports_ok?: boolean;
  };
  open_questions?: string[];
}

export interface ParamBinding {
  dim: string;
  how: "explicit" | "name" | "value" | "name+value" | string;
  role: "interface" | "requirement" | string;
  target: number | null;
  tol: number | null;
  min: number | null;
  max: number | null;
  status: "unknown" | "estimated" | "confirmed" | string;
  clearance: number | null;
  fit: string | null;
  sources: Array<{ value: number; source: string; conf: number | null; photo?: string | null }>;
  feature?: string | null;
}

export interface Param {
  name: string;
  value: unknown;
  type: "number" | "string" | "bool" | "vector" | string;
  section: string;
  description: string;
  min: number | null;
  max: number | null;
  step: number | null;
  options: Array<{ value: unknown; label: string }>;
  raw_value?: string;
  unit?: string;
  kind?: "length" | "angle" | "count" | "ratio" | "clearance" | "stress" | "mass" | "facets" | "toggle" | "choice" | "text" | "vector" | "number" | string;
  label?: string;
  gate?: string | null;
  binding?: ParamBinding | null;
  order?: number;
}

export interface DerivedValue {
  name: string;
  expr: string;
  value: unknown;
  echoed: boolean;
  binding?: { dim: string; role: string; min: number | null; max: number | null; target: number | null; tol: number | null } | null;
}

export interface CustomizerModel {
  available: boolean;
  params: Param[];
  sections: string[];
  render_targets: string[] | null;
  derived: DerivedValue[];
  asserts: Array<{ cond: string; message: string; params: string[] }>;
  bindings: Record<string, string>;
  presets: Record<string, Record<string, unknown>>;
  verified: { iteration: number; values: Record<string, unknown>; ok: boolean } | null;
  preview: PreviewResult | null;
  has_render_target: boolean;
  draft_fn: number;
  part_name?: string;
}

export interface PreviewResult {
  ok: boolean;
  gen: number;
  superseded: boolean;
  cancelled?: boolean;
  values: Record<string, unknown>;
  render_target?: string | null;
  quality?: string;
  duration_s?: number;
  avg_duration_s?: number | null;
  echo_values?: Record<string, unknown>;
  errors?: string[];
  warnings?: string[];
  file?: string | null;
  version?: number;
  assert_failures?: string[];
}

export interface CheckItem {
  id: string;
  label: string;
  kind: "hard" | "soft" | "info" | string;
  passed: boolean | null;
  measured?: unknown;
  target?: unknown;
  tol?: number | null;
  unit?: string;
  detail?: string;
  annotate?: unknown;
}

export interface Checks {
  iteration: number;
  mesh_path?: string;
  all_hard_pass: boolean;
  items: CheckItem[];
  stats?: {
    triangles?: number;
    vertices?: number;
    watertight?: boolean;
    winding_consistent?: boolean;
    bodies?: number;
    volume_mm3?: number;
    surface_area_mm2?: number;
    bbox?: { min: number[]; max: number[]; size: number[] };
    center_mass?: number[];
  };
  walls?: { min: number; p05: number; median: number; n: number; required: number } | null;
  printability?: {
    overhang_fraction: number;
    overhang_area: number;
    bed_contact_area: number;
    centroid_height: number;
    height: number;
    footprint_area: number;
  } | null;
  orientations?: Array<{ name: string; score?: number; overhang_fraction?: number; bed_contact_area?: number; height?: number }>;
  sections?: Array<{ plane_axis: string; at: number; dims: string[] }>;
  interference?: Array<{ id: string; volume_mm3: number; allow_contact: boolean }>;
}

export interface IterationEntry {
  iteration: number;
  ok: boolean;
  compile_ok: boolean;
  failures: string[];
  measured?: Record<string, number>;
  targets?: Record<string, number>;
  label?: string;
  sheet: string | null;
  sections: string | null;
  stl: string | null;
  views: string[];
}

export interface Discrepancy {
  where?: string;
  expected?: string;
  observed?: string;
  severity?: string;
  suggestion?: string;
}

export interface CriticEntry {
  file: string;
  verdict: string;
  summary: string;
  discrepancies: Discrepancy[];
  question_for_user?: string | null;
  model?: string | null;
  duration_s?: number;
}

export interface PhotoGrade {
  sharpness?: number;
  sharpness_ok?: boolean;
  exposure_ok?: boolean;
  mean_brightness?: number;
  markers_found?: number;
  tilt_deg?: number | null;
  tilt_ok?: boolean;
  ok?: boolean;
  instructions?: string[];
  edge_width_px?: number | null;
  marker_px?: number | null;
  error?: string;
}

export interface Photo {
  file: string;
  grade: PhotoGrade | null;
  estimates?: Array<{ dim: string; value: number; conf: number; photo: string; status?: string }>;
}

export interface SessionDetail {
  meta: SessionMeta;
  spec: PartSpec;
  spec_yaml: string;
  params: Param[];
  checks: Checks | null;
  iterations: IterationEntry[];
  critic: CriticEntry[];
  photos: Photo[];
  scad: string | null;
  stl: string | null;
  running: boolean;
  export: string[];
  unconfirmed: string[];
  intake: IntakeResult | null;
  stage: Stage | string;
  llm?: LlmStatus;
  readiness?: Readiness;
  flow?: { stage: string; transitions: Array<{ to: string; label: string; enabled: boolean; guard: string }> };
}

export interface CaptureRequest {
  id: string;
  kind: "photo" | "measure" | "choice" | "coupon" | string;
  dims: string[];
  title: string;
  instructions: string;
  why?: string;
  priority?: number;
  feature?: string | null;
  label?: string | null;
  options?: string[];
}

export interface CaptureRound {
  n: number;
  t?: number;
  requests: CaptureRequest[];
  note?: string;
  missing?: MissingDim[];
}

export interface MissingDim {
  dim: string;
  importance: "interface" | "requirement" | string;
  status: string;
  conf: number;
  reason: "unknown" | "low_confidence" | "conflict" | "estimated" | string;
  recipe?: string | null;
  feature?: string | null;
  interface?: string | null;
  mates_with?: string | null;
  fit?: string | null;
  target?: number | null;
}

export interface Readiness {
  ready: boolean;
  blocking: string[];
  unconfirmed: string[];
  confirmed: number;
  interface_dims: number;
  score: number;
  advice: string;
  missing?: MissingDim[];
}

export interface EvidenceNode {
  id: string;
  type: "dim" | "estimate" | "photo" | "shot" | "request" | "question" | "standard" | "check" | string;
  label?: string;
  status?: string;
  conf?: number;
  target?: number | null;
  importance?: string;
  source?: string;
  trust?: number;
  value?: number;
  ok?: boolean;
  passed?: boolean | null;
  kind?: string;
  file?: string;
  round?: number;
  [k: string]: unknown;
}

export interface EvidenceEdge {
  from: string;
  to: string;
  rel: string;
  weight?: number;
}

export interface EvidenceGraph {
  nodes: EvidenceNode[];
  edges: EvidenceEdge[];
  missing: MissingDim[];
  ready: boolean;
  readiness: Readiness;
}

export interface GraphNodeRun {
  name: string;
  kind: "algorithm" | "agent" | "human" | "io" | string;
  label: string;
  status: "pending" | "running" | "done" | "failed" | "skipped" | "waiting" | string;
  wave: number | null;
  duration_s: number | null;
  est_s: number;
  error?: string | null;
  note?: string;
}

export interface GraphTrace {
  graph: string;
  status: string;
  waiting_on?: string | null;
  request?: Record<string, unknown> | null;
  nodes: GraphNodeRun[];
  edges: Array<{ from: string; to: string; key: string }>;
  critical_path: string[];
  critical_s: number;
  wall_s: number;
  serial_s: number;
  speedup?: number | null;
  waves?: number;
  started?: number;
  iteration?: number;
}

export interface GraphShape {
  graph: string;
  nodes: Array<{ name: string; kind: string; label: string; inputs: string[]; outputs: string[]; est_s: number; optional: boolean }>;
  edges: Array<{ from: string; to: string; key: string }>;
  critical_path: string[];
  critical_s: number;
}

export interface IntakeQuestion {
  id?: string;
  text?: string;
  kind?: string; // number | choice | text
  options?: string[];
  dim?: string | null;
}

export interface CaptureShot {
  n?: number;
  name?: string;
  purpose?: string;
  how?: string;
  measures?: string[];
}

export interface AnswerBody {
  id?: string;
  dim?: string | null;
  kind: "number" | "choice" | "text" | "measure";
  value: string | number;
  question?: string;
}

export interface ExampleSpec {
  name: string;
  yaml: string;
}

export interface IntakeResult {
  object?: string;
  part_role?: string;
  damage?: string;
  interfaces_reasoning?: string;
  spec?: unknown;
  spec_error?: string;
  capture_plan?: CaptureShot[];
  questions?: IntakeQuestion[];
  confidence?: number;
  spec_yaml?: string;
  rounds?: CaptureRound[];
  standards?: Array<{ id: string; name: string; dims: Record<string, number>; note?: string; conf?: number }>;
  standard_estimates?: Array<{ dim: string; value: number; standard: string }>;
  designer_requests?: Array<{ label: string; dims: string[]; instructions: string }>;
  capture_done?: boolean;
  round?: CaptureRound | null;
  evidence?: EvidenceGraph;
  graph?: GraphTrace;
}

export interface MeasureResult {
  photo: string;
  mode: string;
  markers?: number;
  tilt_deg?: number | null;
  circles?: Array<{ cx: number; cy: number; d: number; conf?: number; method?: string }>;
  outline_points?: number;
  openscad_polygon?: string;
  rectified?: string;
  reference?: { kind: string; mm_per_px: number; conf: number };
  attached_to?: string;
  [k: string]: unknown;
}

export interface IterationRunResult {
  iteration: number;
  ok: boolean;
  compile: { ok: boolean; errors?: string[]; warnings?: string[]; [k: string]: unknown };
  checks: Checks | null;
  blueprint: unknown;
  duration_s: number;
  signals: string[];
  budget_left: number;
}

export interface ExportResult {
  iteration: number;
  files: Record<string, string>;
  unconfirmed: string[];
}

// One line of the session's events.jsonl, streamed over SSE. `kind` is the SSE event name.
export interface KinEvent {
  id: number;
  t: number;
  kind: string;
  [k: string]: unknown;
}
