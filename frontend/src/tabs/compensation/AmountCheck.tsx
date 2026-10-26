import type { Assessment } from "../../api";
import { qty, thb, UNIT } from "../../lookups";

interface Props {
  claimed: number;
  approved: number | null;
  a: Assessment;
}

/** Where the claimed amount sits against the typical regional range and the official maximum. */
export default function AmountCheck({ claimed, approved, a }: Props) {
  const lo = a.expected_low_thb;
  const hi = a.expected_high_thb;
  const max = a.official_max_thb;
  const top = Math.max(claimed, max ?? 0, hi ?? 0, approved ?? 0) * 1.12 || 1;
  const pct = (v: number) => `${Math.min(100, (v / top) * 100)}%`;
  const over = max != null && claimed > max * 1.001;
  const unit = a.rate ? UNIT[a.rate.unit]?.short ?? a.rate.unit : "";
  const perUnit = a.rate?.rate_thb != null;

  return (
    <div className="amount">
      <div className="amount-track" aria-hidden>
        {lo != null && hi != null && (
          <span className="amount-band" style={{ left: pct(lo), width: `calc(${pct(hi)} - ${pct(lo)} + 2px)` }} />
        )}
        {max != null && <span className="amount-limit" style={{ left: pct(max) }} />}
        <span className={`amount-dot ${over ? "over" : ""}`} style={{ left: pct(claimed) }} />
      </div>
      <dl className="amount-legend">
        <dt><i className={`key dot ${over ? "over" : ""}`} />Claimed</dt>
        <dd className={over ? "over" : ""}>{thb(claimed)}</dd>
        {approved != null && (<><dt><i className="key none" />Approved</dt><dd>{thb(approved)}</dd></>)}
        <dt><i className="key band" />Typical{a.peer_group === "all provinces" ? " across provinces" : a.peer_group ? ` in ${a.peer_group}` : ""}</dt>
        <dd>{lo != null && hi != null ? (Math.round(lo) === Math.round(hi) ? thb(lo) : `${thb(lo)} – ${thb(hi)}`) : "Not enough claims yet"}</dd>
        <dt><i className="key limit" />Official maximum</dt>
        <dd>{thb(max)}</dd>
      </dl>
      {a.rate && (
        <p className="hint">
          {perUnit
            ? `${qty(a.eligible_quantity)} ${unit} × ${thb(a.rate.rate_thb)}/${unit}`
            : `Capped at ${thb(a.rate.max_thb)} per ${unit}`}
          {a.rate_region === "national" ? ", national rate" : `, ${a.rate_region} rate`}
          {a.peer_count >= 5 && `. Typical range from ${a.peer_count} similar claims.`}
        </p>
      )}
    </div>
  );
}
