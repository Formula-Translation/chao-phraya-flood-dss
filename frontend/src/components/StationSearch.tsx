import { useMemo, useRef, useState } from "react";
import type { Station } from "../api";
import { NO_DATA_COLOR, SITUATION } from "../lookups";

interface Props {
  stations: Station[];
  selected: Station | undefined;
  onSelect: (id: number) => void;
}

export default function StationSearch({ stations, selected, onSelect }: Props) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const term = q.trim().toLowerCase();
    const list = term
      ? stations.filter((s) =>
          [s.code, s.name, s.name_en, s.province, s.amphoe, s.river].some((v) => v?.toLowerCase().includes(term))
        )
      : stations.filter((s) => s.is_key_station);
    return list.slice(0, 40);
  }, [q, stations]);

  const pick = (s: Station) => {
    onSelect(s.id);
    setQ("");
    setOpen(false);
    input.current?.blur();
  };

  return (
    <div className="search">
      <input
        ref={input}
        className="search-input"
        placeholder={selected ? `${selected.code} ${selected.name}` : "Search stations"}
        value={q}
        aria-label="Search stations by code, name, province or river"
        onChange={(e) => { setQ(e.target.value); setActive(0); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          if (e.key === "Enter" && results[active]) pick(results[active]);
          if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && (
        <ul className="search-list" role="listbox">
          {!q && <li className="search-note">Key stations. Type a code, name, province or river to search all {stations.length}.</li>}
          {results.length === 0 && <li className="search-note">No station matches “{q}”.</li>}
          {results.map((s, i) => (
            <li
              key={s.id}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={() => pick(s)}
              onMouseEnter={() => setActive(i)}
            >
              <span className="dot" style={{ background: s.situation_level ? SITUATION[s.situation_level].color : NO_DATA_COLOR }} />
              <span className="search-code">{s.code}</span>
              <span className="search-name">{s.name}<small>{[s.amphoe, s.province].filter(Boolean).join(", ")}</small></span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
