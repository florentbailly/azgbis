"""Thème Urbanisme & foncier — GPU et cadastre via API Carto, en live (spec §3.4)."""
import asyncio

from .. import config
from ..clients import apicarto as ac
from ..geo import Zone, geojson_param
from ..schemas import ThemeResult
from .common import collect, source


def _features(fc: dict) -> list[dict]:
    return fc.get("features", []) if isinstance(fc, dict) else []


# Libellés métier des codes de servitudes d'utilité publique les plus fréquents.
SUP_LABELS = {
    "AC1": "abords de monuments historiques",
    "AC2": "sites inscrits/classés",
    "AC4": "site patrimonial remarquable (SPR/AVAP)",
    "AS1": "protection des captages d'eau potable",
    "EL7": "alignement de voirie",
    "I3": "canalisations de gaz",
    "I4": "lignes électriques",
    "PM1": "plan de prévention des risques naturels",
    "PM2": "installations classées / sols pollués",
    "PM3": "plan de prévention des risques technologiques",
    "PT1": "protections radioélectriques (réception)",
    "PT2": "protections radioélectriques (obstacles)",
    "PT3": "réseaux de télécommunications",
    "T1": "voies ferrées",
    "T5": "dégagement aéronautique (dont PEB)",
    "A5": "canalisations d'eau et d'assainissement",
}


async def analyze(zone: Zone, code_insee: str | None) -> ThemeResult:
    r = ThemeResult(theme="urbanisme")
    source(r, "gpu", "Géoportail de l'Urbanisme (via API Carto IGN)", config.APICARTO_API)
    geom, degraded = geojson_param(zone.small_wgs84)
    if degraded:
        r.avertissements.append(
            "Géométrie simplifiée pour l'interrogation du GPU (limite de taille d'URL, cf. T-04) : "
            "les intersections en bordure de zone sont à vérifier."
        )

    def set_zones(fc: dict) -> None:
        feats = _features(fc)
        zonages: dict[str, dict] = {}
        for f in feats:
            p = f.get("properties", {})
            key = f"{p.get('typezone', '?')}|{p.get('libelle', '?')}"
            zonages.setdefault(key, {"typezone": p.get("typezone"), "libelle": p.get("libelle"),
                                     "libelong": p.get("libelong"), "urlfic": p.get("urlfic"), "nb": 0})
            zonages[key]["nb"] += 1
        r.indicateurs["zones_plu"] = sorted(zonages.values(), key=lambda x: str(x["typezone"]))
        r.indicateurs["zones_plu_nb"] = len(feats)

    def _grouped(feats: list[dict], key: str = "libelle") -> list[dict]:
        """Regroupe les entités par libellé : c'est la synthèse lisible par l'expert,
        plutôt qu'un simple comptage (retour utilisateur du 16/07/2026)."""
        groups: dict[str, dict] = {}
        for f in feats:
            p = f.get("properties", {})
            lib = str(p.get(key) or p.get("txt") or "Sans libellé").strip()
            g = groups.setdefault(lib, {"libelle": lib, "nb": 0, "types": set()})
            g["nb"] += 1
            if p.get("typepsc") or p.get("typesup"):
                g["types"].add(str(p.get("typepsc") or p.get("typesup")))
        return [
            {"libelle": g["libelle"], "nb": g["nb"], "types": sorted(g["types"])}
            for g in sorted(groups.values(), key=lambda x: -x["nb"])
        ]

    def set_prescriptions(fc: dict) -> None:
        feats = _features(fc)
        r.indicateurs["prescriptions"] = _grouped(feats)[:20]
        r.indicateurs["prescriptions_nb"] = len(feats)
        r.items.extend(
            {"categorie": "prescription", **f.get("properties", {})} for f in feats[:100]
        )

    def set_servitudes(fc: dict) -> None:
        feats = _features(fc)
        # Les servitudes GPU portent suptype (code SUP) + nomsuplitt (nom du générateur),
        # pas de champ libelle : regroupement par code SUP avec exemples nominatifs.
        groups: dict[str, dict] = {}
        for f in feats:
            p = f.get("properties", {})
            code = str(p.get("suptype") or "?").upper()
            g = groups.setdefault(code, {"code": code, "nb": 0, "exemples": []})
            g["nb"] += 1
            nom = p.get("nomsuplitt") or p.get("typeass")
            if nom and nom not in g["exemples"] and len(g["exemples"]) < 4:
                g["exemples"].append(str(nom))
        r.indicateurs["servitudes"] = [
            {
                "libelle": f"{g['code']} — {SUP_LABELS.get(g['code'], 'servitude')}",
                "nb": g["nb"],
                "libelong": ", ".join(g["exemples"]) or None,
            }
            for g in sorted(groups.values(), key=lambda x: -x["nb"])
        ][:20]
        r.indicateurs["servitudes_nb"] = len(feats)
        r.indicateurs["peb_present"] = any(g["code"] == "T5" for g in groups.values())
        r.items.extend({"categorie": "servitude", **f.get("properties", {})} for f in feats[:100])

    def set_municipality(payload: dict) -> None:
        feats = _features(payload) or ([payload] if payload else [])
        if feats:
            p = feats[0].get("properties", feats[0])
            r.indicateurs["commune_gpu"] = {"rnu": p.get("is_rnu"), "nom": p.get("name") or p.get("nom")}
            if p.get("is_rnu"):
                r.avertissements.append(
                    "Commune au RNU (règlement national d'urbanisme) : pas de document local au GPU."
                )

    tasks = [
        collect(r, "Zonage PLU (GPU)", ac.gpu_zone_urba(geom), set_zones),
        collect(r, "Prescriptions surfaciques (GPU)", ac.gpu_prescriptions_surf(geom), set_prescriptions),
        collect(r, "Servitudes d'utilité publique (GPU)", ac.gpu_servitudes_surf(geom), set_servitudes),
    ]
    if code_insee:
        tasks.append(collect(r, "Statut GPU de la commune", ac.gpu_municipality(code_insee), set_municipality))
    await asyncio.gather(*tasks)

    if not r.indicateurs.get("zones_plu_nb") and not r.avertissements:
        r.avertissements.append(
            "Aucun zonage retourné par le GPU sur cette zone : document non versé au GPU — vérifier en mairie."
        )
    return r
