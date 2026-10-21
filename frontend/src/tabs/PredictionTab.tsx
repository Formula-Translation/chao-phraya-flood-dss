import { useEffect, useMemo, useState } from "react";
import { api, type Dataset, type Station, type TSPoint } from "../api";
import Timeline, { SCENARIO_COLORS, type ScenarioSeries } from "../components/Timeline";
import { fmtTime, num, SITUATION } from "../lookups";

interface Props {
  stations: Station[];
  station: Station | undefined;
  datasets: Dataset[];
  error: string | null;
  setError: (e: string | null) => void;
  onImport: () => void;
  syncing: boolean;
}

export default function PredictionTab({ stations, station, datasets, error, setError, onImport, syncing }: Props) {
  const [observed, setObserved] = useState<TSPoint[]>([]);
  const [datasetId, setDatasetId] = useState<number | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioSeries[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!station) return;
    let cancelled = false;
    setScenarios([]);
    setObserved([]);
    setLoading(true);
    (async () => {
      let dsId = datasets.find((d) => d.series_type === "time" && d.source !== "thaiwater")?.id ?? null;
      if (station.external_id) {
        try {
          dsId = (await api.syncHistory(station.id, 7)).dataset_id;
        } catch {
          dsId = datasets.find((d) => d.source === "thaiwater")?.id ?? dsId;
        }
      }
      if (dsId == null || cancelled) return;
      const pts = await api.timeseries(dsId, station.id);
      if (!cancelled) { setDatasetId(dsId); setObserved(pts); }
    })()
      .catch(() => setError("Couldn't load readings for this station."))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [station?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const stats = useMemo(() => {
    const pts = observed.filter((p) => p.value != null) as { t: string; value: number }[];
    if (!pts.length) return null;
    const last = pts[pts.length - 1];
    const target = new Date(last.t).getTime() - 24 * 3.6e6;
    const dayAgo = pts.reduce((best, p) =>
      Math.abs(new Date(p.t).getTime() - target) < Math.abs(new Date(best.t).getTime() - target) ? p : best
    );
    return { now: last.value, at: last.t, delta: last.value - dayAgo.value };
  }, [observed]);

  async function runForecast() {
    if (!station || datasetId == null) return;
    setBusy(true);
    try {
      const scs = await api.runPrediction(datasetId, station.id, 48);
      setScenarios(await Promise.all(scs.map(async (s) => ({ name: s.name, points: await api.scenarioResults(s.id) }))));
      setError(null);
    } catch {
      setError("The forecast didn't run. Check the backend logs for details.");
    } finally {
      setBusy(false);
    }
  }

  if (!stations.length) {
    return (
      <>
        <aside className="rail">
          <section>
            <h2>No stations yet</h2>
            <p className="hint gap">Import every telemetry water-level station in Thailand from ThaiWater (HII). It takes a few seconds.</p>
            <button className="primary-btn" onClick={onImport} disabled={syncing}>
              {syncing ? "Importing stations…" : "Import stations"}
            </button>
          </section>
          {error && <div className="error" role="alert">{error}</div>}
        </aside>
        <section className="bottom"><div className="empty">Readings appear here once stations are imported.</div></section>
      </>
    );
  }

  const sit = station?.situation_level ? SITUATION[station.situation_level] : null;
  const unit = "m MSL";
  const now = stats?.now ?? station?.latest_value ?? null;
  const toBank = station?.min_bank != null && now != null ? station.min_bank - now : null;

  return (
    <>
      <aside className="rail">
        {station && (
          <section>
            <div className="readout-code">
              Station {station.code}
              {sit && <span className="pill" style={{ background: sit.color }}>{sit.label} ({sit.th})</span>}
            </div>
            <div className="readout-name">{station.name}</div>
            {now != null ? (
              <>
                <div className="readout-level">
                  <span className="readout-value">{now.toFixed(2)}</span>
                  <span className="readout-unit">{unit}</span>
                </div>
                <div className="readout-trend">
                  {stats && (
                    <span className={stats.delta >= 0 ? "trend-up" : "trend-down"}>
                      {stats.delta >= 0 ? "▲" : "▼"} {Math.abs(stats.delta).toFixed(2)} m in 24 h
                    </span>
                  )}
                </div>
                {toBank != null && (
                  <div className={`bank-gap ${toBank < 0 ? "over" : toBank < 1 ? "near" : ""}`}>
                    {toBank < 0
                      ? `${Math.abs(toBank).toFixed(2)} m above the bank`
                      : `${toBank.toFixed(2)} m below the bank`}
                  </div>
                )}
              </>
            ) : (
              <p className="hint">{loading ? "Loading readings…" : "No recent reading from this station."}</p>
            )}
          </section>
        )}

        {station && (
          <section>
            <h2>Station details</h2>
            <dl className="facts">
              <dt>River</dt><dd>{station.river ?? "–"}</dd>
              <dt>Location</dt><dd>{[station.tambon && `ต.${station.tambon}`, station.amphoe && `อ.${station.amphoe}`, station.province && `จ.${station.province}`].filter(Boolean).join(" ") || "–"}</dd>
              <dt>Basin</dt><dd>{station.basin ?? "–"}</dd>
              <dt>Operator</dt><dd>{station.agency ?? "–"}</dd>
              <dt>Bank level</dt><dd>{num(station.min_bank)} m <small>L {num(station.left_bank)} / R {num(station.right_bank)}</small></dd>
              <dt>Riverbed</dt><dd>{num(station.ground_level)} m</dd>
              {station.critical_level != null && (<><dt>Critical</dt><dd>{num(station.critical_level)} m</dd></>)}
              <dt>Channel full</dt><dd>{station.storage_percent != null ? `${station.storage_percent.toFixed(0)}%` : "–"}</dd>
              <dt>Last reading</dt><dd>{stats ? fmtTime(stats.at) : station.latest_time ? fmtTime(station.latest_time) : "–"}</dd>
              <dt>Position</dt><dd>{station.lat.toFixed(4)}, {station.lon.toFixed(4)}</dd>
            </dl>
          </section>
        )}

        {stats && (
          <section>
            <h2>48-hour outlook</h2>
            {scenarios.length ? (
              <ul className="outlook">
                {scenarios.map((s, i) => {
                  const peak = Math.max(...s.points.map((p) => p.value));
                  const [, label = s.name] = s.name.split(" – ");
                  const over = station?.min_bank != null && peak > station.min_bank;
                  return (
                    <li key={s.name}>
                      <span className="bar" style={{ background: SCENARIO_COLORS[i] }} />
                      <span className="label">
                        {label.charAt(0).toUpperCase() + label.slice(1)} case
                        <small>{over ? "Reaches the bank" : "Peak in 48 h"}</small>
                      </span>
                      <span className="peak">{peak.toFixed(2)}</span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="hint gap">Compare low, expected and high cases from the latest reading.</p>
            )}
            <button className="primary-btn" onClick={runForecast} disabled={busy}>
              {busy ? "Running forecast…" : scenarios.length ? "Run again" : "Run 48-hour forecast"}
            </button>
          </section>
        )}

        {error && <div className="error" role="alert">{error}</div>}
      </aside>

      <section className="bottom">
        <div className="bottom-head">
          <h2>Water level</h2>
          <span>{station ? `${station.code} ${station.name}, past 7 days${scenarios.length ? " and forecast" : ""}` : "Select a station"}</span>
        </div>
        <div className="bottom-body">
          {observed.length ? (
            <Timeline
              observed={observed} scenarios={scenarios} today={stats?.at ?? null} unit={unit}
              bank={station?.min_bank} critical={station?.critical_level}
            />
          ) : (
            <div className="empty">{loading ? "Fetching the last 7 days from ThaiWater…" : "No readings for this station in the last 7 days."}</div>
          )}
        </div>
      </section>
    </>
  );
}
