import { useEffect, useMemo, useState } from "react";
import { analyzeZone, fetchCatalog, fetchSources, type SourceFraicheur } from "./api";
import AnalysisPanel, { type ParcelInfo } from "./components/AnalysisPanel";
import LayerPanel from "./components/LayerPanel";
import MapView from "./components/MapView";
import ZoneToolbar from "./components/ZoneToolbar";
import { TYPOLOGIE_ORDRE } from "./typologies";
import type { AnalyzeResponse, Catalog, ZoneInput } from "./types";
import { initialDraft, loadDraft, parcelleToZone, saveDraft, toFeatures, toZoneInput, zoneInputToDraft, type ZoneDraft } from "./zone";

const DEFAULT_THEMES = ["risques_naturels", "risques_technologiques", "environnement", "urbanisme", "marche_ventes"];

/** Mode « rendu » : chargé par le worker de rapports (Playwright) pour les cartes
 *  statiques du PDF — carte seule, zone et couches imposées par l'URL, aucun panneau.
 *  Ex. /?rendu=1&couches=natura2000,znieff&zone={"type":"point_radii",…} */
function lireModeRendu(): { couches: string[]; zone: ZoneInput | null } | null {
  const q = new URLSearchParams(window.location.search);
  if (!q.get("rendu")) return null;
  let zone: ZoneInput | null = null;
  try {
    zone = JSON.parse(q.get("zone") ?? "null");
  } catch {
    zone = null;
  }
  const couches = (q.get("couches") ?? "").split(",").filter(Boolean);
  return { couches, zone };
}

const MODE_RENDU = lireModeRendu();

export default function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [activeLayerIds, setActiveLayerIds] = useState<Set<string>>(
    () => new Set(MODE_RENDU?.couches ?? []),
  );
  // Filtre typologique de la carte des prix (toutes cochées = tuiles précalculées).
  const [typologiesPrix, setTypologiesPrix] = useState<string[]>([...TYPOLOGIE_ORDRE]);
  const [draft, setDraft] = useState<ZoneDraft>(() => {
    if (MODE_RENDU) return MODE_RENDU.zone ? zoneInputToDraft(MODE_RENDU.zone) : initialDraft;
    return loadDraft() ?? initialDraft;
  });
  const [selectedThemes, setSelectedThemes] = useState<Set<string>>(new Set(DEFAULT_THEMES));
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [parcel, setParcel] = useState<ParcelInfo | null>(null);
  const [flyTo, setFlyTo] = useState<[number, number] | null>(null);
  // Petit écran : les panneaux deviennent des tiroirs et démarrent fermés (la carte d'abord).
  const [leftOpen, setLeftOpen] = useState(() => !window.matchMedia("(max-width: 900px)").matches);
  const [rightOpen, setRightOpen] = useState(() => !window.matchMedia("(max-width: 900px)").matches);
  const [sources, setSources] = useState<SourceFraicheur[]>([]);

  useEffect(() => {
    fetchCatalog().then(setCatalog).catch((e) => setError(`Catalogue de couches inaccessible : ${e}`));
    fetchSources().then(setSources).catch(() => setSources([]));
  }, []);

  useEffect(() => {
    if (!MODE_RENDU) saveDraft(draft);
  }, [draft]);

  const zoneFeatures = useMemo(() => {
    const fc = toFeatures(draft);
    // Surlignage de la parcelle sélectionnée sur la carte (retour utilisateur 16/07/2026).
    if (parcel?.parcelle?.geometry) {
      fc.features.push({
        type: "Feature",
        geometry: parcel.parcelle.geometry,
        properties: { role: "parcelle" },
      });
    }
    return fc;
  }, [draft, parcel]);
  // Mode « Parcelle » : la zone d'analyse est la parcelle sélectionnée elle-même
  // (le tracé ne produit rien dans ce mode — le bouton restait grisé à tort).
  const zoneInput = useMemo(
    () => (draft.mode === "select" ? parcelleToZone(parcel?.parcelle?.geometry) : toZoneInput(draft)),
    [draft, parcel],
  );

  function updateDraft(d: ZoneDraft) {
    setDraft(d);
  }

  async function onMapClick(lon: number, lat: number) {
    if (draft.mode === "point") {
      setDraft({ ...draft, center: [lon, lat] });
    } else if (draft.mode === "polygon" && !draft.polygonClosed) {
      setDraft({ ...draft, polygonPoints: [...draft.polygonPoints, [lon, lat]] });
    } else if (draft.mode === "select") {
      try {
        const r = await fetch(`/api/parcelles/lookup?lon=${lon}&lat=${lat}`);
        setParcel(await r.json());
      } catch (e) {
        setParcel({ parcelle: null, zones_plu: [], commune: null, avertissements: [String(e)] });
      }
    }
  }

  async function onAnalyze() {
    if (!zoneInput || selectedThemes.size === 0) return;
    setAnalyzing(true);
    setError(null);
    try {
      setAnalysis(await analyzeZone(zoneInput, [...selectedThemes]));
    } catch (e) {
      setError(String(e));
    } finally {
      setAnalyzing(false);
    }
  }

  if (MODE_RENDU) {
    return (
      <div className="app">
        <div className="map-container">
          <MapView
            catalog={catalog}
            activeLayerIds={activeLayerIds}
            zoneFeatures={zoneFeatures}
            onMapClick={() => undefined}
            flyTo={null}
            rendu
          />
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      {leftOpen && (
        <LayerPanel
          catalog={catalog}
          activeLayerIds={activeLayerIds}
          sources={sources}
          typologiesPrix={typologiesPrix}
          onClose={() => setLeftOpen(false)}
          onToggle={(id) =>
            setActiveLayerIds((prev) => {
              const next = new Set(prev);
              next.has(id) ? next.delete(id) : next.add(id);
              return next;
            })
          }
          onToggleTypologie={(code) =>
            setTypologiesPrix((prev) =>
              prev.includes(code)
                ? prev.length > 1 ? prev.filter((c) => c !== code) : prev // jamais zéro
                : [...prev, code],
            )
          }
        />
      )}
      <div className="map-container">
        <button className="panel-toggle left" onClick={() => setLeftOpen((v) => !v)}>
          {leftOpen ? "◀ masquer" : "Couches ▶"}
        </button>
        <button className="panel-toggle right" onClick={() => setRightOpen((v) => !v)}>
          {rightOpen ? "masquer ▶" : "◀ Analyse"}
        </button>
        <ZoneToolbar
          draft={draft}
          onDraftChange={updateDraft}
          onAnalyze={onAnalyze}
          analyzing={analyzing}
          canAnalyze={zoneInput !== null && selectedThemes.size > 0}
          onFlyTo={setFlyTo}
        />
        <MapView
          catalog={catalog}
          activeLayerIds={activeLayerIds}
          typologiesPrix={typologiesPrix}
          zoneFeatures={zoneFeatures}
          onMapClick={onMapClick}
          flyTo={flyTo}
        />
      </div>
      {rightOpen && (
        <AnalysisPanel
          catalog={catalog}
          analysis={analysis}
          error={error}
          parcel={parcel}
          zoneInput={zoneInput}
          onClose={() => setRightOpen(false)}
          selectedThemes={selectedThemes}
          onToggleTheme={(id) =>
            setSelectedThemes((prev) => {
              const next = new Set(prev);
              next.has(id) ? next.delete(id) : next.add(id);
              return next;
            })
          }
        />
      )}
    </div>
  );
}
