"""Synthèse en une page (spec §8 ③) : un point d'attention par thème.

Règles volontairement simples et lisibles — le tableau de bord signale « à examiner »
(rouge charte) ou « rien de notable » (teal), jamais une conclusion d'expertise :
la conclusion reste à l'expert, section par section.
"""
from ..schemas import ThemeResult

VIGILANCE, OK, INDISPONIBLE = "vigilance", "ok", "indisponible"


def _nb(ind: dict, *cles: str) -> int:
    total = 0
    for c in cles:
        v = ind.get(c)
        if isinstance(v, (int, float)):
            total += int(v)
        elif isinstance(v, list):
            total += len(v)
    return total


def _point(r: ThemeResult) -> tuple[str, str]:
    ind = r.indicateurs
    if not ind and r.avertissements:
        return INDISPONIBLE, "Données indisponibles — voir les avertissements de la section."

    if r.theme == "risques_naturels":
        nb = _nb(ind, "mouvements_terrain_nb", "cavites_nb", "azi_nb", "tri_nb")
        rga = str(ind.get("argiles_rga") or "")
        if "fort" in rga.lower():
            return VIGILANCE, f"Aléa argiles {rga} ; {nb} élément(s) de risque recensé(s)."
        if nb:
            return VIGILANCE, f"{nb} élément(s) de risque recensé(s) (inondation, mouvement, cavité)."
        return OK, "Aucun risque naturel notable recensé sur la zone."

    if r.theme == "risques_technologiques":
        nb = _nb(ind, "icpe_nb", "sis_nb", "sites_pollues_casias_nb")
        if nb:
            return VIGILANCE, f"{nb} installation(s) ou site(s) recensé(s) (ICPE, SIS, CASIAS)."
        return OK, "Aucune installation classée ni site pollué recensé."

    if r.theme == "environnement":
        nb = _nb(ind, "natura2000_nb", "znieff1_nb", "znieff2_nb", "espace_protege_nb", "patrimoine_geol_nb")
        if nb:
            return VIGILANCE, f"{nb} zonage(s) environnementaux intersectent la zone."
        return OK, "Aucun zonage environnemental n'intersecte la zone."

    if r.theme == "urbanisme":
        servitudes = _nb(ind, "servitudes_nb")
        if servitudes:
            return VIGILANCE, f"{servitudes} servitude(s) d'utilité publique sur la zone."
        if _nb(ind, "zones_plu_nb"):
            return OK, f"{_nb(ind, 'zones_plu_nb')} zone(s) de PLU, sans servitude signalée."
        return INDISPONIBLE, "Zonage d'urbanisme non disponible (commune hors GPU ?)."

    if r.theme == "marche_ventes":
        nb = _nb(ind, "nb_transactions_zone_contexte")
        if nb:
            return OK, f"{nb} transaction(s) comparable(s) dans la zone de contexte."
        return INDISPONIBLE, "Aucune transaction disponible — vérifier la couverture DVF du secteur."

    return INDISPONIBLE, "Thème non couvert par la synthèse."


def construire(resultats: list[ThemeResult]) -> list[dict]:
    out = []
    for r in resultats:
        niveau, message = _point(r)
        out.append({"theme": r.theme, "niveau": niveau, "message": message})
    return out
