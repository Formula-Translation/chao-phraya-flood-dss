import { useRef, useState } from "react";
import { fileUrl, type Assessment, type Claim, type Incident, type Photo } from "../../api";
import { CLAIM_STATUS, DAMAGE_TYPE, FLAG_COLOR, fmtDate, qty, RISK, UNIT } from "../../lookups";
import AmountCheck from "./AmountCheck";

interface Props {
  claim: Claim;
  incident: Incident | undefined;
  assessment: Assessment | null;
  photos: Photo[];
  uploading: boolean;
  onBack: () => void;
  onAdvance: () => void;
  onReject: () => void;
  onUpload: (files: File[]) => void;
  onDeletePhoto: (id: number) => void;
}

export default function ClaimDetail(p: Props) {
  const { claim: c, assessment: a, photos } = p;
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const st = CLAIM_STATUS[c.status];
  const risk = a ? RISK[a.level] : null;
  const issues = a?.flag_list.filter((f) => f.level !== "info") ?? [];
  const notes = a?.flag_list.filter((f) => f.level === "info") ?? [];
  const photoLevel = (id: number) => {
    const fs = a?.flag_list.filter((f) => f.photo_id === id) ?? [];
    return fs.some((f) => f.level === "high") ? "high" : fs.some((f) => f.level === "review") ? "review" : null;
  };
  const unit = a?.rate ? UNIT[a.rate.unit]?.short : null;
  const amountShown = a?.rate?.unit === "rai" ? c.area_rai : c.units;

  const pickFiles = (list: FileList | null) => {
    const files = Array.from(list ?? []).filter((f) => f.type.startsWith("image/") || /\.(heic|heif)$/i.test(f.name));
    if (files.length) p.onUpload(files);
  };

  return (
    <>
      <button className="back-link" onClick={p.onBack}>← All claims</button>

      <section>
        <div className="readout-code">
          Claim #{c.id}
          <span className="stage" style={{ color: st?.color, borderColor: st?.color }}>{st?.label ?? c.status}</span>
        </div>
        <div className="claim-head">
          <div className="readout-name">{c.claimant}</div>
          {risk && a && (
            <span className="risk-badge big" style={{ color: risk.color, background: risk.bg }} title={`Score ${a.score} of 100`}>
              {risk.label}
            </span>
          )}
        </div>
        <p className="claim-meta">
          {DAMAGE_TYPE[c.damage_type] ?? c.damage_type}
          {amountShown != null && unit && a?.rate?.rate_thb != null ? `, ${qty(amountShown)} ${unit}` : ""}
          <br />
          {[c.village, c.amphoe && `อ.${c.amphoe}`, c.province && `จ.${c.province}`].filter(Boolean).join(" ")}
          {p.incident && <><br /><span className="muted">{p.incident.title}</span></>}
        </p>
      </section>

      {a && (
        <section>
          <h2>Amount check</h2>
          <AmountCheck claimed={c.estimated_thb} approved={c.approved_thb} a={a} />
        </section>
      )}

      {a && (
        <section>
          <h2>{issues.length ? `${issues.length} issue${issues.length > 1 ? "s" : ""} to check` : "Checks"}</h2>
          {!issues.length && <p className="hint">Amount, region comparison and evidence look consistent.</p>}
          <ul className="flags">
            {issues.map((f, i) => (
              <li key={i}>
                <i style={{ background: FLAG_COLOR[f.level] }} />
                <div><b>{f.title}</b><span>{f.detail}</span></div>
              </li>
            ))}
          </ul>
          {notes.length > 0 && (
            <details className="notes">
              <summary>{notes.length} note{notes.length > 1 ? "s" : ""}</summary>
              <ul className="flags">
                {notes.map((f, i) => (
                  <li key={i}>
                    <i style={{ background: FLAG_COLOR.info }} />
                    <div><b>{f.title}</b><span>{f.detail}</span></div>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}

      <section
        className={`photos ${dragging ? "drop" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); pickFiles(e.dataTransfer.files); }}
      >
        <div className="section-head">
          <h2>Photos{photos.length ? ` (${photos.length})` : ""}</h2>
          <button className="ghost-btn small" onClick={() => input.current?.click()} disabled={p.uploading}>
            {p.uploading ? "Uploading…" : "Add photos"}
          </button>
          <input
            ref={input} type="file" accept="image/*,.heic,.heif" multiple hidden
            onChange={(e) => { pickFiles(e.target.files); e.target.value = ""; }}
          />
        </div>
        {photos.length ? (
          <ul className="photo-grid">
            {photos.map((ph) => {
              const lvl = photoLevel(ph.id);
              return (
                <li key={ph.id} className={lvl ? `flag-${lvl}` : ""}>
                  <a href={fileUrl(ph.url)} target="_blank" rel="noreferrer" title={ph.filename}>
                    <img src={fileUrl(ph.thumb_url)} alt={`Damage photo ${ph.filename}`} loading="lazy" />
                  </a>
                  <button className="photo-del" aria-label={`Remove ${ph.filename}`} onClick={() => p.onDeletePhoto(ph.id)}>×</button>
                  <span className="photo-cap">
                    {ph.taken_at ? fmtDate(ph.taken_at) : "No date"}
                    <br />
                    {ph.distance_km != null ? `${ph.distance_km < 1 ? "<1" : Math.round(ph.distance_km)} km from flood` : "No location"}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="hint">Drop photos here or use Add photos. The time and GPS position saved by the camera are checked against the incident.</p>
        )}
      </section>

      {(st?.action || c.status === "submitted" || c.status === "surveyed") && (
        <div className="form-actions">
          {st?.action && <button className="primary-btn" onClick={p.onAdvance}>{st.action}</button>}
          {(c.status === "submitted" || c.status === "surveyed") && (
            <button className="ghost-btn" onClick={p.onReject}>Reject</button>
          )}
        </div>
      )}
    </>
  );
}
