const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}
const post = (body?: unknown): RequestInit => ({ method: "POST", body: body ? JSON.stringify(body) : undefined });
const patch = (body: unknown): RequestInit => ({ method: "PATCH", body: JSON.stringify(body) });

export type SeriesType = "time" | "feature" | "attribute" | "raster";

export interface Dataset {
  id: number;
  name: string;
  series_type: SeriesType;
  unit: string | null;
  source: string | null;
}
export interface Station {
  id: number; code: string; name: string; lon: number; lat: number;
  external_id: number | null; name_en: string | null; river: string | null;
  tambon: string | null; amphoe: string | null; province: string | null; basin: string | null; agency: string | null;
  left_bank: number | null; right_bank: number | null; min_bank: number | null; ground_level: number | null;
  warning_level: number | null; critical_level: number | null; is_key_station: boolean | null;
  situation_level: number | null; storage_percent: number | null; latest_value: number | null; latest_time: string | null;
}
export interface TSPoint { t: string; value: number | null }
export interface Scenario { id: number; name: string; model: string; base_time: string }

export interface Incident {
  id: number; title: string; kind: string; severity: number; status: string;
  station_id: number | null; province: string | null; amphoe: string | null; description: string | null;
  households_affected: number; area_rai: number; lon: number | null; lat: number | null;
  started_at: string; ended_at: string | null; claims: number;
}
export type IncidentInput = Partial<Omit<Incident, "id" | "claims" | "started_at" | "ended_at">> & { title: string };

export interface Claim {
  id: number; incident_id: number; claimant: string; village: string | null;
  province: string | null; amphoe: string | null; damage_type: string;
  area_rai: number | null; units: number | null; estimated_thb: number; approved_thb: number | null; status: string;
  notes: string | null; submitted_at: string;
}
export type ClaimInput = Pick<Claim, "incident_id" | "claimant" | "damage_type" | "estimated_thb"> &
  Partial<Pick<Claim, "village" | "area_rai" | "units" | "notes">>;

export interface Rate {
  id: number; damage_type: string; province: string | null; label: string; category: string; unit: string;
  rate_thb: number | null; max_units: number | null; max_thb: number | null; source: string | null;
  effective_from: string | null;
}

export interface Flag { code: string; level: "info" | "review" | "high"; title: string; detail: string; photo_id: number | null }

export interface AssessmentSummary { claim_id: number; level: "ok" | "review" | "high"; score: number; flags: number; top_flag: string | null }

export interface Assessment extends AssessmentSummary {
  flag_list: Flag[];
  rate: Rate | null; rate_region: string | null;
  quantity: number | null; eligible_quantity: number | null; official_max_thb: number | null;
  peer_group: string | null; peer_count: number; peer_median: number | null;
  expected_low_thb: number | null; expected_mid_thb: number | null; expected_high_thb: number | null;
}

export interface Photo {
  id: number; claim_id: number; filename: string; content_type: string | null; size_bytes: number;
  width: number | null; height: number | null; taken_at: string | null; lat: number | null; lon: number | null;
  camera: string | null; uploaded_at: string; url: string; thumb_url: string; distance_km: number | null;
}

export const fileUrl = (path: string) => `${BASE}${path}`;

export interface CompensationSummary {
  by_status: Record<string, { count: number; estimated_thb: number; approved_thb: number }>;
  claims: number; estimated_thb: number; approved_thb: number; paid_thb: number;
}

export const api = {
  datasets: () => http<Dataset[]>("/api/datasets"),
  stations: () => http<Station[]>("/api/stations"),
  syncStations: () => http<{ stations: number; readings: number }>("/api/sync/stations", post()),
  syncHistory: (stationId: number, days = 7) =>
    http<{ points: number; dataset_id: number }>(`/api/stations/${stationId}/sync-history?days=${days}`, post()),
  timeseries: (datasetId: number, stationId: number) =>
    http<TSPoint[]>(`/api/datasets/${datasetId}/timeseries?station_id=${stationId}`),
  runPrediction: (dataset_id: number, station_id: number, horizon_hours = 48) =>
    http<Scenario[]>("/api/prediction/run", post({ dataset_id, station_id, horizon_hours })),
  scenarioResults: (id: number) => http<{ t: string; value: number }[]>(`/api/scenarios/${id}/results`),

  incidents: () => http<Incident[]>("/api/incidents"),
  createIncident: (body: IncidentInput) => http<Incident>("/api/incidents", post(body)),
  updateIncident: (id: number, body: Partial<Incident>) => http<Incident>(`/api/incidents/${id}`, patch(body)),

  claims: () => http<Claim[]>("/api/claims"),
  createClaim: (body: ClaimInput) => http<Claim>("/api/claims", post(body)),
  updateClaim: (id: number, body: Partial<Claim>) => http<Claim>(`/api/claims/${id}`, patch(body)),
  compensationSummary: () => http<CompensationSummary>("/api/compensation/summary"),

  assessments: () => http<AssessmentSummary[]>("/api/compensation/assessments"),
  assessment: (claimId: number) => http<Assessment>(`/api/claims/${claimId}/assessment`),

  rates: () => http<Rate[]>("/api/compensation/rates"),
  addRateOverride: (body: { damage_type: string; province: string; rate_thb?: number | null; max_units?: number | null; max_thb?: number | null }) =>
    http<Rate>("/api/compensation/rates", post(body)),
  updateRate: (id: number, body: Partial<Pick<Rate, "rate_thb" | "max_units" | "max_thb" | "source">>) =>
    http<Rate>(`/api/compensation/rates/${id}`, patch(body)),
  deleteRate: (id: number) => fetch(`${BASE}/api/compensation/rates/${id}`, { method: "DELETE" }),

  photos: (claimId: number) => http<Photo[]>(`/api/claims/${claimId}/photos`),
  uploadPhotos: async (claimId: number, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const res = await fetch(`${BASE}/api/claims/${claimId}/photos`, { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? `Upload failed (${res.status})`);
    return (await res.json()) as Photo[];
  },
  deletePhoto: (id: number) => fetch(`${BASE}/api/photos/${id}`, { method: "DELETE" }),

  seedResponse: () => http<unknown>("/api/dev/seed-response", post()),
};
