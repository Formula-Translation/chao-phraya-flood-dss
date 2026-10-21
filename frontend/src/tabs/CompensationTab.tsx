import { useState } from "react";
import { api, type Claim, type CompensationSummary, type Incident } from "../api";
import { CLAIM_STATUS, DAMAGE_TYPE, thb } from "../lookups";

interface Props {
  incidents: Incident[];
  claims: Claim[];
  summary: CompensationSummary | null;
  selectedIncident: number | null;
  onSelectIncident: (id: number) => void;
  reload: () => Promise<void>;
  error: string | null;
  setError: (e: string | null) => void;
}

const PIPE = ["submitted", "surveyed", "approved", "paid", "rejected"];

export default function CompensationTab(p: Props) {
  const { incidents, claims, summary, reload, error, setError } = p;
  const [filter, setFilter] = useState<number | "all">("all");
  const [form, setForm] = useState<null | { incident_id: number; claimant: string; village: string; damage_type: string; area_rai: number; estimated_thb: number }>(null);
  const [saving, setSaving] = useState(false);

  const incTitle = (id: number) => incidents.find((i) => i.id === id)?.title ?? `#${id}`;
  const shown = filter === "all" ? claims : claims.filter((c) => c.incident_id === filter);
  const pending = summary
    ? (summary.by_status.submitted?.estimated_thb ?? 0) + (summary.by_status.surveyed?.estimated_thb ?? 0)
    : 0;

  async function advance(c: Claim) {
    const next = CLAIM_STATUS[c.status]?.next;
    if (!next) return;
    const body: Partial<Claim> = { status: next };
    if (next === "approved" && c.approved_thb == null) body.approved_thb = c.estimated_thb;
    await api.updateClaim(c.id, body).catch(() => setError("Couldn't update the claim."));
    await reload();
  }

  async function reject(c: Claim) {
    await api.updateClaim(c.id, { status: "rejected" }).catch(() => setError("Couldn't update the claim."));
    await reload();
  }

  async function save() {
    if (!form || !form.claimant.trim()) return;
    setSaving(true);
    try {
      await api.createClaim({ ...form, village: form.village || null });
      await reload();
      setForm(null);
      setError(null);
    } catch {
      setError("The claim wasn't saved. Check the backend is running and try again.");
    } finally {
      setSaving(false);
    }
  }

  const total = summary?.claims || 0;

  return (
    <>
      <aside className="rail">
        {form ? (
          <section>
            <h2>New claim</h2>
            <div className="form">
              <label>Incident
                <select value={form.incident_id} onChange={(e) => setForm({ ...form, incident_id: Number(e.target.value) })}>
                  {incidents.map((i) => <option key={i.id} value={i.id}>{i.title}</option>)}
                </select>
              </label>
              <label>Claimant
                <input value={form.claimant} autoFocus placeholder="Name of household head"
                  onChange={(e) => setForm({ ...form, claimant: e.target.value })} />
              </label>
              <label>Village
                <input value={form.village} placeholder="e.g. หมู่ 4"
                  onChange={(e) => setForm({ ...form, village: e.target.value })} />
              </label>
              <label>Damage
                <select value={form.damage_type} onChange={(e) => setForm({ ...form, damage_type: e.target.value })}>
                  {Object.entries(DAMAGE_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <div className="form-row">
                <label>Area (rai)
                  <input type="number" min={0} value={form.area_rai} onChange={(e) => setForm({ ...form, area_rai: Number(e.target.value) })} />
                </label>
                <label>Estimated loss (฿)
                  <input type="number" min={0} step={100} value={form.estimated_thb} onChange={(e) => setForm({ ...form, estimated_thb: Number(e.target.value) })} />
                </label>
              </div>
              <div className="form-actions">
                <button className="primary-btn" onClick={save} disabled={saving || !form.claimant.trim()}>
                  {saving ? "Saving…" : "Save claim"}
                </button>
                <button className="ghost-btn" onClick={() => setForm(null)}>Cancel</button>
              </div>
            </div>
          </section>
        ) : (
          <>
            <section>
              <div className="readout-code">Total claimed</div>
              <div className="readout-level">
                <span className="readout-value money">{thb(summary?.estimated_thb ?? 0)}</span>
              </div>
              <div className="readout-trend">{total} claims from {incidents.length} incidents</div>
            </section>

            <section className="kpis">
              <div><b>{thb(pending)}</b><span>Waiting for survey or approval</span></div>
              <div><b>{thb(summary?.approved_thb ?? 0)}</b><span>Approved</span></div>
              <div><b>{thb(summary?.paid_thb ?? 0)}</b><span>Paid out</span></div>
            </section>

            {total > 0 && (
              <section>
                <h2>Claims by stage</h2>
                <div className="pipeline" aria-hidden>
                  {PIPE.map((s) => {
                    const n = summary?.by_status[s]?.count ?? 0;
                    return n ? <span key={s} style={{ flex: n, background: CLAIM_STATUS[s].color }} /> : null;
                  })}
                </div>
                <ul className="pipe-legend">
                  {PIPE.map((s) => (
                    <li key={s}>
                      <i style={{ background: CLAIM_STATUS[s].color }} />
                      {CLAIM_STATUS[s].label}
                      <b>{summary?.by_status[s]?.count ?? 0}</b>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <button
              className="primary-btn" disabled={!incidents.length}
              onClick={() => setForm({
                incident_id: p.selectedIncident ?? incidents[0]?.id, claimant: "", village: "",
                damage_type: "crops", area_rai: 0, estimated_thb: 0,
              })}
            >
              Add a claim
            </button>
            {!incidents.length && <p className="hint">Claims attach to an incident. Report one in the Incident tab first.</p>}
          </>
        )}
        {error && <div className="error" role="alert">{error}</div>}
      </aside>

      <section className="bottom">
        <div className="bottom-head">
          <h2>Claims</h2>
          <select
            className="filter" aria-label="Filter by incident" value={filter}
            onChange={(e) => {
              const v = e.target.value === "all" ? "all" : Number(e.target.value);
              setFilter(v);
              if (v !== "all") p.onSelectIncident(v);
            }}
          >
            <option value="all">All incidents</option>
            {incidents.map((i) => <option key={i.id} value={i.id}>{i.title}</option>)}
          </select>
          <span>{shown.length} shown</span>
        </div>
        <div className="bottom-body table-wrap">
          {shown.length ? (
            <table className="table">
              <thead>
                <tr><th>Claimant</th><th>Village</th>{filter === "all" && <th>Incident</th>}<th>Damage</th><th className="r">Rai</th><th className="r">Estimated</th><th className="r">Approved</th><th>Stage</th><th /></tr>
              </thead>
              <tbody>
                {shown.map((c) => {
                  const st = CLAIM_STATUS[c.status];
                  return (
                    <tr key={c.id}>
                      <td>{c.claimant}</td>
                      <td>{c.village ?? "–"}</td>
                      {filter === "all" && <td className="muted-cell">{incTitle(c.incident_id)}</td>}
                      <td>{DAMAGE_TYPE[c.damage_type] ?? c.damage_type}</td>
                      <td className="r">{c.area_rai ?? "–"}</td>
                      <td className="r">{thb(c.estimated_thb)}</td>
                      <td className="r">{thb(c.approved_thb)}</td>
                      <td><span className="stage" style={{ color: st?.color, borderColor: st?.color }}>{st?.label ?? c.status}</span></td>
                      <td className="actions"><div>
                        {st?.action && <button className="ghost-btn small" onClick={() => advance(c)}>{st.action}</button>}
                        {(c.status === "submitted" || c.status === "surveyed") && (
                          <button className="link-btn" onClick={() => reject(c)}>Reject</button>
                        )}
                      </div></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="empty">No claims yet{filter !== "all" ? " for this incident" : ""}.</div>
          )}
        </div>
      </section>
    </>
  );
}
