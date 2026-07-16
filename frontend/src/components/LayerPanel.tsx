import type { Catalog } from "../types";

interface Props {
  catalog: Catalog | null;
  activeLayerIds: Set<string>;
  onToggle: (layerId: string) => void;
}

export default function LayerPanel({ catalog, activeLayerIds, onToggle }: Props) {
  if (!catalog) return <div className="panel panel-left">Chargement du catalogue…</div>;
  return (
    <div className="panel panel-left" title="Bord droit étirable pour redimensionner">
      <div className="app-title">Couches à visualiser</div>
      {catalog.themes.map((theme) => {
        const layers = catalog.layers.filter((l) => l.theme === theme.id);
        if (layers.length === 0) return null;
        return (
          <details key={theme.id} className="theme-group" open={theme.id !== "fonds"}>
            <summary className="theme-header" style={{ borderLeftColor: theme.couleur }}>
              <span className="theme-dot" style={{ background: theme.couleur }} />
              {theme.libelle}
            </summary>
            {layers.map((l) => (
              <div key={l.id} className="layer-row">
                <input
                  type="checkbox"
                  id={`layer-${l.id}`}
                  checked={activeLayerIds.has(l.id)}
                  onChange={() => onToggle(l.id)}
                />
                <label htmlFor={`layer-${l.id}`}>{l.libelle}</label>
                {!l.flux_confirme && <span className="badge-unconfirmed" title="URL/nom du flux à confirmer (T-01)">flux à confirmer</span>}
                {l.mode === "batch" && <span className="badge-unconfirmed" title="Servie par le pipeline batch">batch</span>}
              </div>
            ))}
          </details>
        );
      })}
      <p className="muted">
        Couches « batch » : visibles après le premier import du pipeline (pipeline/README.md).
      </p>
    </div>
  );
}
