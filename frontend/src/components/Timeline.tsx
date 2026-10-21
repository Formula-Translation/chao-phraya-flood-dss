import {
  CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { TSPoint } from "../api";

export interface ScenarioSeries {
  name: string;
  points: { t: string; value: number }[];
}

interface Props {
  observed: TSPoint[];
  scenarios: ScenarioSeries[];
  today: string | null;
  unit?: string | null;
  bank?: number | null;
  critical?: number | null;
}

export const SCENARIO_COLORS = ["#5f9a6b", "#d39a12", "#b8323a"];
const INK = "#17323a";
const MUTED = "#8a9a9c";

const fmtTick = (ms: number) =>
  new Date(ms).toLocaleDateString(undefined, { day: "numeric", month: "short" });
const fmtFull = (ms: number) =>
  new Date(ms).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export default function Timeline({ observed, scenarios, today, unit, bank, critical }: Props) {
  const rows = new Map<number, Record<string, number | null>>();
  const put = (t: string, key: string, v: number | null) => {
    const k = new Date(t).getTime();
    rows.set(k, { ...(rows.get(k) ?? { t: k }), [key]: v });
  };
  observed.forEach((p) => put(p.t, "Observed", p.value));
  // start each scenario at today's value so lines join the observed curve
  const last = observed.at(-1);
  scenarios.forEach((s) => {
    if (last) put(last.t, s.name, last.value);
    s.points.forEach((p) => put(p.t, s.name, p.value));
  });
  const data = [...rows.values()].sort((a, b) => (a.t as number) - (b.t as number));
  const todayMs = today ? new Date(today).getTime() : null;
  const endMs = data.length ? (data[data.length - 1].t as number) : null;
  const startMs = data.length ? (data[0].t as number) : null;
  const dayTicks: number[] = [];
  if (startMs && endMs) {
    const d = new Date(startMs);
    d.setHours(0, 0, 0, 0);
    for (d.setDate(d.getDate() + 1); d.getTime() <= endMs; d.setDate(d.getDate() + 1)) dayTicks.push(d.getTime());
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 18, right: 12, bottom: 0, left: 4 }}>
        <CartesianGrid vertical={false} stroke="#e3e8e5" />
        {todayMs && endMs && endMs > todayMs && (
          <ReferenceArea x1={todayMs} x2={endMs} fill="#d7e8ee" fillOpacity={0.45} />
        )}
        <XAxis
          dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]}
          ticks={dayTicks} tickFormatter={fmtTick} tick={{ fill: MUTED, fontSize: 11 }}
          axisLine={{ stroke: "#d5dcd8" }} tickLine={false} minTickGap={40}
        />
        <YAxis
          domain={([lo, hi]: readonly number[]) => {
            const top = Math.max(hi, bank ?? -Infinity);
            const pad = Math.max((top - lo) * 0.08, 0.2);
            return [Math.floor((lo - pad) * 2) / 2, Math.ceil((top + pad) * 2) / 2];
          }}
          allowDataOverflow width={44} tickFormatter={(v) => Number(v).toFixed(1)}
          tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false}
        />
        <Tooltip
          content={({ active, label, payload }) =>
            active && payload?.length ? (
              <div className="chart-tip">
                <b>{fmtFull(Number(label))}</b>
                {payload.map((p) => (
                  <div key={String(p.dataKey)}>
                    <span style={{ color: p.dataKey === "Observed" ? "#cfe0de" : String(p.color) }}>
                      {String(p.dataKey).replace(/^Scenario \d – /, "")}
                    </span>
                    <span>{Number(p.value).toFixed(2)} {unit}</span>
                  </div>
                ))}
              </div>
            ) : null
          }
        />
        {bank != null && (
          <ReferenceLine
            y={bank} stroke="#b8323a" strokeDasharray="2 3"
            label={{ value: `Bank ${bank.toFixed(2)}`, position: "insideBottomLeft", fill: "#b8323a", fontSize: 11 }}
          />
        )}
        {critical != null && critical !== bank && (
          <ReferenceLine
            y={critical} stroke="#d9682b" strokeDasharray="2 3"
            label={{ value: `Critical ${critical.toFixed(2)}`, position: "insideBottomRight", dx: -48, fill: "#d9682b", fontSize: 11 }}
          />
        )}
        <Line type="monotone" dataKey="Observed" stroke={INK} strokeWidth={2.25} dot={false} isAnimationActive={false} />
        {scenarios.map((s, i) => (
          <Line
            key={s.name} type="monotone" dataKey={s.name}
            stroke={SCENARIO_COLORS[i % SCENARIO_COLORS.length]} strokeWidth={2}
            strokeDasharray="5 4" dot={false} connectNulls
          />
        ))}
        {todayMs && (
          <ReferenceLine
            x={todayMs} stroke={INK} strokeWidth={1}
            label={{ value: "Today", position: "insideTopRight", fill: INK, fontSize: 11, fontWeight: 600, dy: -16 }}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}
