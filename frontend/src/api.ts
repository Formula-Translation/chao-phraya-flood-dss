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
  id: number; incident_id: number; claimant: string; village: string | null; damage_type: string;
  area_rai: number | null; estimated_thb: number; approved_thb: number | null; status: string;
  notes: string | null; submitted_at: string;
}
export type ClaimInput = Pick<Claim, "incident_id" | "claimant" | "damage_type" | "estimated_thb"> &
  Partial<Pick<Claim, "village" | "area_rai" | "notes">>;

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

  seedResponse: () => http<unknown>("/api/dev/seed-response", post()),
};
