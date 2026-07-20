import * as turf from "@turf/turf";
import type { DrawMode, ZoneInput } from "./types";

export interface ZoneDraft {
  mode: DrawMode;
  center: [number, number] | null;
  smallRadiusM: number;
  largeRadiusM: number;
  polygonPoints: [number, number][];
  polygonClosed: boolean;
}

export const initialDraft: ZoneDraft = {
  mode: "select",
  center: null,
  smallRadiusM: 500,
  largeRadiusM: 1500,
  polygonPoints: [],
  polygonClosed: false,
};

/** Zone envoyée à l'API, ou null si le tracé est incomplet. */
export function toZoneInput(d: ZoneDraft): ZoneInput | null {
  if (d.mode === "point" && d.center) {
    return {
      type: "point_radii",
      center: d.center,
      small_radius_m: d.smallRadiusM,
      large_radius_m: Math.max(d.largeRadiusM, d.smallRadiusM),
    };
  }
  if (d.mode === "polygon" && d.polygonClosed && d.polygonPoints.length >= 3) {
    const ring = [...d.polygonPoints, d.polygonPoints[0]];
    return { type: "polygon", geometry: { type: "Polygon", coordinates: [ring] } };
  }
  return null;
}

/** Rendu carte : zone d'étude (violet plein), zone de contexte (pointillé), tracé en cours. */
export function toFeatures(d: ZoneDraft): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  if (d.mode === "point" && d.center) {
    const small = turf.circle(d.center, d.smallRadiusM / 1000, { steps: 96, units: "kilometers" });
    small.properties = { role: "etude" };
    features.push(small);
    if (d.largeRadiusM > d.smallRadiusM) {
      const large = turf.circle(d.center, d.largeRadiusM / 1000, { steps: 96, units: "kilometers" });
      large.properties = { role: "contexte" };
      features.push(large);
    }
    features.push(turf.point(d.center, { role: "centre" }));
  }
  if (d.mode === "polygon" && d.polygonPoints.length > 0) {
    if (d.polygonClosed && d.polygonPoints.length >= 3) {
      const ring = [...d.polygonPoints, d.polygonPoints[0]];
      features.push(turf.polygon([ring], { role: "etude" }));
    } else {
      features.push(turf.lineString(
        d.polygonPoints.length >= 2 ? d.polygonPoints : [d.polygonPoints[0], d.polygonPoints[0]],
        { role: "draft" },
      ));
      for (const p of d.polygonPoints) features.push(turf.point(p, { role: "sommet" }));
    }
  }
  return { type: "FeatureCollection", features };
}

/** Mode « rendu » (rapport PDF) : reconstruit un tracé depuis la zone passée en URL. */
export function zoneInputToDraft(z: ZoneInput): ZoneDraft {
  if (z.type === "point_radii") {
    return {
      ...initialDraft,
      mode: "point",
      center: z.center,
      smallRadiusM: z.small_radius_m,
      largeRadiusM: z.large_radius_m,
    };
  }
  const ring = z.geometry.coordinates[0] as [number, number][];
  // L'anneau GeoJSON est fermé (dernier point = premier) ; le tracé ne stocke pas la fermeture.
  return {
    ...initialDraft,
    mode: "polygon",
    polygonPoints: ring.slice(0, -1),
    polygonClosed: true,
  };
}

const STORAGE_KEY = "azgbis.derniere_zone";

/** Zones privées sans compte (lot 1) : persistance navigateur uniquement. */
export function saveDraft(d: ZoneDraft): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(d));
  } catch { /* stockage indisponible : non bloquant */ }
}

export function loadDraft(): ZoneDraft | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...initialDraft, ...JSON.parse(raw) } : null;
  } catch {
    return null;
  }
}
