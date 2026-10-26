import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api, type Assessment, type AssessmentSummary, type Claim, type CompensationSummary, type Incident,
  type Photo, type Rate,
} from "../api";
import type { PhotoPoint } from "../components/MapView";
import { CATEGORY, CLAIM_STATUS, DAMAGE_TYPE, qty, RISK, thb, UNIT } from "../lookups";
import ClaimDetail from "./compensation/ClaimDetail";
import RatesView from "./compensation/RatesView";

interface Props {
  incidents: Incident[];
  claims: Claim[];
  summary: CompensationSummary | null;
  provinces: string[];
  selectedIncident: number | null;
  onSelectIncident: (id: number) => void;
  setPhotoPoints: (p: PhotoPoint[]) => void;
  reload: () => Promise<void>;
  error: string | null;
  setError: (e: string | null) => void;
}

const PIPE = ["submitted", "surveyed", "approved", "paid", "rejected"];
type Check = "all" | "flagged" | "high";
interface Form { incident_id: number; claimant: string; village: string; damage_type: string; amount: number; estimated_thb: number }

export default function CompensationTab(p: Props) {
  const { incidents, claims, summary, reload, error, setError, setPhotoPoints } = p;
  const [view, setView] = useState<"claims" | "rates">("claims");
  const [filter, setFilter] = useState<number | "all">("all");
  const [check, setCheck] = useState<Check>("all");
  const [sortRisk, setSortRisk] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [assess, setAssess] = useState<Record<number, AssessmentSummary>>({});
  const [detail, setDetail] = useState<Assessment | null>(null);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [rates, setRates] = useState<Rate[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const loadAssessments = useCallback(async () => {
    const list = await api.assessments();
    setAssess(Object.fromEntries(list.map((a) => [a.claim_id, a])));
  }, []);
  const loadRates = useCallback(async () => setRates(await api.rates()), []);
  const loadDetail = useCallback(async (id: number) => {
    const [a, ph] = await Promise.all([api.assessment(id), api.photos(id)]);
    setDetail(a);
    setPhotos(ph);
  }, []);

  useEffect(() => { loadAssessments().catch(() => setError("Couldn't load claim checks.")); }, [claims]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadRates().catch(() => null); }, [loadRates]);
  useEffect(() => {
    if (selected == null) { setDetail(null); setPhotos([]); return; }
    loadDetail(selected).catch(() => setError("Couldn't load the claim."));
  }, [selected, claims, loadDetail]); // eslint-disable-line react-hooks/exhaustive-deps

  // photo locations on the map
  useEffect(() => {
    const flagged = new Set(detail?.flag_list.filter((f) => f.photo_id && f.level !== "info").map((f) => f.photo_id));
    setPhotoPoints(
      photos.filter((ph) => ph.lat != null && ph.lon != null).map((ph) => ({
        id: ph.id, lon: ph.lon!, lat: ph.lat!, flagged: flagged.has(ph.id),
        label: `<b>${ph.filename}</b><br>${ph.distance_km != null ? `${ph.distance_km.toFixed(1)} km from the incident` : ""}`,
      }))
    );
  }, [photos, detail, setPhotoPoints]);
  useEffect(() => () => setPhotoPoints([]), [setPhotoPoints]);

  const claim = claims.find((c) => c.id === selected);
  const select = (c: Claim) => { setSelected(c.id); setForm(null); p.onSelectIncident(c.incident_id); };

  const incTitle = (id: number) => incidents.find((i) => i.id === id)?.title ?? `#${id}`;
  const shown = useMemo(() => {
    let list = filter === "all" ? claims : claims.filter((c) => c.incident_id === filter);
    if (check === "flagged") list = list.filter((c) => assess[c.id] && assess[c.id].level !== "ok");
    if (check === "high") list = list.filter((c) => assess[c.id]?.level === "high");
    if (sortRisk) list = [...list].sort((a, b) => (assess[b.id]?.score ?? 0) - (assess[a.id]?.score ?? 0));
    return list;
  }, [claims, filter, check, sortRisk, assess]);

  const counts = useMemo(() => {
    const v = Object.values(assess);
    return { high: v.filter((a) => a.level === "high").length, review: v.filter((a) => a.level === "review").length };
  }, [assess]);
  const pending = summary
    ? (summary.by_status.submitted?.estimated_thb ?? 0) + (summary.by_status.surveyed?.estimated_thb ?? 0)
    : 0;

  async function advance(c: Claim) {
    const next = CLAIM_STATUS[c.status]?.next;
    if (!next) return;
    const body: Partial<Claim> = { status: next };
    if (next === "approved" && c.approved_thb == null) {
      // approve the claimed amount, but never above the official maximum
      const max = selected === c.id ? detail?.official_max_thb : null;
      body.approved_thb = max != null ? Math.min(c.estimated_thb, max) : c.estimated_thb;
    }
    await api.updateClaim(c.id, body).catch(() => setError("Couldn't update the claim."));
    await reload();
  }

  async function reject(c: Claim) {
    await api.updateClaim(c.id, { status: "rejected" }).catch(() => setError("Couldn't update the claim."));
    await reload();
  }

  async function upload(files: File[]) {
    if (selected == null) return;
    setUploading(true);
    try {
      await api.uploadPhotos(selected, files);
      await Promise.all([loadDetail(selected), loadAssessments()]);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The photos weren't uploaded.");
    } finally {
      setUploading(false);
    }
  }

  async function deletePhoto(id: number) {
    if (selected == null) return;
    await api.deletePhoto(id);
    await Promise.all([loadDetail(selected), loadAssessments()]);
  }

  async function save() {
    if (!form || !form.claimant.trim()) return;
    const rate = rates.find((r) => r.damage_type === form.damage_type && !r.province);
    setSaving(true);
    try {
      const c = await api.createClaim({
        incident_id: form.incident_id, claimant: form.claimant, village: form.village || null,
        damage_type: form.damage_type, estimated_thb: form.estimated_thb,
        ...(rate?.unit === "rai" ? { area_rai: form.amount } : { units: rate?.rate_thb == null ? 1 : form.amount }),
      });
      await reload();
      setForm(null);
      setSelected(c.id);
      setError(null);
    } catch {
      setError("The claim wasn't saved. Check the backend is running and try again.");
    } finally {
      setSaving(false);
    }
  }

  // live "up to ฿…" hint while entering a claim
  const formRate = form ? rates.find((r) => r.damage_type === form.damage_type && !r.province) : undefined;
  const formMax = formRate
    ? formRate.rate_thb == null
      ? formRate.max_thb
      : Math.min(form!.amount, formRate.max_units ?? Infinity) * formRate.rate_thb
    : null;
  const nationalRates = rates.filter((r) => !r.province);
  const total = summary?.claims || 0;

  return (
    <>
      <aside className="rail">
        {claim ? (
          <ClaimDetail
            claim={claim} incident={incidents.find((i) => i.id === claim.incident_id)} assessment={detail} photos={photos}
            uploading={uploading} onBack={() => setSelected(null)} onAdvance={() => advance(claim)} onReject={() => reject(claim)}
            onUpload={upload} onDeletePhoto={deletePhoto}
          />
        ) : form ? (
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
                <input value={form.village} placeholder="e.g. หมู่ 4" onChange={(e) => setForm({ ...form, village: e.target.value })} />
              </label>
              <label>Damage
                <select value={form.damage_type} onChange={(e) => setForm({ ...form, damage_type: e.target.value })}>
                  {Object.entries(CATEGORY).map(([cat, label]) => (
                    <optgroup key={cat} label={label}>
                      {nationalRates.filter((r) => r.category === cat).map((r) => <option key={r.id} value={r.damage_type}>{r.label}</option>)}
                    </optgroup>
                  ))}
                </select>
              </label>
              <div className="form-row">
                {formRate && UNIT[formRate.unit]?.field && (
                  <label>{UNIT[formRate.unit].field}
                    <input type="number" min={0} step="any" value={form.amount}
                      onChange={(e) => setForm({ ...form, amount: Number(e.target.value) })} />
                  </label>
                )}
                <label>Estimated loss (฿)
                  <input type="number" min={0} step={100} value={form.estimated_thb}
                    onChange={(e) => setForm({ ...form, estimated_thb: Number(e.target.value) })} />
                </label>
              </div>
              {formRate && (
                <p className={`hint ${formMax != null && form.estimated_thb > formMax ? "warn" : ""}`}>
                  {formRate.rate_thb != null
                    ? `Official rate ${thb(formRate.rate_thb)}/${UNIT[formRate.unit]?.short}, up to ${qty(formRate.max_units)} ${UNIT[formRate.unit]?.short}. `
                    : ""}
                  Maximum payable {thb(formMax)}.
                </p>
              )}
              <div className="form-actions">
                <button className="primary-btn" onClick={save} disabled={saving || !form.claimant.trim()}>
                  {saving ? "Saving…" : "Save claim"}
                </button>
                <button className="ghost-btn" onClick={() => setForm(null)}>Cancel</button>
              </div>
              <p className="hint">You can add photos after saving.</p>
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

            {total > 0 && (
              <button className="review-callout" onClick={() => { setView("claims"); setCheck("flagged"); setSortRisk(true); }}>
                <b>{counts.high + counts.review} claims need a closer look</b>
                <span>
                  <i style={{ background: RISK.high.color }} />{counts.high} high risk
                  <i style={{ background: "#d39a12" }} />{counts.review} to review
                </span>
              </button>
            )}

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
                    <li key={s}><i style={{ background: CLAIM_STATUS[s].color }} />{CLAIM_STATUS[s].label}<b>{summary?.by_status[s]?.count ?? 0}</b></li>
                  ))}
                </ul>
              </section>
            )}

            <button
              className="primary-btn" disabled={!incidents.length}
              onClick={() => setForm({
                incident_id: p.selectedIncident ?? incidents[0]?.id, claimant: "", village: "",
                damage_type: "rice", amount: 0, estimated_thb: 0,
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
          <div className="segmented-sm" role="tablist" aria-label="View">
            <button role="tab" aria-selected={view === "claims"} className={view === "claims" ? "on" : ""} onClick={() => setView("claims")}>Claims</button>
            <button role="tab" aria-selected={view === "rates"} className={view === "rates" ? "on" : ""} onClick={() => setView("rates")}>Rates</button>
          </div>
          {view === "claims" && (
            <>
              <select className="filter" aria-label="Filter by incident" value={filter}
                onChange={(e) => {
                  const v = e.target.value === "all" ? "all" : Number(e.target.value);
                  setFilter(v);
                  if (v !== "all") p.onSelectIncident(v);
                }}>
                <option value="all">All incidents</option>
                {incidents.map((i) => <option key={i.id} value={i.id}>{i.title}</option>)}
              </select>
              <select className="filter" aria-label="Filter by check result" value={check} onChange={(e) => setCheck(e.target.value as Check)}>
                <option value="all">All checks</option>
                <option value="flagged">Needs a look</option>
                <option value="high">High risk only</option>
              </select>
              <label className="toggle">
                <input type="checkbox" checked={sortRisk} onChange={(e) => setSortRisk(e.target.checked)} /> Riskiest first
              </label>
              <span>{shown.length} shown</span>
            </>
          )}
          {view === "rates" && <span>Official assistance rates used for the amount check</span>}
        </div>
        <div className="bottom-body table-wrap">
          {view === "rates" ? (
            <RatesView rates={rates} provinces={p.provinces} setError={setError}
              reload={async () => { await loadRates(); await loadAssessments(); if (selected) await loadDetail(selected); }} />
          ) : shown.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Check</th><th>Claimant</th><th>Village</th>{filter === "all" && <th>Incident</th>}<th>Damage</th>
                  <th className="r">Area / qty</th><th className="r">Claimed</th><th className="r">Approved</th><th>Stage</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((c) => {
                  const st = CLAIM_STATUS[c.status];
                  const a = assess[c.id];
                  const risk = a ? RISK[a.level] : null;
                  const q = c.area_rai ?? c.units;
                  return (
                    <tr key={c.id} className={`clickable ${c.id === selected ? "sel" : ""}`} onClick={() => select(c)}>
                      <td>
                        {risk && (
                          <span className="risk-badge" style={{ color: risk.color, background: risk.bg }} title={a?.top_flag ?? ""}>
                            {risk.label}
                          </span>
                        )}
                      </td>
                      <td><button className="row-link" onClick={(e) => { e.stopPropagation(); select(c); }}>{c.claimant}</button></td>
                      <td>{c.village ?? "–"}</td>
                      {filter === "all" && <td className="muted-cell">{incTitle(c.incident_id)}</td>}
                      <td>{DAMAGE_TYPE[c.damage_type] ?? c.damage_type}</td>
                      <td className="r">{q != null ? `${qty(q)}${c.area_rai != null ? " rai" : ""}` : "–"}</td>
                      <td className="r">{thb(c.estimated_thb)}</td>
                      <td className="r">{thb(c.approved_thb)}</td>
                      <td><span className="stage" style={{ color: st?.color, borderColor: st?.color }}>{st?.label ?? c.status}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="empty">
              {claims.length ? "No claims match these filters." : "No claims yet."}
              {!claims.length && (
                <button className="ghost-btn small" onClick={() => api.seedResponse().then(reload)}>Load sample claims</button>
              )}
            </div>
          )}
        </div>
      </section>
    </>
  );
}
