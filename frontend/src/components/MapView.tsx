import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import { fetchDvfPeriode } from "../api";
import { TYPOLOGIE_LABELS, TYPOLOGIE_ORDRE } from "../typologies";
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

/** Période de ventes appliquée à la carte des prix ; null = toutes les ventes. */
type Periode = { debut: string; fin: string } | null;

/** Mois « AAAA-MM » couverts par les bornes (curseurs du filtre de période). */
function moisEntre(min: string, max: string): string[] {
  const out: string[] = [];
  const d = new Date(`${min.slice(0, 7)}-01T12:00:00`);
  const dernier = max.slice(0, 7);
  for (let i = 0; i < 600; i++) {
    const m = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    out.push(m);
    if (m === dernier) break;
    d.setMonth(d.getMonth() + 1);
  }
  return out;
}

function dernierJourDuMois(mois: string): string {
  const [a, m] = mois.split("-").map(Number);
  return `${mois}-${String(new Date(a, m, 0).getDate()).padStart(2, "0")}`;
}

function frDate(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("fr-FR");
}

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
  /** Typologies affichées sur la carte des prix (panneau Couches) ; toutes = pas de filtre. */
  typologiesPrix?: string[];
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

export default function MapView({ catalog, activeLayerIds, typologiesPrix, zoneFeatures, onMapClick, flyTo, rendu }: Props) {
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

  // Filtres de la carte des prix : période (bornes = min/max des ventes importées,
  // null = toutes) et typologies (panneau Couches). Sans aucun filtre, l'URL reste
  // nue : tuiles précalculées, plus rapides.
  const [bornes, setBornes] = useState<{ min: string; max: string } | null>(null);
  const [periode, setPeriode] = useState<Periode>(null);
  const filtresPrix: string[] = [];
  if (periode) filtresPrix.push(`debut=${periode.debut}`, `fin=${periode.fin}`);
  if (typologiesPrix && typologiesPrix.length > 0 && typologiesPrix.length < TYPOLOGIE_ORDRE.length) {
    filtresPrix.push(`typologies=${typologiesPrix.join(",")}`);
  }
  const prixSuffixe = filtresPrix.length ? `?${filtresPrix.join("&")}` : "";
  const prixSuffixeRef = useRef(prixSuffixe);
  prixSuffixeRef.current = prixSuffixe;

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
    // Infobulle des choroplèthes : couches marquées par leurs métadonnées `rendu`
    // (prix_m2 ou classes), quel que soit leur id de catalogue.
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, maxWidth: "280px" });
    map.on("mousemove", (e) => {
      const ids = map
        .getStyle()
        .layers.filter((ly) => (ly.metadata as { rendu?: string } | undefined)?.rendu)
        .map((ly) => ly.id);
      const f = ids.length ? map.queryRenderedFeatures(e.point, { layers: ids })[0] : undefined;
      if (!f) {
        popup.remove();
        return;
      }
      const meta = (f.layer.metadata ?? {}) as { rendu?: string; couche?: string };
      const p = f.properties as Record<string, unknown>;
      let texte: string;
      if (meta.rendu === "prix_m2") {
        texte =
          `${Number(p.prix_m2).toLocaleString("fr-FR")} €/m² médian — ` +
          `${p.nb_ventes} vente${Number(p.nb_ventes) > 1 ? "s" : ""} (${p.libelle ?? p.code})`;
      } else {
        const def = catalogRef.current?.layers.find((l) => l.id === meta.couche);
        const cl = def?.classes?.find((c) => c.classe === Number(p.classe));
        texte = `${cl?.libelle ?? `Classe ${p.classe}`} — ${p.libelle ?? p.code}`;
      }
      popup.setLngLat(e.lngLat).setText(texte).addTo(map);
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
      syncOverlays(map, catalogRef.current, activeRef.current, prixSuffixeRef.current);
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
    if (map && readyRef.current) syncOverlays(map, catalog, activeLayerIds, prixSuffixeRef.current);
  }, [catalog, activeLayerIds]);

  // Changement de période : recharger les tuiles de la couche prix sans la recréer.
  // Débounce : un glissement de curseur ne doit pas déclencher une requête par cran.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !catalog) return;
    const t = setTimeout(() => {
      if (!readyRef.current) return;
      for (const l of catalog.layers) {
        if (l.rendu !== "prix_m2") continue;
        const src = map.getSource(`src-${l.id}`) as maplibregl.VectorTileSource | undefined;
        src?.setTiles?.([`${window.location.origin}${l.url}${prixSuffixe}`]);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [prixSuffixe, catalog]);

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

  // Légendes des choroplèthes, affichées dès que la couche correspondante est active.
  const prixActif = !!catalog?.layers.some((l) => l.rendu === "prix_m2" && activeLayerIds.has(l.id));
  const couchesClasses =
    catalog?.layers.filter((l) => l.rendu === "classes" && !!l.classes?.length && activeLayerIds.has(l.id)) ?? [];

  // Bornes du filtre de période, chargées à la première activation de la couche prix.
  useEffect(() => {
    if (!prixActif || bornes || rendu) return;
    fetchDvfPeriode().then((p) => {
      if (p.min && p.max) setBornes({ min: p.min, max: p.max });
    });
  }, [prixActif, bornes, rendu]);
  // Mode rendu : légende des couches actives (les choroplèthes ont déjà la leur).
  const couchesLegende =
    rendu && catalog ? catalog.layers.filter((l) => activeLayerIds.has(l.id) && !l.rendu) : [];
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
      {(prixActif || couchesClasses.length > 0) && (
        <div className="legendes">
          {couchesClasses.map((l) => (
            <div key={l.id} className="prix-legende">
              <div className="prix-legende-titre">{l.libelle}</div>
              {l.classes!.map((c) => (
                <div key={c.classe} className="prix-legende-ligne">
                  <span className="prix-legende-carre" style={{ background: c.couleur }} />
                  {c.libelle}
                </div>
              ))}
              {l.note_legende && <div className="prix-legende-note">{l.note_legende}</div>}
            </div>
          ))}
          {prixActif && (
            <div className="prix-legende">
              <div className="prix-legende-titre">Prix médian — ventes DVF (€/m²)</div>
              {PRIX_CLASSES.map((c) => (
                <div key={c.couleur} className="prix-legende-ligne">
                  <span className="prix-legende-carre" style={{ background: c.couleur }} />
                  {c.libelle}
                </div>
              ))}
              {!rendu && bornes && (
                <PeriodeControles bornes={bornes} periode={periode} onChange={setPeriode} />
              )}
              <div className="prix-legende-note">
                {periode ? `Ventes du ${frDate(periode.debut)} au ${frDate(periode.fin)}. ` : ""}
                {typologiesPrix && typologiesPrix.length < TYPOLOGIE_ORDRE.length
                  ? `Typologies : ${typologiesPrix.map((c) => TYPOLOGIE_LABELS[c] ?? c).join(", ")}. `
                  : ""}
                Maille selon le zoom : département → commune → section cadastrale → parcelle.
                Aucune couleur = aucune vente connue.
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}

/** Filtre de période de la carte des prix : un curseur (pas mensuel) + un champ date
 *  par borne. Revenir aux bornes complètes équivaut à « toute la période » (tuiles
 *  précalculées, plus rapides). */
function PeriodeControles({ bornes, periode, onChange }: {
  bornes: { min: string; max: string };
  periode: Periode;
  onChange: (p: Periode) => void;
}) {
  const mois = moisEntre(bornes.min, bornes.max);
  const debut = periode?.debut ?? bornes.min;
  const fin = periode?.fin ?? bornes.max;
  const idx = (d: string, defaut: number) => {
    const i = mois.indexOf(d.slice(0, 7));
    return i >= 0 ? i : defaut;
  };
  const poser = (d: string, f: string) =>
    onChange(d <= bornes.min && f >= bornes.max ? null : { debut: d, fin: f });
  return (
    <div className="prix-periode">
      <div className="prix-periode-ligne">
        <span className="prix-periode-lib">Du</span>
        <input
          type="range" min={0} max={mois.length - 1} value={idx(debut, 0)}
          onChange={(e) => {
            const m = mois[Number(e.target.value)];
            const d = `${m}-01`;
            poser(d, d > fin ? dernierJourDuMois(m) : fin);
          }}
        />
        <input
          type="date" min={bornes.min} max={bornes.max} value={debut}
          onChange={(e) => e.target.value && poser(e.target.value, e.target.value > fin ? e.target.value : fin)}
        />
      </div>
      <div className="prix-periode-ligne">
        <span className="prix-periode-lib">Au</span>
        <input
          type="range" min={0} max={mois.length - 1} value={idx(fin, mois.length - 1)}
          onChange={(e) => {
            const m = mois[Number(e.target.value)];
            const f = dernierJourDuMois(m);
            poser(f < debut ? `${m}-01` : debut, f);
          }}
        />
        <input
          type="date" min={bornes.min} max={bornes.max} value={fin}
          onChange={(e) => e.target.value && poser(e.target.value < debut ? e.target.value : debut, e.target.value)}
        />
      </div>
      {periode && (
        <button className="prix-periode-reset" onClick={() => onChange(null)}>
          Toute la période
        </button>
      )}
    </div>
  );
}

function syncOverlays(map: maplibregl.Map, catalog: Catalog | null, active: Set<string>, prixSuffixe: string) {
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
            tiles: [`${window.location.origin}${l.url}${l.rendu === "prix_m2" ? prixSuffixe : ""}`],
            minzoom: 5,
            maxzoom: 14,
            attribution: l.attribution ?? "",
          });
        } else {
          map.addSource(sourceId, { type: "vector", url: `pmtiles://${l.url}`, attribution: l.attribution ?? "" });
        }
        const sourceLayer = l.source_layer ?? l.id;
        if (l.rendu === "classes" && l.classes?.length) {
          // Choroplèthe catégorielle générique : couleurs et libellés portés par le
          // catalogue — aucune connaissance de la donnée (radon…) côté front.
          const matchExpr = [
            "match", ["get", "classe"],
            ...l.classes.flatMap((c) => [c.classe, c.couleur]),
            "#7F7F7F",
          ] as unknown as maplibregl.ExpressionSpecification;
          map.addLayer({
            id: layerId, type: "fill", source: sourceId, "source-layer": sourceLayer,
            metadata: { rendu: "classes", couche: l.id },
            paint: { "fill-color": matchExpr, "fill-opacity": 0.55 },
          });
          map.addLayer({
            id: `${layerId}-line`, type: "line", source: sourceId, "source-layer": sourceLayer,
            paint: { "line-color": "#7F7F7F", "line-width": 0.4, "line-opacity": 0.5 },
          });
        } else if (l.rendu === "prix_m2") {
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
