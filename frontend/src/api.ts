import type { AnalyzeResponse, Catalog, ZoneInput } from "./types";

export async function fetchCatalog(): Promise<Catalog> {
  const r = await fetch("/api/layers");
  if (!r.ok) throw new Error(`GET /api/layers → ${r.status}`);
  return r.json();
}

export async function analyzeZone(zone: ZoneInput, themes: string[]): Promise<AnalyzeResponse> {
  const r = await fetch("/api/zones/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zone, themes }),
  });
  if (!r.ok) throw new Error(`POST /api/zones/analyze → ${r.status}: ${await r.text()}`);
  return r.json();
}

export interface ReportMeta {
  titre: string;
  client_ref: string;
  auteur: string;
}

export interface ReportStatus {
  status: "pending" | "running" | "done" | "error";
  download_url?: string;
  erreur?: string;
}

export async function createReport(zone: ZoneInput, themes: string[], meta: ReportMeta): Promise<string> {
  const r = await fetch("/api/reports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zone, themes, ...meta }),
  });
  if (!r.ok) throw new Error(`POST /api/reports → ${r.status}: ${await r.text()}`);
  return (await r.json()).job_id;
}

export async function getReportStatus(jobId: string): Promise<ReportStatus> {
  const r = await fetch(`/api/reports/${jobId}`);
  if (!r.ok) throw new Error(`GET /api/reports/${jobId} → ${r.status}`);
  return r.json();
}

/** Télécharge l'Excel des transactions DVF de la zone de contexte (section Marché). */
export async function downloadTransactionsExcel(zone: ZoneInput): Promise<void> {
  const r = await fetch("/api/dvf/export.xlsx", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zone }),
  });
  if (!r.ok) throw new Error(`POST /api/dvf/export.xlsx → ${r.status}: ${await r.text()}`);
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = "transactions-dvf.xlsx";
  a.click();
  URL.revokeObjectURL(url);
}

export interface DvfPeriode {
  min: string | null;
  max: string | null;
}

/** Bornes temporelles des ventes DVF importées (curseur de période de la carte des prix). */
export async function fetchDvfPeriode(): Promise<DvfPeriode> {
  const r = await fetch("/api/dvf/periode");
  if (!r.ok) return { min: null, max: null };
  return r.json();
}

export interface SourceFraicheur {
  code: string;
  libelle: string;
  millesime: string | null;
  date_import: string;
}

/** Millésimes et dates d'import des données chargées en base (panneau Couches). */
export async function fetchSources(): Promise<SourceFraicheur[]> {
  const r = await fetch("/api/sources");
  if (!r.ok) return [];
  return (await r.json()).sources ?? [];
}

export interface BanSuggestion {
  label: string;
  lon: number;
  lat: number;
}

export async function searchAddress(q: string): Promise<BanSuggestion[]> {
  const r = await fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(q)}&limit=5`);
  if (!r.ok) return [];
  const data = await r.json();
  return (data.features ?? []).map((f: any) => ({
    label: f.properties.label,
    lon: f.geometry.coordinates[0],
    lat: f.geometry.coordinates[1],
  }));
}
