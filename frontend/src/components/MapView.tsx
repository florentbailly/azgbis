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

// Choroplèthe des prix DVF : rampe séquentielle mono-teinte (violet de la charte),
// validée clair→foncé sur fond OSM. Bornes calées sur les quartiles DVF observés.
const PRIX_COLORS = ["#BE8DD8", "#A265C2", "#8542A8", "#672B8B", "#4B1965"];
const PRIX_BREAKS = [2500, 3500, 4500, 6000]; // €/m²
export const PRIX_CLASSES = PRIX_COLORS.map((c, i) => ({
  couleur: c,
  libelle:
    i === 0
      ? `< ${PRIX_BREAKS[0].toLocaleString("fr-FR")}`
      : i === PRIX_COLORS.length - 1
        ? `≥ ${PRIX_BREAKS[i - 1].toLocaleString("fr-FR")}`
        : `${PRIX_BREAKS[i - 1].toLocaleString("fr-FR")} – ${PRIX_BREAKS[i].toLocaleString("fr-FR")}`,
}));

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
  /** Mode « rendu » (cartes du rapport PDF) : cadre la zone, masque les contrôles de
   *  navigation, affiche la légende des couches actives et signale la fin du chargement
   *  en posant #rendu-pret (attendu par Playwright côté worker). */
  rendu?: boolean;
}

/** Emprise englobante d'une FeatureCollection (lon/lat). */
function bboxDe(fc: GeoJSON.FeatureCollection): [[number, number], [number, number]] | null {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const visite = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") {
      const [x, y] = c as [number, number];
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    } else if (Array.isArray(c)) {
      c.forEach(visite);
    }
  };
  for (const f of fc.features) visite((f.geometry as { coordinates?: unknown }).coordinates);
  return Number.isFinite(minX) ? [[minX, minY], [maxX, maxY]] : null;
}

