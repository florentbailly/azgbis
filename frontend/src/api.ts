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
