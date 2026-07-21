import { useState } from "react";
import { searchAddress, type BanSuggestion } from "../api";
import type { DrawMode } from "../types";
import type { ZoneDraft } from "../zone";

interface Props {
  draft: ZoneDraft;
  onDraftChange: (d: ZoneDraft) => void;
  onAnalyze: () => void;
  analyzing: boolean;
  canAnalyze: boolean;
  onFlyTo: (lonlat: [number, number]) => void;
}

export default function ZoneToolbar({ draft, onDraftChange, onAnalyze, analyzing, canAnalyze, onFlyTo }: Props) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<BanSuggestion[]>([]);
  const [repliee, setRepliee] = useState(false);

  const setMode = (mode: DrawMode) =>
    onDraftChange({ ...draft, mode, polygonPoints: [], polygonClosed: false, center: mode === "point" ? draft.center : null });

  async function onSearch(q: string) {
    setQuery(q);
    setSuggestions(q.length >= 3 ? await searchAddress(q) : []);
  }

  // Barre repliée : un simple bouton pour dégager la carte (le tracé reste actif).
  if (repliee) {
    return (
      <div className="toolbar toolbar-repliee">
        <button className="secondary" onClick={() => setRepliee(false)} title="Déplier la sélection de zone">
          Zone d'étude ▾
        </button>
      </div>
    );
  }

  return (
    <div className="toolbar">
      <div className="toolbar-row">
        <input
          type="text"
          placeholder="Adresse ou commune (BAN)…"
          value={query}
          onChange={(e) => onSearch(e.target.value)}
        />
        <button className="toolbar-plier" onClick={() => setRepliee(true)} title="Replier la sélection de zone">
          ▴
        </button>
      </div>
      {suggestions.length > 0 && (
        <div className="suggestions">
          {suggestions.map((s) => (
            <div
              key={s.label}
              onClick={() => {
                onFlyTo([s.lon, s.lat]);
                setQuery(s.label);
                setSuggestions([]);
                if (draft.mode === "point") onDraftChange({ ...draft, center: [s.lon, s.lat] });
              }}
            >
              {s.label}
            </div>
          ))}
        </div>
      )}
      <div className="toolbar-row">
        <button className={`secondary ${draft.mode === "select" ? "active-mode" : ""}`} onClick={() => setMode("select")}>
          Parcelle
        </button>
        <button className={`secondary ${draft.mode === "point" ? "active-mode" : ""}`} onClick={() => setMode("point")}>
          Point + rayons
        </button>
        <button className={`secondary ${draft.mode === "polygon" ? "active-mode" : ""}`} onClick={() => setMode("polygon")}>
          Polygone
        </button>
      </div>
      {draft.mode === "point" && (
        <div className="toolbar-row">
          <span className="muted">Rayons (m)</span>
          <input
            type="number" min={50} step={50} value={draft.smallRadiusM}
            onChange={(e) => onDraftChange({ ...draft, smallRadiusM: Number(e.target.value) })}
            title="Petit rayon : zone d'étude"
          />
          <input
            type="number" min={50} step={50} value={draft.largeRadiusM}
            onChange={(e) => onDraftChange({ ...draft, largeRadiusM: Number(e.target.value) })}
            title="Grand rayon : zone de contexte / comparables"
          />
          {!draft.center && <span className="muted">Cliquer sur la carte pour placer le centre.</span>}
        </div>
      )}
      {draft.mode === "polygon" && (
        <div className="toolbar-row">
          <span className="muted">
            {draft.polygonClosed
              ? `Polygone fermé (${draft.polygonPoints.length} sommets).`
              : `Cliquer pour ajouter des sommets (${draft.polygonPoints.length}).`}
          </span>
          {!draft.polygonClosed && draft.polygonPoints.length >= 3 && (
            <button onClick={() => onDraftChange({ ...draft, polygonClosed: true })}>Terminer</button>
          )}
          {draft.polygonPoints.length > 0 && (
            <button className="secondary" onClick={() => onDraftChange({ ...draft, polygonPoints: [], polygonClosed: false })}>
              Effacer
            </button>
          )}
        </div>
      )}
      <div className="toolbar-row">
        <button onClick={onAnalyze} disabled={!canAnalyze || analyzing}>
          {analyzing ? "Analyse en cours…" : "Analyser la zone"}
        </button>
        {draft.mode === "select" && (
          <span className="muted">
            {canAnalyze
              ? "L'analyse portera sur la parcelle sélectionnée."
              : "Activez la couche « Parcelles cadastrales » puis cliquez sur une parcelle : sa fiche s'affiche dans le panneau Analyse."}
          </span>
        )}
      </div>
    </div>
  );
}