export default function MapView({ catalog, activeLayerIds, zoneFeatures, onMapClick, flyTo, rendu }: Props) {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const readyRef = useRef(false);
  const clickRef = useRef(onMapClick);
  clickRef.current = onMapClick;
  // Le gestionnaire `load` est une fermeture du premier rendu : il lirait un catalogue
  // encore null si le fetch aboutit après l'init de la carte. Les refs suivent la valeur courante.
  const catalogRef = useRef(catalog);
  catalogRef.current = catalog;
  const activeRef = useRef(activeLayerIds);
  activeRef.current = activeLayerIds;
  const renduArmeRef = useRef(false);

  useEffect(() => {
    const map = new maplibregl.Map({
      container: "map",
      style: BASE_STYLE,
      center: [2.5, 46.6],
      zoom: 5.5,
      // Position dans l'URL (#zoom/lat/lon) : permet de partager une vue et de
      // revenir au même endroit après rechargement.
      hash: true,
      attributionControl: { compact: true },
    });
    if (!rendu) map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }));
    map.on("click", (e) => clickRef.current(e.lngLat.lng, e.lngLat.lat));
    // Infobulle des prix : le prix médian au m² de la maille survolée (couche marquée
    // rendu prix_m2 via ses métadonnées, quel que soit son id de catalogue).
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, maxWidth: "280px" });
    map.on("mousemove", (e) => {
      const ids = map
        .getStyle()
        .layers.filter((ly) => (ly.metadata as { rendu?: string } | undefined)?.rendu === "prix_m2")
        .map((ly) => ly.id);
      const f = ids.length ? map.queryRenderedFeatures(e.point, { layers: ids })[0] : undefined;
      if (!f) {
        popup.remove();
        return;
      }
      const p = f.properties as { prix_m2: number; nb_ventes: number; libelle?: string; code: string };
      popup
        .setLngLat(e.lngLat)
        .setText(
          `${Number(p.prix_m2).toLocaleString("fr-FR")} €/m² médian — ` +
            `${p.nb_ventes} vente${Number(p.nb_ventes) > 1 ? "s" : ""} (${p.libelle ?? p.code})`,
        )
        .addTo(map);
    });
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
      syncOverlays(map, catalogRef.current, activeRef.current);
      (map.getSource(ZONE_SOURCE) as maplibregl.GeoJSONSource).setData(zoneFeatures);
      if (rendu) {
        const bbox = bboxDe(zoneFeatures);
        if (bbox) map.fitBounds(bbox, { padding: 60, animate: false, maxZoom: 16 });
      }
    });
    mapRef.current = map;
    return () => { readyRef.current = false; map.remove(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) syncOverlays(map, catalog, activeLayerIds);
  }, [catalog, activeLayerIds]);

  // Mode rendu : n'armer le signal de fin (#rendu-pret) qu'une fois carte ET catalogue
  // prêts — sinon Playwright capturerait une carte sans ses couches thématiques.
  useEffect(() => {
    const map = mapRef.current;
    if (!rendu || !catalog || !map || renduArmeRef.current) return;
    const armer = () => {
      if (renduArmeRef.current) return;
      renduArmeRef.current = true;
      // `idle` = plus aucune tuile en attente : la carte est capturable. La petite
      // marge couvre le fondu d'apparition des tuiles raster.
      map.once("idle", () => {
        setTimeout(() => {
          const marqueur = document.createElement("div");
          marqueur.id = "rendu-pret";
          document.body.appendChild(marqueur);
        }, 400);
      });
      // Si la carte était déjà au repos, `idle` ne serait jamais réémis : forcer un cycle.
      map.triggerRepaint();
    };
    if (readyRef.current) armer();
    else map.once("load", armer);
  }, [rendu, catalog]);

  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) {
      (map.getSource(ZONE_SOURCE) as maplibregl.GeoJSONSource | undefined)?.setData(zoneFeatures);
    }
  }, [zoneFeatures]);

  useEffect(() => {
    if (flyTo && mapRef.current) mapRef.current.flyTo({ center: flyTo, zoom: 15 });
  }, [flyTo]);

  // Légende de la carte des prix, affichée dès que la couche choroplèthe est active.
  const prixActif = !!catalog?.layers.some((l) => l.rendu === "prix_m2" && activeLayerIds.has(l.id));
  // Mode rendu : légende des couches actives (la couche prix a déjà la sienne).
  const couchesLegende =
    rendu && catalog ? catalog.layers.filter((l) => activeLayerIds.has(l.id) && l.rendu !== "prix_m2") : [];
  return (
    <>
      <div id="map" />
      {couchesLegende.length > 0 && (
        <div className="rendu-legende">
          {couchesLegende.map((l) => (
            <div key={l.id} className="rendu-legende-item">
              <div className="rendu-legende-nom">
                {l.type !== "wms" && (
                  <span className="rendu-swatch" style={{ background: themeColor(catalog!, l.theme) }} />
                )}
                {l.libelle}
              </div>
              {l.type === "wms" && l.url.includes("georisques") && (
                <img
                  alt=""
                  src={`${l.url}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetLegendGraphic&FORMAT=image/png&LAYER=${encodeURIComponent(l.wms_layer ?? "")}`}
                />
              )}
            </div>
          ))}
        </div>
      )}
      {prixActif && (
        <div className="prix-legende">
          <div className="prix-legende-titre">Prix médian — ventes DVF (€/m²)</div>
          {PRIX_CLASSES.map((c) => (
            <div key={c.couleur} className="prix-legende-ligne">
              <span className="prix-legende-carre" style={{ background: c.couleur }} />
              {c.libelle}
            </div>
          ))}
          <div className="prix-legende-note">
            Maille selon le zoom : département → commune → section cadastrale → parcelle.
            Aucune couleur = aucune vente connue.
          </div>
        </div>
      )}
    </>
  );
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
          // Certains WMS (EAIP) ne servent qu'une fenêtre d'échelles : en la déclarant,
          // MapLibre ré-agrandit la tuile la plus proche au lieu d'afficher du vide.
          ...(l.zoom_natif_min != null ? { minzoom: l.zoom_natif_min } : {}),
          ...(l.zoom_natif_max != null ? { maxzoom: l.zoom_natif_max } : {}),
          attribution: l.attribution ?? "",
        });
        map.addLayer({
          id: layerId,
          type: "raster",
          source: sourceId,
          paint: {
            "raster-opacity": l.opacite ?? 0.75,
            // Renforcement des aplats trop pâles (EAIP est servi en bleu quasi blanc) :
            // on assombrit le point blanc et on remonte la saturation.
            ...(l.renforcement ? { "raster-brightness-max": 0.6, "raster-saturation": 0.7 } : {}),
          },
        });
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
        if (l.rendu === "prix_m2") {
          // Choroplèthe : couleur par classe de prix. Les mailles sans vente ne sont
          // simplement pas dans les tuiles — rien n'est dessiné là où on ne sait rien.
          const stepExpr = [
            "step", ["get", "prix_m2"], PRIX_COLORS[0],
            PRIX_BREAKS[0], PRIX_COLORS[1],
            PRIX_BREAKS[1], PRIX_COLORS[2],
            PRIX_BREAKS[2], PRIX_COLORS[3],
            PRIX_BREAKS[3], PRIX_COLORS[4],
          ] as unknown as maplibregl.ExpressionSpecification;
          map.addLayer({
            id: layerId, type: "fill", source: sourceId, "source-layer": sourceLayer,
            metadata: { rendu: "prix_m2" },
            paint: { "fill-color": stepExpr, "fill-opacity": 0.65 },
          });
          map.addLayer({
            id: `${layerId}-line`, type: "line", source: sourceId, "source-layer": sourceLayer,
            paint: { "line-color": "#581D74", "line-width": 0.5, "line-opacity": 0.5 },
          });
        } else {
          map.addLayer({
            id: layerId, type: "fill", source: sourceId, "source-layer": sourceLayer,
            paint: { "fill-color": themeColor(catalog, l.theme), "fill-opacity": 0.25 },
          });
          map.addLayer({
            id: `${layerId}-line`, type: "line", source: sourceId, "source-layer": sourceLayer,
            paint: { "line-color": themeColor(catalog, l.theme), "line-width": 1 },
          });
        }
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
