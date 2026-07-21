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
  /** Rendu spécial : "prix_m2" = choroplèthe du prix médian au m² (couche DVF) ;
   *  "classes" = choroplèthe catégorielle générique (légende portée par `classes`). */
  rendu?: "prix_m2" | "classes";
  /** Légende d'une couche `rendu: "classes"` : valeur, couleur et libellé de chaque classe. */
  classes?: { classe: number; couleur: string; libelle: string }[];
  /** Note de méthode affichée sous la légende (ex. maille selon le zoom). */
  note_legende?: string;
  /** Opacité du raster (défaut 0.75). */
  opacite?: number;
  /** Accentue un WMS servi trop pâle (assombrit + sature, ex. EAIP). */
  renforcement?: boolean;
  /** Fenêtre de zooms réellement servie par le WMS : en dehors, MapLibre
   *  ré-agrandit la tuile la plus proche au lieu de recevoir du vide. */
  zoom_natif_min?: number;
  zoom_natif_max?: number;
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
