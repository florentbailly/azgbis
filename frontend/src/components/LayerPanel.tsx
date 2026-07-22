import type { SourceFraicheur } from "../api";
import { TYPOLOGIE_LABELS, TYPOLOGIE_ORDRE } from "../typologies";
import type { Catalog } from "../types";

interface Props {
  catalog: Catalog | null;
  activeLayerIds: Set<string>;
  sources: SourceFraicheur[];
  typologiesPrix: string[];
  onToggle: (layerId: string) => void;
  onToggleTypologie: (code: string) => void;
  onClose: () => void;
}

/* Libellés courts des sources importées en base (le libellé stocké mentionne un
   département ou une année précise, peu parlant en synthèse). */
const SOURCE_LABELS: Record<string, string> = {
  dvf: "Ventes DVF (DGFiP / Etalab)",
  cadastre: "Contours cadastraux (Etalab)",
  admin: "Contours administratifs (Etalab)",
  radon: "Potentiel radon (IRSN)",
  bdtopo: "Bâtiments BD TOPO (IGN)",
  sirene: "Établissements SIRENE (INSEE)",
};

function frDateHeure(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR");
}

export default function LayerPanel({ catalog, activeLayerIds, sources, typologiesPrix, onToggle, onToggleTypologie, onClose }: Props) {
  if (!catalog) return <div className="panel panel-left">Chargement du catalogue…</div>;
  return (
    <div className="panel panel-left" title="Bord droit étirable pour redimensionner">
      <button className="panel-close" onClick={onClose}>✕ fermer</button>
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
              <div key={l.id}>
                <div className="layer-row">
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
                {/* Filtre typologique de la carte des prix (spec §5) : recalcul des
                    médianes à la volée côté tuiles dès qu'une case est décochée. */}
                {l.rendu === "prix_m2" && activeLayerIds.has(l.id) && (
                  <div className="typo-filtre">
                    <div className="typo-filtre-titre">Typologies affichées</div>
                    {TYPOLOGIE_ORDRE.map((code) => (
                      <div key={code} className="layer-row typo-filtre-ligne">
                        <input
                          type="checkbox"
                          id={`typo-${code}`}
                          checked={typologiesPrix.includes(code)}
                          disabled={typologiesPrix.length === 1 && typologiesPrix.includes(code)}
                          onChange={() => onToggleTypologie(code)}
                        />
                        <label htmlFor={`typo-${code}`}>{TYPOLOGIE_LABELS[code]}</label>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </details>
        );
      })}
      <details className="theme-group">
        <summary className="theme-header">Fraîcheur des données</summary>
        <div className="fraicheur">
          {sources.length === 0 ? (
            <p className="muted">Aucune donnée importée en base (ou base indisponible).</p>
          ) : (
            <table className="mini">
              <thead>
                <tr><th>Donnée</th><th>Millésime</th><th>Importée le</th></tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.code}>
                    <td>{SOURCE_LABELS[s.code] ?? s.libelle}</td>
                    <td>{s.millesime ?? "—"}</td>
                    <td>{frDateHeure(s.date_import)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted">
            Les couches « live » (Géorisques, IGN, GPU…) interrogent le service officiel
            en direct : leur fraîcheur est celle du service au moment de l'affichage.
          </p>
        </div>
      </details>
      <p className="muted">
        Couches « batch » : visibles après le premier import du pipeline (pipeline/README.md).
      </p>
    </div>
  );
}
