export interface ThemeDef {
  id: string;
  libelle: string;
  couleur: string;
  analyse: boolean;
}

export interface LayerDef {
  id: string;
  theme: string;
  libelle: string;
  mode: "live" | "batch";
  type: "wms" | "xyz" | "vector" | "pmtiles";
  url: string;
  wms_layer?: string;
  /** Couche à lire dans les tuiles vectorielles (types vector et pmtiles). */
  source_layer?: string;
  attribution?: string;
  flux_confirme: boolean;
}

export interface Catalog {
  themes: ThemeDef[];
  layers: LayerDef[];
}

export type ZoneInput =
  | { type: "polygon"; geometry: GeoJSON.Polygon }
  | { type: "point_radii"; center: [number, number]; small_radius_m: number; large_radius_m: number };

export interface SourceRef {
  code: string;
  libelle: string;
  url: string;
  millesime?: string;
}

export interface ThemeResult {
  theme: string;
  indicateurs: Record<string, unknown>;
  items: Record<string, unknown>[];
  avertissements: string[];
  sources: SourceRef[];
}

export interface AnalyzeResponse {
  zone_resume: Record<string, unknown>;
  resultats: ThemeResult[];
}

export type DrawMode = "select" | "point" | "polygon";
