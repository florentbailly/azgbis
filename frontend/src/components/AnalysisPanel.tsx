import { useEffect, useState, type ReactNode } from "react";
import { createReport, downloadTransactionsExcel, getReportStatus } from "../api";
import type { AnalyzeResponse, Catalog, ThemeResult, ZoneInput } from "../types";

interface ParcelInfo {
  parcelle: any;
  zones_plu: any[];
  commune: any;
  statut_gpu?: any;
  avertissements: string[];
}

interface Props {
  catalog: Catalog | null;
  analysis: AnalyzeResponse | null;
  error: string | null;
  parcel: ParcelInfo | null;
  selectedThemes: Set<string>;
  onToggleTheme: (id: string) => void;
  zoneInput: ZoneInput | null;
  onClose: () => void;
}

export type { ParcelInfo };

/* --- Libellés métier des indicateurs (retour utilisateur du 16/07/2026 :
   restitution orientée conclusions, pas clés techniques) --- */
const LABELS: Record<string, string> = {
  argiles_rga: "Exposition retrait-gonflement des argiles",
  mouvements_terrain_nb: "Mouvements de terrain recensés",
  cavites_nb: "Cavités souterraines recensées",
  azi_nb: "Atlas des zones inondables (AZI)",
  tri_nb: "Territoires à risque important d'inondation (TRI)",
  procedures_gaspar_nb: "Procédures de prévention des risques (GASPAR)",
  radon_potentiel: "Potentiel radon (1 faible → 3 significatif)",
  zonage_sismique: "Zonage sismique",
  icpe_nb: "Installations classées (ICPE)",
  seveso_nb: "dont établissements Seveso",
  sites_pollues_casias_nb: "Anciens sites industriels (CASIAS)",
  sis_nb: "Secteurs d'information sur les sols (SIS)",
  conclusions_sup_nb: "Servitudes d'utilité publique « sols »",
  zones_plu_nb: "Zones de PLU intersectées",
  peb_present: "Plan d'exposition au bruit (PEB)",
  natura2000_nb: "Sites Natura 2000",
  znieff1_nb: "ZNIEFF de type I",
  znieff2_nb: "ZNIEFF de type II",
  espace_protege_nb: "Espaces protégés",
  patrimoine_geol_nb: "Patrimoine géologique",
  nb_transactions_zone_contexte: "Transactions (zone de contexte)",
};

const CATEGORY_LABELS: Record<string, string> = {
  icpe: "ICPE",
  casias: "Site CASIAS",
  sis: "SIS",
  mouvement_terrain: "Mouvement de terrain",
  cavite: "Cavité",
  azi: "AZI",
  tri: "TRI",
  procedure_gaspar: "Procédure",
  prescription: "Prescription",
  servitude: "Servitude",
  transaction: "Transaction",
  natura2000: "Natura 2000",
  znieff1: "ZNIEFF I",
  znieff2: "ZNIEFF II",
  espace_protege: "Espace protégé",
  patrimoine_geol: "Patrimoine géol.",
};

// Clés rendues par un bloc dédié : ne pas les répéter dans la liste générique.
const SPECIAL_KEYS = new Set(["zones_plu", "prescriptions", "servitudes", "par_typologie", "commune_gpu", "prescriptions_nb", "servitudes_nb"]);

const TITLE_FIELDS = [
  "nom", "libelle", "nom_etablissement", "raisonSociale", "raison_sociale", "nom_ouvrage",
  "libelle_azi", "libelle_tri", "libelle_risque_long", "type", "identifiant_ssp", "id_mutation",
];
const HIDDEN_FIELDS = new Set(["categorie", "geog", "geom", "geometry", "bbox"]);

