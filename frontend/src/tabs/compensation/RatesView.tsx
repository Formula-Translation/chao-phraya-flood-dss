import { useState } from "react";
import { api, type Rate } from "../../api";
import { CATEGORY, thb, UNIT } from "../../lookups";

interface Props {
  rates: Rate[];
  provinces: string[];
  reload: () => Promise<void>;
  setError: (e: string | null) => void;
}

/** Number cell that saves when you leave it or press Enter. */
function NumCell({ value, onSave, suffix }: { value: number | null; onSave: (v: number | null) => void; suffix?: string }) {
  const [v, setV] = useState(value == null ? "" : String(value));
  const commit = () => {
    const n = v.trim() === "" ? null : Number(v);
    if (n !== value && (n == null || !Number.isNaN(n))) onSave(n);
  };
  return (
    <span className="num-cell">
      <input
        value={v} inputMode="decimal" aria-label="Edit value"
        onChange={(e) => setV(e.target.value)} onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      />
      {suffix && <small>{suffix}</small>}
    </span>
  );
}

export default function RatesView({ rates, provinces, reload, setError }: Props) {
  const national = rates.filter((r) => !r.province);
  const [form, setForm] = useState({ province: provinces[0] ?? "", damage_type: national[0]?.damage_type ?? "rice", rate: "" });

  const save = async (r: Rate, patch: Partial<Rate>) => {
    try {
      await api.updateRate(r.id, patch);
      await reload();
    } catch {
      setError("The rate wasn't saved.");
    }
  };

  const add = async () => {
    const base = national.find((r) => r.damage_type === form.damage_type);
    if (!base || !form.province) return;
    const n = form.rate.trim() === "" ? null : Number(form.rate);
    try {
      await api.addRateOverride({
        damage_type: form.damage_type, province: form.province,
        ...(base.rate_thb == null ? { max_thb: n } : { rate_thb: n }),
      });
      setForm({ ...form, rate: "" });
      await reload();
      setError(null);
    } catch (e) {
      setError(String(e).includes("409") ? `${form.province} already has its own rate for that type.` : "The provincial rate wasn't added.");
    }
  };

  const remove = async (r: Rate) => {
    await api.deleteRate(r.id);
    await reload();
  };

  const groups = Object.keys(CATEGORY).map((cat) => ({ cat, rows: rates.filter((r) => r.category === cat) }));

  return (
    <div className="rates">
      <table className="table">
        <thead>
          <tr>
            <th>Damage type</th><th>Region</th><th className="r">Rate</th><th className="r">Household limit</th>
            <th className="r">Amount cap</th><th>Source</th><th />
          </tr>
        </thead>
        {groups.map(({ cat, rows }) =>
          rows.length ? (
            <tbody key={cat}>
              <tr className="group-row"><td colSpan={7}>{CATEGORY[cat]}</td></tr>
              {rows.map((r) => {
                const u = UNIT[r.unit]?.short ?? r.unit;
                return (
                  <tr key={r.id} className={r.province ? "override" : ""}>
                    <td>{r.province ? <span className="muted">↳ </span> : null}{r.label}</td>
                    <td>{r.province ?? "National"}</td>
                    <td className="r">
                      {r.rate_thb != null
                        ? <NumCell key={`${r.id}-rate-${r.rate_thb}`} value={r.rate_thb} suffix={`฿/${u}`} onSave={(v) => save(r, { rate_thb: v })} />
                        : <span className="muted">lump sum</span>}
                    </td>
                    <td className="r">
                      {r.rate_thb != null
                        ? <NumCell key={`${r.id}-max-${r.max_units}`} value={r.max_units} suffix={u} onSave={(v) => save(r, { max_units: v })} />
                        : "–"}
                    </td>
                    <td className="r">
                      {r.rate_thb == null
                        ? <NumCell key={`${r.id}-cap-${r.max_thb}`} value={r.max_thb} suffix="฿" onSave={(v) => save(r, { max_thb: v })} />
                        : r.max_thb != null ? thb(r.max_thb) : "–"}
                    </td>
                    <td className="muted-cell source" title={r.source ?? ""}>{r.source ?? "–"}</td>
                    <td className="actions">
                      <div>{r.province && <button className="link-btn" onClick={() => remove(r)}>Remove</button>}</div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          ) : null
        )}
      </table>

      <div className="override-form">
        <span>Add a provincial rate</span>
        <select aria-label="Province" value={form.province} onChange={(e) => setForm({ ...form, province: e.target.value })}>
          {provinces.map((p) => <option key={p}>{p}</option>)}
        </select>
        <select aria-label="Damage type" value={form.damage_type} onChange={(e) => setForm({ ...form, damage_type: e.target.value })}>
          {national.map((r) => <option key={r.id} value={r.damage_type}>{r.label}</option>)}
        </select>
        <input
          aria-label="Rate" placeholder={(() => {
            const b = national.find((r) => r.damage_type === form.damage_type);
            return b?.rate_thb != null ? `฿ per ${UNIT[b.unit]?.short ?? b.unit}` : "Cap in ฿";
          })()}
          inputMode="decimal" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })}
        />
        <button className="ghost-btn small" onClick={add} disabled={!form.province || !form.rate.trim()}>Add</button>
      </div>
      <p className="hint rates-note">
        Defaults: MOAC farmer assistance criteria effective 21 Aug 2026 and the MOF 2025 advance-fund regulation.
        Check against the official announcement before using them for payments. A provincial rate replaces the national one for claims in that province.
      </p>
    </div>
  );
}
