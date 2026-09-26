import type {
  AnswerBody,
  CaptureRound,
  EvidenceGraph,
  ExampleSpec,
  GraphShape,
  GraphTrace,
  ExportResult,
  Health,
  IntakeResult,
  IterationRunResult,
  KinEvent,
  MeasureResult,
  Photo,
  Readiness,
  SessionDetail,
  SessionMeta,
  SettingsBody,
  SettingsInfo,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let msg = `${res.status} ${res.statusText}`;
  try {
    const text = await res.text();
    try {
      const j = JSON.parse(text);
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d: { msg?: string; loc?: unknown[] }) => `${(d.loc || []).join(".")}: ${d.msg}`).join("; ");
      else if (j.detail) msg = JSON.stringify(j.detail);
      else if (text) msg = text.slice(0, 300);
    } catch {
      if (text) msg = text.slice(0, 300);
    }
  } catch {
    /* ignore */
  }
  return new ApiError(res.status, msg);
}

async function request<T>(method: string, path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {};
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: payload, ...init });
  } catch (e) {
    throw new ApiError(0, `Network error: ${(e as Error).message}`);
  }
  if (!res.ok) throw await parseError(res);
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

const S = (sid: string) => `/api/sessions/${encodeURIComponent(sid)}`;

export function fileUrl(sid: string, rel: string, v?: string | number): string {
  const clean = rel.replace(/^\/+/, "");
  const path = clean.split("/").map(encodeURIComponent).join("/");
  return `${S(sid)}/files/${path}${v !== undefined ? `?v=${encodeURIComponent(String(v))}` : ""}`;
}

export const sheetPdfUrl = "/api/sheet.pdf";

export const kin = {
  health: () => api.get<Health>("/api/health"),
  settings: () => api.get<SettingsInfo>("/api/settings"),
  setSettings: (body: SettingsBody) =>
    api.post<{ ok: boolean; changed: string[]; llm: SettingsInfo["llm"]; probe?: { checked: boolean; ok: boolean | null; message?: string; model?: string } | null }>(
      "/api/settings",
      body,
    ),
  testSettings: () => api.post<{ checked: boolean; ok: boolean | null; message?: string; model?: string }>("/api/settings/test"),
  examples: () => api.get<ExampleSpec[]>("/api/specs/examples"),
  sessions: () => api.get<SessionMeta[]>("/api/sessions"),
  createSession: (body: { name?: string; spec_yaml?: string; scad?: string; intake?: boolean }) => api.post<SessionDetail>("/api/sessions", body),
  setStage: (sid: string, stage: string) => api.post<{ ok: boolean; stage: string }>(`${S(sid)}/stage`, { stage }),
  answers: (sid: string, answers: AnswerBody[], advance = true) =>
    api.post<{ ok: boolean; applied: unknown[]; unconfirmed: string[]; spec_yaml: string; readiness?: Readiness }>(`${S(sid)}/answers`, { answers, advance }),
  followup: (sid: string) =>
    api.post<{ evidence: EvidenceGraph; applied: unknown[]; round: CaptureRound | null; ready: boolean; readiness: Readiness; note?: string }>(`${S(sid)}/followup`),
  evidence: (sid: string) => api.get<EvidenceGraph>(`${S(sid)}/evidence`),
  graphs: (sid: string, iteration?: number) =>
    api.get<{ intake?: GraphTrace; iteration?: GraphTrace; export?: GraphTrace; shapes: Record<string, GraphShape> }>(
      `${S(sid)}/graphs${iteration ? `?iteration=${iteration}` : ""}`,
    ),
  eventsOnce: (sid: string, since = 0) => api.get<{ since: number; next: number; events: KinEvent[] }>(`${S(sid)}/events?once=true&since=${since}`),
  session: (sid: string) => api.get<SessionDetail>(S(sid)),
  deleteSession: (sid: string) => api.del<{ ok: boolean }>(S(sid)),
  updateSpec: (sid: string, spec_yaml: string) => api.put<{ ok: boolean }>(`${S(sid)}/spec`, { spec_yaml }),
  confirm: (sid: string, dim: string, value: number, source = "user_stated") =>
    api.post<{ ok: boolean; unconfirmed: string[] }>(`${S(sid)}/confirm`, { dim, value, source }),
  uploadPhotos: (sid: string, files: File[], expectSheet: boolean, label?: string) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    fd.append("expect_sheet", expectSheet ? "true" : "false");
    if (label) fd.append("label", label);
    return api.post<Photo[]>(`${S(sid)}/photos`, fd);
  },
  measure: (sid: string, body: { photo: string; mode: "sheet" | "reference"; dim?: string | null; reference?: string }) =>
    api.post<MeasureResult>(`${S(sid)}/measure`, body),
  intake: (sid: string, text: string, photos?: string[]) => api.post<IntakeResult>(`${S(sid)}/intake`, { text, photos: photos || [] }),
  run: (sid: string, body: { message?: string; strategy?: string; budget?: number; critic_rounds?: number; answer?: string }) =>
    api.post<{ ok: boolean; status: string }>(`${S(sid)}/run`, body),
  stop: (sid: string) => api.post<{ ok: boolean; stopped: boolean }>(`${S(sid)}/stop`),
  setParams: (sid: string, values: Record<string, unknown>, label?: string) =>
    api.post<IterationRunResult>(`${S(sid)}/params`, { values, label }),
  iterate: (sid: string, scad: string, label?: string) => api.post<IterationRunResult>(`${S(sid)}/iterate`, { scad, label }),
  branch: (sid: string, iteration: number) => api.post<{ ok: boolean; scad: string }>(`${S(sid)}/branch`, { iteration }),
  coupon: (sid: string) => api.post<{ ok: boolean; file: string }>(`${S(sid)}/coupon`),
  couponResult: (sid: string, clearance: number) =>
    api.post<{ ok: boolean; confirmed: string[]; iteration: IterationRunResult | null }>(`${S(sid)}/coupon/result`, { clearance }),
  export: (sid: string) => api.post<ExportResult>(`${S(sid)}/export`),
};
