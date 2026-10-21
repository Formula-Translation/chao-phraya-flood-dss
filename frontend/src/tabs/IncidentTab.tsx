import { useState } from "react";
import { api, type Claim, type Incident, type Station } from "../api";
import type { Pick } from "../App";
import { ago, fmtTime, INCIDENT_KIND, INCIDENT_STATUS, SEVERITY } from "../lookups";

interface Props {
  incidents: Incident[];
  claims: Claim[];
  station: Station | undefined;
  selectedId: number | null;
  onSelect: (id: number) => void;
  reload: () => Promise<void>;
  pick: Pick | null;
  setPick: (p: Pick | null) => void;
  error: string | null;
  setError: (e: string | null) => void;
}

const EMPTY = { title: "", kind: "inundation", severity: 2, households_affected: 0, area_rai: 0, description: "" };

export default function IncidentTab(p: Props) {
  const { incidents, selectedId, onSelect, reload, setPick, error, setError } = p;
  const [form, setForm] = useState<typeof EMPTY | null>(null);
  const [point, setPoint] = useState<[number, number] | null>(null);
  const [saving, setSaving] = useState(false);
  const sel = incidents.find((i) => i.id === selectedId);

  const startForm = () => {
    setForm({ ...EMPTY });
    const pt: [number, number] | null = p.station ? [p.station.lon, p.station.lat] : null;
    setPoint(pt);
    armPick(pt);
  };
  const armPick = (pt: [number, number] | null) =>
    setPick({ point: pt, onPick: (lon, lat) => { setPoint([lon, lat]); armPick([lon, lat]); } });
  const closeForm = () => { setForm(null); setPick(null); };

  async function save() {
    if (!form || !form.title.trim()) return;
    setSaving(true);
    try {
      const inc = await api.createIncident({
        ...form, status: "active",
        lon: point?.[0] ?? null, lat: point?.[1] ?? null,
        province: p.station?.province ?? null, amphoe: p.station?.amphoe ?? null,
      });
      await reload();
      onSelect(inc.id);
      closeForm();
      setError(null);
    } catch {
      setError("The incident wasn't saved. Check the backend is running and try again.");
    } finally {
      setSaving(false);
    }
  }

  async function setStatus(status: string) {
    if (!sel) return;
    await api.updateIncident(sel.id, { status }).catch(() => setError("Couldn't update the incident."));
    await reload();
  }

  const active = incidents.filter((i) => i.status !== "closed");
  const totals = active.reduce((a, i) => ({ hh: a.hh + i.households_affected, rai: a.rai + i.area_rai }), { hh: 0, rai: 0 });

  return (
    <>
      <aside className="rail">
        {form ? (
          <section>
            <h2>Report an incident</h2>
            <div className="form">
              <label>What happened
                <input value={form.title} autoFocus placeholder="e.g. Bank overflow at Wat Ko market"
                  onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </label>
              <label>Type
                <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                  {Object.entries(INCIDENT_KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <fieldset>
                <legend>Severity</legend>
                <div className="segmented">
                  {Object.entries(SEVERITY).map(([k, v]) => (
                    <button type="button" key={k} className={form.severity === Number(k) ? "on" : ""}
                      style={form.severity === Number(k) ? { background: v.color, borderColor: v.color } : undefined}
                      onClick={() => setForm({ ...form, severity: Number(k) })}>{v.label}</button>
                  ))}
                </div>
              </fieldset>
              <div className="form-row">
                <label>Households affected
                  <input type="number" min={0} value={form.households_affected}
                    onChange={(e) => setForm({ ...form, households_affected: Number(e.target.value) })} />
                </label>
                <label>Area flooded (rai)
                  <input type="number" min={0} value={form.area_rai}
                    onChange={(e) => setForm({ ...form, area_rai: Number(e.target.value) })} />
                </label>
              </div>
              <label>Notes
                <textarea rows={3} value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </label>
              <p className="hint">
                {point ? `Location ${point[1].toFixed(4)}, ${point[0].toFixed(4)}. Click the map to move it.` : "Click the map to set the location."}
              </p>
              <div className="form-actions">
                <button className="primary-btn" onClick={save} disabled={saving || !form.title.trim()}>
                  {saving ? "Saving…" : "Save incident"}
                </button>
                <button className="ghost-btn" onClick={closeForm}>Cancel</button>
              </div>
            </div>
          </section>
        ) : (
          <>
            <section className="kpis">
              <div><b>{active.length}</b><span>Open incidents</span></div>
              <div><b>{totals.hh.toLocaleString()}</b><span>Households affected</span></div>
              <div><b>{Math.round(totals.rai).toLocaleString()}</b><span>Rai flooded</span></div>
            </section>
            <button className="primary-btn" onClick={startForm}>Report an incident</button>

            {sel ? (
              <section>
                <div className="readout-code">
                  {INCIDENT_KIND[sel.kind] ?? sel.kind}
                  <span className="pill" style={{ background: SEVERITY[sel.severity]?.color }}>{SEVERITY[sel.severity]?.label}</span>
                </div>
                <div className="readout-name">{sel.title}</div>
                {sel.description && <p className="body-text">{sel.description}</p>}
                <dl className="facts">
                  <dt>Status</dt><dd>{INCIDENT_STATUS[sel.status] ?? sel.status}</dd>
                  <dt>Where</dt><dd>{[sel.amphoe && `อ.${sel.amphoe}`, sel.province && `จ.${sel.province}`].filter(Boolean).join(" ") || "–"}</dd>
                  <dt>Started</dt><dd>{fmtTime(sel.started_at)} <small>{ago(sel.started_at)}</small></dd>
                  {sel.ended_at && (<><dt>Closed</dt><dd>{fmtTime(sel.ended_at)}</dd></>)}
                  <dt>Households</dt><dd>{sel.households_affected.toLocaleString()}</dd>
                  <dt>Area</dt><dd>{sel.area_rai.toLocaleString()} rai</dd>
                  <dt>Claims</dt><dd>{sel.claims}</dd>
                </dl>
                <div className="form-actions">
                  {sel.status === "active" && <button className="ghost-btn" onClick={() => setStatus("receding")}>Mark receding</button>}
                  {sel.status !== "closed" && <button className="ghost-btn" onClick={() => setStatus("closed")}>Close incident</button>}
                  {sel.status === "closed" && <button className="ghost-btn" onClick={() => setStatus("active")}>Reopen</button>}
                </div>
              </section>
            ) : (
              <p className="hint">Select an incident on the map or in the table.</p>
            )}
          </>
        )}
        {error && <div className="error" role="alert">{error}</div>}
      </aside>

      <section className="bottom">
        <div className="bottom-head">
          <h2>Incidents</h2>
          <span>{incidents.length} recorded, most severe first</span>
          {!incidents.length && (
            <button className="ghost-btn small push" onClick={() => api.seedResponse().then(reload)}>Load sample incidents</button>
          )}
        </div>
        <div className="bottom-body table-wrap">
          {incidents.length ? (
            <table className="table">
              <thead>
                <tr><th>Incident</th><th>Severity</th><th>Status</th><th>Province</th><th className="r">Households</th><th className="r">Rai</th><th className="r">Claims</th><th>Started</th></tr>
              </thead>
              <tbody>
                {incidents.map((i) => (
                  <tr key={i.id} className={i.id === selectedId ? "sel" : ""} onClick={() => onSelect(i.id)}>
                    <td><button className="row-link" onClick={() => onSelect(i.id)}>{i.title}</button></td>
                    <td><span className="sev"><i style={{ background: SEVERITY[i.severity]?.color }} />{SEVERITY[i.severity]?.label}</span></td>
                    <td>{INCIDENT_STATUS[i.status] ?? i.status}</td>
                    <td>{i.province ?? "–"}</td>
                    <td className="r">{i.households_affected.toLocaleString()}</td>
                    <td className="r">{i.area_rai.toLocaleString()}</td>
                    <td className="r">{i.claims}</td>
                    <td>{ago(i.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty">No incidents recorded. Report one when flooding starts.</div>
          )}
        </div>
      </section>
    </>
  );
}