function fmtVal(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "Oui" : "Non";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function prettifyKey(k: string): string {
  return k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

function ItemCard({ item }: { item: Record<string, unknown> }) {
  const cat = String(item.categorie ?? "");
  const title =
    TITLE_FIELDS.map((f) => item[f]).find((v) => v !== null && v !== undefined && v !== "") ?? "(sans libellé)";
  const fields = Object.entries(item)
    .filter(
      ([k, v]) =>
        !HIDDEN_FIELDS.has(k) &&
        !TITLE_FIELDS.includes(k) &&
        v !== null && v !== undefined && v !== "" &&
        (typeof v === "string" || typeof v === "number" || typeof v === "boolean") &&
        String(v).length <= 90,
    )
    .slice(0, 5);
  return (
    <div className="item-card">
      <div className="item-title">
        {cat && <span className="item-cat">{CATEGORY_LABELS[cat] ?? cat}</span>}
        {String(title)}
      </div>
      {fields.length > 0 && (
        <div className="item-fields">
          {fields.map(([k, v]) => `${prettifyKey(k)} : ${fmtVal(v)}`).join(" · ")}
        </div>
      )}
    </div>
  );
}

function SynthList({ title, entries }: { title: string; entries: any[] }) {
  if (!entries?.length) return null;
  return (
    <>
      <div className="synth-title">{title}</div>
      <ul className="synth-list">
        {entries.map((e, i) => (
          <li key={i}>
            <span className="lib">{e.libelle}</span>
            {e.nb > 1 && <span className="nb">×{e.nb}</span>}
            {e.libelong && <span className="desc">{e.libelong}</span>}
          </li>
        ))}
      </ul>
    </>
  );
}

/** Bouton d'export Excel des transactions (section Marché — ventes). */
function ExportTransactions({ zoneInput }: { zoneInput: ZoneInput | null }) {
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  if (!zoneInput) return null;
  return (
    <div style={{ margin: "6px 0" }}>
      <button
        className="secondary"
        disabled={enCours}
        onClick={async () => {
          setEnCours(true);
          setErreur(null);
          try {
            await downloadTransactionsExcel(zoneInput);
          } catch (e) {
            setErreur(String(e));
          } finally {
            setEnCours(false);
          }
        }}
      >
        {enCours ? "Préparation du fichier…" : "⬇ Télécharger les transactions (Excel)"}
      </button>
      {erreur && <div className="warning">{erreur}</div>}
    </div>
  );
}

function ThemeBlock({ result, color, libelle, extra }: { result: ThemeResult; color: string; libelle: string; extra?: ReactNode }) {
  const ind = result.indicateurs;
  return (
    <div className="result-theme">
      <h3 style={{ background: color }}>{libelle}</h3>
      <div className="result-body">
        {Object.entries(ind)
          .filter(([k]) => !SPECIAL_KEYS.has(k))
          .map(([k, v]) => (
            <div className="indicateur" key={k}>
              <span className="k">{LABELS[k] ?? prettifyKey(k)}</span>
              <span className="v">{Array.isArray(v) ? `${v.length}` : fmtVal(v)}</span>
            </div>
          ))}

        {ind.commune_gpu != null && (
          <div className="indicateur">
            <span className="k">Commune (GPU)</span>
            <span className="v">
              {(ind.commune_gpu as any).nom}
              {(ind.commune_gpu as any).rnu ? " — RNU" : ""}
            </span>
          </div>
        )}
        <SynthList title="Zonage PLU" entries={(ind.zones_plu as any[]) ?? []} />
        <SynthList
          title={`Prescriptions d'urbanisme${ind.prescriptions_nb ? ` (${ind.prescriptions_nb})` : ""}`}
          entries={(ind.prescriptions as any[]) ?? []}
        />
        <SynthList
          title={`Servitudes d'utilité publique${ind.servitudes_nb ? ` (${ind.servitudes_nb})` : ""}`}
          entries={(ind.servitudes as any[]) ?? []}
        />
        {Array.isArray(ind.par_typologie) && (ind.par_typologie as any[]).length > 0 && (
          <table className="mini">
            <thead>
              <tr><th>Typologie</th><th>Ventes</th><th>Prix/m² médian</th></tr>
            </thead>
            <tbody>
              {(ind.par_typologie as any[]).map((t, i) => (
                <tr key={i}>
                  <td>{t.typologie}</td>
                  <td className="num">{t.nb_transactions}</td>
                  <td className="num">{t.prix_m2_median ? `${t.prix_m2_median.toLocaleString("fr-FR")} €` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {extra}
        {result.avertissements.map((a, i) => (
          <div className="warning" key={i}>{a}</div>
        ))}
        {result.items.length > 0 && (
          <details className="items-details">
            <summary>{result.items.length} élément(s) détaillé(s)</summary>
            <div className="items-list">
              {result.items.map((it, i) => (
                <ItemCard item={it} key={i} />
              ))}
            </div>
          </details>
        )}
        {result.sources.length > 0 && (
          <p className="muted">
            Sources : {result.sources.map((s) => `${s.libelle} (${s.millesime ?? "live"})`).join(" · ")}
          </p>
        )}
      </div>
    </div>
  );
}

/** Génération du rapport PDF (spec §8) : formulaire de page de garde, dépôt du job,
 *  suivi jusqu'au lien de téléchargement. Le PDF est purgé côté serveur après 24 h. */
function ReportBlock({ zoneInput, themes }: { zoneInput: ZoneInput | null; themes: string[] }) {
  const [titre, setTitre] = useState("");
  const [clientRef, setClientRef] = useState("");
  const [auteur, setAuteur] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId || downloadUrl || (status && !["pending", "running"].includes(status))) return;
    const t = setInterval(async () => {
      try {
        const s = await getReportStatus(jobId);
        setStatus(s.status);
        if (s.status === "done") setDownloadUrl(s.download_url ?? null);
        if (s.status === "error") setErreur(s.erreur ?? "Erreur inconnue pendant la génération.");
      } catch (e) {
        setErreur(String(e));
        setStatus("error");
      }
    }, 3000);
    return () => clearInterval(t);
  }, [jobId, status, downloadUrl]);

  async function lancer() {
    if (!zoneInput || themes.length === 0) return;
    setErreur(null);
    setDownloadUrl(null);
    setStatus("pending");
    try {
      setJobId(await createReport(zoneInput, themes, { titre, client_ref: clientRef, auteur }));
    } catch (e) {
      setErreur(String(e));
      setStatus("error");
      setJobId(null);
    }
  }

  const enCours = ["pending", "running"].includes(status) && !downloadUrl;
  return (
    <div className="result-theme">
      <h3 style={{ background: "var(--brand-primary)" }}>Rapport PDF</h3>
      <div className="result-body">
        <input type="text" className="report-input" placeholder="Titre du rapport"
               value={titre} onChange={(e) => setTitre(e.target.value)} />
        <input type="text" className="report-input" placeholder="Référence dossier client"
               value={clientRef} onChange={(e) => setClientRef(e.target.value)} />
        <input type="text" className="report-input" placeholder="Auteur"
               value={auteur} onChange={(e) => setAuteur(e.target.value)} />
        <button onClick={lancer} disabled={!zoneInput || themes.length === 0 || enCours} style={{ width: "100%" }}>
          {enCours ? "Génération en cours…" : "Générer le rapport"}
        </button>
        {enCours && (
          <p className="muted">
            {status === "pending" ? "En file d'attente…" : "Analyse et cartes en cours (moins de 3 min)…"}
          </p>
        )}
        {downloadUrl && (
          <p>
            <a href={downloadUrl}><b>Télécharger le rapport PDF</b></a>
            <span className="muted"> — conservé 24 h, puis purgé.</span>
          </p>
        )}
        {erreur && <div className="warning">{erreur}</div>}
      </div>
    </div>
  );
}

export default function AnalysisPanel({ catalog, analysis, error, parcel, selectedThemes, onToggleTheme, zoneInput, onClose }: Props) {
  const analyseThemes = catalog?.themes.filter((t) => t.analyse) ?? [];
  return (
    <div className="panel panel-right">
      <button className="panel-close" onClick={onClose}>✕ fermer</button>
      <div className="app-title">Analyse de zone</div>
      <div>
        {analyseThemes.map((t) => (
          <div key={t.id} className="layer-row" style={{ paddingLeft: 0 }}>
            <input type="checkbox" id={`th-${t.id}`} checked={selectedThemes.has(t.id)} onChange={() => onToggleTheme(t.id)} />
            <label htmlFor={`th-${t.id}`} style={{ color: t.couleur, fontWeight: 600 }}>{t.libelle}</label>
          </div>
        ))}
      </div>
      <hr style={{ border: "none", borderTop: "1px solid #eee" }} />
      {parcel && (
        <div className="result-theme">
          <h3 style={{ background: "var(--theme-urbanisme)" }}>Parcelle sélectionnée</h3>
          <div className="result-body">
            {parcel.parcelle ? (
              <>
                <div className="indicateur"><span className="k">Référence</span>
                  <span className="v">{parcel.parcelle.properties?.section} {parcel.parcelle.properties?.numero}</span></div>
                <div className="indicateur"><span className="k">Contenance</span>
                  <span className="v">{fmtVal(parcel.parcelle.properties?.contenance)} m²</span></div>
                <div className="indicateur"><span className="k">Commune</span>
                  <span className="v">{parcel.commune?.nom} ({parcel.commune?.code})</span></div>
              </>
            ) : (
              <p className="muted">Aucune parcelle à cet endroit.</p>
            )}
            {parcel.zones_plu.map((z, i) => (
              <div className="indicateur" key={i}>
                <span className="k">Zone PLU</span>
                <span className="v">
                  {z.libelle} ({z.typezone}){z.urlfic ? <> · <a href={z.urlfic} target="_blank" rel="noreferrer">règlement</a></> : null}
                </span>
              </div>
            ))}
            {parcel.avertissements.map((a, i) => <div className="warning" key={i}>{a}</div>)}
          </div>
        </div>
      )}
      {error && <div className="warning">{error}</div>}
      {analysis && (
        <>
          <div className="zone-resume">
            <b>Zone d'étude :</b> {((analysis.zone_resume.surface_zone_etude_m2 as number) / 10000).toFixed(1)} ha
            {" · "}contexte : {((analysis.zone_resume.surface_zone_contexte_m2 as number) / 10000).toFixed(1)} ha
            {analysis.zone_resume.code_insee_centre ? ` · commune ${analysis.zone_resume.code_insee_centre}` : ""}
          </div>
          <ReportBlock zoneInput={zoneInput} themes={[...selectedThemes]} />
          {analysis.resultats.map((r) => {
            const t = catalog?.themes.find((x) => x.id === r.theme);
            return (
              <ThemeBlock
                key={r.theme}
                result={r}
                color={t?.couleur ?? "#7F7F7F"}
                libelle={t?.libelle ?? r.theme}
                extra={r.theme === "marche_ventes" ? <ExportTransactions zoneInput={zoneInput} /> : undefined}
              />
            );
          })}
        </>
      )}
      {!analysis && !error && <p className="muted">Tracez une zone (point + rayons ou polygone) puis « Analyser la zone ».</p>}
    </div>
  );
}
