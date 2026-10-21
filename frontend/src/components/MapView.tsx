import { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";
import type { Incident, Station } from "../api";
import { NO_DATA_COLOR, SEVERITY, SITUATION } from "../lookups";

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN ?? "";

export const HEIGHT_COLORS = ["#c9dbd6", "#8fb4ad", "#4f8a86", "#24605f"];

interface Props {
  stations: Station[];
  selectedStation: number | null;
  onSelectStation: (id: number) => void;
  incidents: Incident[];
  showIncidents: boolean;
  selectedIncident: number | null;
  onSelectIncident: (id: number) => void;
  /** when set, the next map click places a point */
  onPick?: ((lon: number, lat: number) => void) | null;
  pickPoint?: [number, number] | null;
}

const fc = (features: GeoJSON.Feature[] = []): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features });

export default function MapView(props: Props) {
  const { stations, selectedStation, incidents, showIncidents, selectedIncident, onPick, pickPoint } = props;
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const loaded = useRef(false);
  const handlers = useRef(props);
  handlers.current = props;
  const pickMarker = useRef<mapboxgl.Marker | null>(null);

  // ---------- create map once ----------
  useEffect(() => {
    if (!container.current || map.current) return;
    const m = new mapboxgl.Map({
      container: container.current,
      style: "mapbox://styles/mapbox/light-v11",
      center: [100.2, 15.6],
      zoom: 7.4,
    });
    map.current = m;
    m.addControl(new mapboxgl.NavigationControl(), "top-right");
    const popup = new mapboxgl.Popup({ closeButton: false, closeOnClick: false, offset: 10, className: "map-tip" });

    m.on("load", () => {
      m.addLayer({
        id: "real-buildings",
        type: "fill-extrusion",
        source: "composite",
        "source-layer": "building",
        filter: ["==", ["get", "extrude"], "true"],
        minzoom: 13,
        paint: {
          "fill-extrusion-height": ["coalesce", ["get", "height"], 4],
          "fill-extrusion-base": ["coalesce", ["get", "min_height"], 0],
          "fill-extrusion-color": [
            "interpolate", ["linear"], ["coalesce", ["get", "height"], 4],
            0, HEIGHT_COLORS[0], 8, HEIGHT_COLORS[1], 20, HEIGHT_COLORS[2], 50, HEIGHT_COLORS[3],
          ],
          "fill-extrusion-opacity": ["interpolate", ["linear"], ["zoom"], 13, 0, 14, 0.9],
        },
      });

      m.addSource("stations", { type: "geojson", data: fc() });
      m.addLayer({
        id: "stations",
        type: "circle",
        source: "stations",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, ["case", ["get", "selected"], 6, 3], 12, ["case", ["get", "selected"], 10, 7]],
          "circle-color": ["get", "color"],
          "circle-opacity": ["case", ["get", "dim"], 0.35, 1],
          "circle-stroke-color": ["case", ["get", "selected"], "#17323a", "#ffffff"],
          "circle-stroke-width": ["case", ["get", "selected"], 3, 1],
        },
      });

      m.addSource("incidents", { type: "geojson", data: fc() });
      m.addLayer({
        id: "incident-halo",
        type: "circle",
        source: "incidents",
        paint: {
          "circle-radius": ["*", ["get", "severity"], 9],
          "circle-color": ["get", "color"],
          "circle-opacity": ["case", ["get", "selected"], 0.28, 0.14],
        },
      });
      m.addLayer({
        id: "incidents",
        type: "circle",
        source: "incidents",
        paint: {
          "circle-radius": ["case", ["get", "selected"], 9, 7],
          "circle-color": ["get", "color"],
          "circle-stroke-color": ["case", ["get", "selected"], "#17323a", "#ffffff"],
          "circle-stroke-width": 2.5,
        },
      });

      for (const layer of ["stations", "incidents"]) {
        m.on("mouseenter", layer, (e) => {
          m.getCanvas().style.cursor = "pointer";
          const f = e.features?.[0];
          if (f?.geometry.type === "Point") {
            popup.setLngLat(f.geometry.coordinates as [number, number]).setHTML(String(f.properties?.tip ?? "")).addTo(m);
          }
        });
        m.on("mouseleave", layer, () => {
          m.getCanvas().style.cursor = handlers.current.onPick ? "crosshair" : "";
          popup.remove();
        });
      }
      m.on("click", (e) => {
        const h = handlers.current;
        if (h.onPick) return h.onPick(e.lngLat.lng, e.lngLat.lat);
        const hit = m.queryRenderedFeatures(e.point, { layers: ["incidents", "stations"] })[0];
        if (!hit) return;
        const id = Number(hit.properties?.id);
        if (hit.layer?.id === "incidents") h.onSelectIncident(id);
        else h.onSelectStation(id);
      });

      loaded.current = true;
      m.fire("cfm:ready");
    });

    // keep the canvas matched to its panel when the layout or window changes
    const ro = new ResizeObserver(() => m.resize());
    ro.observe(container.current);

    return () => {
      ro.disconnect();
      m.remove();
      map.current = null;
      loaded.current = false;
    };
  }, []);

  // run fn now if the style is loaded, otherwise once it is
  const whenReady = (fn: (m: mapboxgl.Map) => void) => {
    const m = map.current;
    if (!m) return;
    if (loaded.current) fn(m);
    else m.once("cfm:ready", () => fn(m));
  };

  // ---------- stations ----------
  useEffect(() => {
    whenReady((m) => {
      const features: GeoJSON.Feature[] = stations.map((s) => {
        const sit = s.situation_level ? SITUATION[s.situation_level] : null;
        const level = s.latest_value != null ? `${s.latest_value.toFixed(2)} m MSL` : "No reading";
        return {
          type: "Feature",
          geometry: { type: "Point", coordinates: [s.lon, s.lat] },
          properties: {
            id: s.id,
            color: sit?.color ?? NO_DATA_COLOR,
            selected: s.id === selectedStation,
            dim: showIncidents,
            tip: `<b>${s.code} ${s.name}</b><br>${level}${sit ? `, ${sit.label.toLowerCase()}` : ""}`,
          },
        };
      });
      (m.getSource("stations") as mapboxgl.GeoJSONSource).setData(fc(features));
    });
  }, [stations, selectedStation, showIncidents]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- incidents ----------
  useEffect(() => {
    whenReady((m) => {
      const features: GeoJSON.Feature[] = showIncidents
        ? incidents
            .filter((i) => i.lon != null && i.lat != null)
            .map((i) => ({
              type: "Feature",
              geometry: { type: "Point", coordinates: [i.lon!, i.lat!] },
              properties: {
                id: i.id,
                severity: i.severity,
                color: i.status === "closed" ? NO_DATA_COLOR : SEVERITY[i.severity]?.color ?? NO_DATA_COLOR,
                selected: i.id === selectedIncident,
                tip: `<b>${i.title}</b><br>${i.households_affected.toLocaleString()} households affected`,
              },
            }))
        : [];
      (m.getSource("incidents") as mapboxgl.GeoJSONSource).setData(fc(features));
    });
  }, [incidents, showIncidents, selectedIncident]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- fly to selection ----------
  useEffect(() => {
    const s = stations.find((x) => x.id === selectedStation);
    if (s && !showIncidents) map.current?.flyTo({ center: [s.lon, s.lat], zoom: 13.5, pitch: 50, bearing: -15, duration: 1400 });
  }, [selectedStation]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const i = incidents.find((x) => x.id === selectedIncident);
    if (i?.lon != null && i.lat != null && showIncidents)
      map.current?.flyTo({ center: [i.lon, i.lat], zoom: 12, pitch: 40, duration: 1200 });
  }, [selectedIncident, showIncidents]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- pick mode ----------
  useEffect(() => {
    const m = map.current;
    if (m) m.getCanvas().style.cursor = onPick ? "crosshair" : "";
  }, [onPick]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    if (pickPoint) {
      pickMarker.current ??= new mapboxgl.Marker({ color: "#17323a" });
      pickMarker.current.setLngLat(pickPoint).addTo(m);
    } else {
      pickMarker.current?.remove();
    }
  }, [pickPoint]);

  return <div ref={container} className="map" />;
}
