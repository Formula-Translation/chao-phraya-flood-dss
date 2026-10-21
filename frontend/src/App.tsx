import { useCallback, useEffect, useState } from "react";
import { api, type Claim, type CompensationSummary, type Dataset, type Incident, type Station } from "./api";
import MapView from "./components/MapView";
import StationSearch from "./components/StationSearch";
import { SEVERITY, SITUATION } from "./lookups";
import PredictionTab from "./tabs/PredictionTab";
import IncidentTab from "./tabs/IncidentTab";
import CompensationTab from "./tabs/CompensationTab";

export type Tab = "prediction" | "incident" | "compensation";
const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: "prediction", label: "Prediction", hint: "Before: watch levels and forecast" },
  { id: "incident", label: "Incident", hint: "During: track flood events" },
  { id: "compensation", label: "Compensation", hint: "After: process damage claims" },
];

export interface Pick { onPick: (lon: number, lat: number) => void; point: [number, number] | null }

export default function App() {
  const [tab, setTab] = useState<Tab>("prediction");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [stationId, setStationId] = useState<number | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [incidentId, setIncidentId] = useState<number | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [summary, setSummary] = useState<CompensationSummary | null>(null);
  const [pick, setPick] = useState<Pick | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const station = stations.find((s) => s.id === stationId);

  const loadStations = useCallback(async () => {
    const [ds, st] = await Promise.all([api.datasets(), api.stations()]);
    setDatasets(ds);
    setStations(st);
    setStationId((cur) => cur ?? (st.find((s) => s.code === "C.2") ?? st.find((s) => s.is_key_station) ?? st[0])?.id ?? null);
  }, []);

  const loadResponse = useCallback(async () => {
    const [inc, cl, sum] = await Promise.all([api.incidents(), api.claims(), api.compensationSummary()]);
    setIncidents(inc);
    setClaims(cl);
    setSummary(sum);
    setIncidentId((cur) => cur ?? inc[0]?.id ?? null);
  }, []);

  useEffect(() => {
    Promise.all([loadStations(), loadResponse()]).catch(() =>
      setError("Can't reach the API at port 8000. Check that the backend container is running.")
    );
  }, [loadStations, loadResponse]);

  async function importStations() {
    setSyncing(true);
    try {
      await api.syncStations();
      await loadStations();
      setError(null);
    } catch {
      setError("Couldn't reach ThaiWater. Check the internet connection and try again.");
    } finally {
      setSyncing(false);
    }
  }

  const changeTab = (t: Tab) => { setPick(null); setTab(t); };
  const shared = { stations, station, incidents, claims, summary, setError };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">CFM</span>
          <span className="brand-sub">Chao Phraya flood decision support</span>
        </div>
        <nav className="tabs" role="tablist" aria-label="Stage">
          {TABS.map((t) => (
            <button
              key={t.id} role="tab" aria-selected={tab === t.id} title={t.hint}
              className={`tab ${tab === t.id ? "on" : ""}`} onClick={() => changeTab(t.id)}
            >
              {t.label}
              {t.id === "incident" && incidents.some((i) => i.status === "active") && (
                <span className="tab-count">{incidents.filter((i) => i.status === "active").length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="topbar-right">
          {tab === "prediction" && stations.length > 0 && (
            <StationSearch stations={stations} selected={station} onSelect={setStationId} />
          )}
        </div>
      </header>

      <div className="workspace">
        <div className="map-wrap">
          <MapView
            stations={stations}
            selectedStation={stationId}
            onSelectStation={(id) => { setStationId(id); if (tab !== "prediction" && !pick) setTab("prediction"); }}
            incidents={incidents}
            showIncidents={tab !== "prediction"}
            selectedIncident={incidentId}
            onSelectIncident={setIncidentId}
            onPick={pick?.onPick ?? null}
            pickPoint={pick?.point ?? null}
          />
          <div className="map-legend">
            {tab === "prediction"
              ? Object.values(SITUATION).map((s) => (
                  <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>
                ))
              : Object.values(SEVERITY).map((s) => (
                  <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>
                ))}
          </div>
          {pick && <div className="map-banner">Click the map to place the incident</div>}
        </div>

        {tab === "prediction" && (
          <PredictionTab {...shared} datasets={datasets} onImport={importStations} syncing={syncing} error={error} />
        )}
        {tab === "incident" && (
          <IncidentTab
            {...shared} error={error} selectedId={incidentId} onSelect={setIncidentId}
            reload={loadResponse} pick={pick} setPick={setPick}
          />
        )}
        {tab === "compensation" && (
          <CompensationTab
            {...shared} error={error} selectedIncident={incidentId} onSelectIncident={setIncidentId} reload={loadResponse}
          />
        )}
      </div>
    </div>
  );
}
