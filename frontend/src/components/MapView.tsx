import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import type { Catalog, LayerDef } from "../types";

maplibregl.addProtocol("pmtiles", new Protocol().tile);

// Fond raster OSM : fiable sans dépendance à un service de styles vectoriels.
const BASE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

const ZONE_SOURCE = "zone";
const ZONE_LAYERS = [
  "zone-contexte-line", "zone-etude-fill", "zone-etude-line", "zone-draft-line",
  "zone-parcelle-fill", "zone-parcelle-line", "zone-points",
];

function wmsTileUrl(l: LayerDef): string {
  const sep = l.url.includes("?") ? "&" : "?";
  return (
    `${l.url}${sep}SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=${encodeURIComponent(l.wms_layer ?? "")}` +
    `&STYLES=&FORMAT=image/png&TRANSPARENT=true&CRS=EPSG:3857&WIDTH=256&HEIGHT=256&BBOX={bbox-epsg-3857}`
  );
}

interface Props {
  catalog: Catalog | null;
  activeLayerIds: Set<string>;
  zoneFeatures: GeoJSON.FeatureCollection;
  onMapClick: (lon: number, lat: number) => void;
  flyTo: [number, number] | null;
}

export default function MapView({ catalog, activeLayerIds, zoneFeatures, onMapClick, flyTo }: Props) {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const readyRef = useRef(false);
  const clickRef = useRef(onMapClick);
  clickRef.current = onMapClick;

  useEffect(() => {
    const map = new maplibregl.Map({
      container: "map",
      style: BASE_STYLE,
      center: [2.5, 46.6],
      zoom: 5.5,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }));
    map.on("click", (e) => clickRef.current(e.lngLat.lng, e.lngLat.lat));
    map.on("load", () => {
      map.addSource(ZONE_SOURCE, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "zone-etude-fill", type: "fill", source: ZONE_SOURCE,
        filter: ["==", ["get", "role"], "etude"],
        paint: { "fill-color": "#581D74", "fill-opacity": 0.08 },
      });
      map.addLayer({
        id: "zone-etude-line", type: "line", source: ZONE_SOURCE,
        filter: ["==", ["get", "role"], "etude"],
        paint: { "line-color": "#581D74", "line-width": 2.5 },
      });
      map.addLayer({
        id: "zone-contexte-line", type: "line", source: ZONE_SOURCE,
        filter: ["==", ["get", "role"], "contexte"],
        paint: { "line-color": "#8A5599", "line-width": 2, "line-dasharray": [3, 2] },
      });
      map.addLayer({
        id: "zone-draft-line", type: "line", source: ZONE_SOURCE,
        filter: ["==", ["get", "role"], "draft"],
        paint: { "line-color": "#581D74", "line-width": 2, "line-dasharray": [2, 2] },
      });
      map.addLayer({
        id: "zone-parcelle-fill", type: "fill", source: ZONE_SOURCE,
        filter: ["==", ["get", "role"], "parcelle"],
        paint: { "fill-color": "#55579E", "fill-opacity": 0.3 },
      });
      map.addLayer({
        id: "zone-parcelle-line", type: "line", source: ZONE_SOURCE,
        filter: ["==", ["get", "role"], "parcelle"],
        paint: { "line-color": "#55579E", "line-width": 2.5 },
      });
      map.addLayer({
        id: "zone-points", type: "circle", source: ZONE_SOURCE,
        filter: ["in", ["get", "role"], ["literal", ["centre", "sommet"]]],
        paint: { "circle-radius": 5, "circle-color": "#581D74", "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 },
      });
      readyRef.current = true;
      syncOverlays(map, catalog, activeLayerIds);
      (map.getSource(ZONE_SOURCE) as maplibregl.GeoJSONSource).setData(zoneFeatures);
    });
    mapRef.current = map;
    return () => { readyRef.current = false; map.remove(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) syncOverlays(map, catalog, activeLayerIds);
  }, [catalog, activeLayerIds]);

  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) {
      (map.getSource(ZONE_SOURCE) as maplibregl.GeoJSONSource | undefined)?.setData(zoneFeatures);
    }
  }, [zoneFeatures]);

  useEffect(() => {
    if (flyTo && mapRef.current) mapRef.current.flyTo({ center: flyTo, zoom: 15 });
  }, [flyTo]);

  return <div id="map" />;
}

function syncOverlays(map: maplibregl.Map, catalog: Catalog | null, active: Set<string>) {
  if (!catalog) return;
  for (const l of catalog.layers) {
    const layerId = `overlay-${l.id}`;
    const sourceId = `src-${l.id}`;
    const wanted = active.has(l.id);
    const present = !!map.getLayer(layerId);
    if (wanted === present) continue;
    if (!wanted) {
      map.removeLayer(layerId);
      if (map.getLayer(`${layerId}-line`)) map.removeLayer(`${layerId}-line`);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
      continue;
    }
    try {
      if (l.type === "wms" || l.type === "xyz") {
        map.addSource(sourceId, {
          type: "raster",
          tiles: [l.type === "wms" ? wmsTileUrl(l) : l.url],
          tileSize: 256,
          attribution: l.attribution ?? "",
        });
        map.addLayer({ id: layerId, type: "raster", source: sourceId, paint: { "raster-opacity": 0.75 } });
      } else {
        // Tuiles vectorielles : servies par l'API depuis PostGIS (vector), ou fichier
        // PMTiles produit par le pipeline (pmtiles).
        if (l.type === "vector") {
          // Concaténation et non `new URL()`, qui percent-encoderait les {z}/{x}/{y}
          // du gabarit et empêcherait MapLibre de les substituer.
          // maxzoom : au-delà de 14 MapLibre ré-agrandit les tuiles de z14 au lieu
          // d'en demander de nouvelles — inutile de solliciter la base à chaque zoom.
          map.addSource(sourceId, {
            type: "vector",
            tiles: [`${window.location.origin}${l.url}`],
            minzoom: 5,
            maxzoom: 14,
            attribution: l.attribution ?? "",
          });
        } else {
          map.addSource(sourceId, { type: "vector", url: `pmtiles://${l.url}`, attribution: l.attribution ?? "" });
        }
        const sourceLayer = l.source_layer ?? l.id;
        map.addLayer({
          id: layerId, type: "fill", source: sourceId, "source-layer": sourceLayer,
          paint: { "fill-color": themeColor(catalog, l.theme), "fill-opacity": 0.25 },
        });
        map.addLayer({
          id: `${layerId}-line`, type: "line", source: sourceId, "source-layer": sourceLayer,
          paint: { "line-color": themeColor(catalog, l.theme), "line-width": 1 },
        });
      }
    } catch (e) {
      console.warn(`Couche ${l.id} non chargée :`, e);
    }
  }
  // La zone d'étude reste toujours au-dessus des couches thématiques.
  for (const id of ZONE_LAYERS) if (map.getLayer(id)) map.moveLayer(id);
}

function themeColor(catalog: Catalog, themeId: string): string {
  return catalog.themes.find((t) => t.id === themeId)?.couleur ?? "#7F7F7F";
}
