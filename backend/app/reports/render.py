"""Assemblage du rapport (spec §8 ③) : contexte Python → gabarit Jinja2 → WeasyPrint.

Tout le travail de mise en forme (libellés, tri, agrégats de traçabilité) est fait ici ;
le gabarit HTML ne contient que de la structure. Les cartes arrivent en PNG (bytes) et
sont inlinées en data-URI : le PDF est autonome, aucun fichier annexe.
"""
import base64
import datetime
import zoneinfo
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import catalog, config
from ..schemas import AnalyzeResponse, ReportRequest, ThemeResult
from . import libelles, synthese

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)

PARIS = zoneinfo.ZoneInfo("Europe/Paris")


def _fr_nombre(v: Any) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (int, float)):
        return f"{v:,}".replace(",", " ")
    return str(v)


def _fmt(v: Any) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return "Oui" if v else "Non"
    if isinstance(v, (int, float)):
        return _fr_nombre(v)
    return str(v)


_env.filters["fr_nombre"] = _fr_nombre
_env.filters["fmt"] = _fmt
# Codes typologie (spec §5) → libellés métier, partagés avec l'écran et l'Excel.
_env.filters["typologie"] = lambda v: libelles.TYPOLOGIES.get(str(v), _fmt(v))


def _theme_meta(theme_id: str) -> dict:
    for t in catalog.THEMES:
        if t["id"] == theme_id:
            return t
    return {"id": theme_id, "libelle": theme_id, "couleur": "#7F7F7F"}


def _titre_item(item: dict) -> str:
    for f in libelles.TITLE_FIELDS:
        v = item.get(f)
        if v not in (None, ""):
            return str(v)
    return "(sans libellé)"


def _champs_item(item: dict, max_champs: int = 5) -> str:
    """Mêmes règles de sélection que la fiche du panneau Analyse (front)."""
    parts = []
    for k, v in item.items():
        if k in libelles.HIDDEN_FIELDS or k in libelles.TITLE_FIELDS:
            continue
        if v in (None, "") or not isinstance(v, (str, int, float, bool)):
            continue
        if len(str(v)) > 90:
            continue
        cle = k.replace("_", " ").capitalize()
        parts.append(f"{cle} : {_fmt(v)}")
        if len(parts) >= max_champs:
            break
    return " · ".join(parts)


def _indicateurs(r: ThemeResult) -> list[tuple[str, str]]:
    exclus = {"zones_plu", "prescriptions", "servitudes", "par_typologie", "commune_gpu",
              "prescriptions_nb", "servitudes_nb"}
    lignes = []
    for k, v in r.indicateurs.items():
        if k in exclus:
            continue
        val = f"{len(v)}" if isinstance(v, list) else _fmt(v)
        lignes.append((libelles.LABELS.get(k, k.replace("_", " ").capitalize()), val))
    return lignes


def _wkt_polygone(geometry: dict, precision: int = 6) -> str:
    rings = []
    for ring in geometry.get("coordinates", []):
        pts = ", ".join(f"{round(x, precision)} {round(y, precision)}" for x, y in ring)
        rings.append(f"({pts})")
    return f"POLYGON({', '.join(rings)})"


def _definition_zone(demande: ReportRequest, analyse: AnalyzeResponse) -> dict:
    z = demande.zone
    resume = analyse.zone_resume
    d: dict[str, Any] = {
        "surface_etude_ha": round(resume.get("surface_zone_etude_m2", 0) / 10_000, 2),
        "surface_contexte_ha": round(resume.get("surface_zone_contexte_m2", 0) / 10_000, 2),
        "code_insee": resume.get("code_insee_centre"),
    }
    if z.type == "point_radii":
        lon, lat = z.center  # type: ignore[misc]
        d["type"] = "Point + rayons"
        d["detail"] = (f"Centre {round(lat, 6)} N, {round(lon, 6)} E — rayon d'étude "
                       f"{_fr_nombre(z.small_radius_m)} m, contexte {_fr_nombre(z.large_radius_m)} m")
    else:
        d["type"] = "Polygone"
        d["detail"] = _wkt_polygone(z.geometry or {})
    return d


def _tracabilite(resultats: list[ThemeResult]) -> list[dict]:
    vus: dict[tuple, dict] = {}
    for r in resultats:
        for s in r.sources:
            cle = (s.code, s.libelle, s.millesime)
            vus.setdefault(cle, {"code": s.code, "libelle": s.libelle, "url": s.url,
                                 "millesime": s.millesime or "appel en direct à la génération"})
    return sorted(vus.values(), key=lambda s: s["code"])


def _b64(png: bytes | None) -> str | None:
    return base64.b64encode(png).decode() if png else None


def html_rapport(demande: ReportRequest, analyse: AnalyzeResponse,
                 images: dict[str, bytes], avert_cartes: list[str]) -> str:
    genere_le = datetime.datetime.now(PARIS)

    sections = []
    for r in analyse.resultats:
        meta = _theme_meta(r.theme)
        # « elements » et non « items » : en Jinja, `s.items` résoudrait la méthode
        # dict.items au lieu de la clé.
        elements = [{"categorie": libelles.CATEGORY_LABELS.get(str(i.get("categorie", "")), str(i.get("categorie", ""))),
                     "titre": _titre_item(i), "champs": _champs_item(i)}
                    for i in r.items[:30]]
        sections.append({
            "id": r.theme,
            "libelle": meta["libelle"],
            "couleur": meta["couleur"],
            "carte": _b64(images.get(r.theme)),
            "indicateurs": _indicateurs(r),
            "par_typologie": r.indicateurs.get("par_typologie") or [],
            "zones_plu": r.indicateurs.get("zones_plu") or [],
            "servitudes": r.indicateurs.get("servitudes") or [],
            "prescriptions": r.indicateurs.get("prescriptions") or [],
            "elements": elements,
            "nb_items_total": len(r.items),
            "avertissements": r.avertissements,
            "note_methodo": libelles.NOTES_METHODO.get(r.theme, ""),
        })

    transactions = []
    icpe_sis = []
    for r in analyse.resultats:
        if r.theme == "marche_ventes":
            transactions = [i for i in r.items if i.get("categorie") == "transaction"]
        if r.theme == "risques_technologiques":
            icpe_sis = [{"categorie": libelles.CATEGORY_LABELS.get(str(i.get("categorie", "")), ""),
                         "titre": _titre_item(i), "champs": _champs_item(i, max_champs=7)}
                        for i in r.items]

    ctx = {
        "titre": demande.titre or "Qualification de zone",
        "client_ref": demande.client_ref,
        "auteur": demande.auteur,
        "genere_le": genere_le.strftime("%d/%m/%Y à %H:%M (heure de Paris)"),
        "version_app": config.APP_VERSION,
        "carte_situation": _b64(images.get("situation")),
        "zone": _definition_zone(demande, analyse),
        "synthese": [
            {**pt, "libelle": _theme_meta(pt["theme"])["libelle"]}
            for pt in synthese.construire(analyse.resultats)
        ],
        "sections": sections,
        "transactions": transactions,
        "icpe_sis": icpe_sis,
        "avert_cartes": avert_cartes,
        "tracabilite": _tracabilite(analyse.resultats),
    }
    return _env.get_template("rapport.html.j2").render(**ctx)


def pdf(html: str) -> bytes:
    """Rendu WeasyPrint — appel bloquant, à exécuter via asyncio.to_thread."""
    from weasyprint import HTML

    return HTML(string=html).write_pdf()
