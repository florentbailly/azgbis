"""Thème Risques naturels — sources live Géorisques (spec §3.1)."""
import asyncio

from .. import config
from ..clients import georisques as gr
from ..geo import Zone
from ..schemas import ThemeResult
from .common import collect, source


async def analyze(zone: Zone, code_insee: str | None) -> ThemeResult:
    r = ThemeResult(theme="risques_naturels")
    source(r, "georisques", "Géorisques (BRGM / MTE)", config.GEORISQUES_API)
    lon, lat = zone.centroid_lonlat
    radius = zone.small_radius_m

    def set_rga(payload: dict) -> None:
        expo = payload.get("exposition") or payload.get("alea") or payload
        r.indicateurs["argiles_rga"] = expo

    def set_mvt(items: list) -> None:
        r.indicateurs["mouvements_terrain_nb"] = len(items)
        r.items.extend({"categorie": "mouvement_terrain", **i} for i in items[:50])

    def set_cavites(items: list) -> None:
        r.indicateurs["cavites_nb"] = len(items)
        r.items.extend({"categorie": "cavite", **i} for i in items[:50])

    def set_azi(items: list) -> None:
        r.indicateurs["azi_nb"] = len(items)
        r.items.extend({"categorie": "azi", **i} for i in items[:20])

    def set_tri(items: list) -> None:
        r.indicateurs["tri_nb"] = len(items)
        r.items.extend({"categorie": "tri", **i} for i in items[:20])

    def set_ppr(items: list) -> None:
        # GASPAR renvoie toutes les procédures ; on isole les PPR naturels (PPRI, PPRN, PPRMT…)
        pprs = [i for i in items if str(i.get("libelle_risque_long", "")) or i.get("code_nat_pprn")]
        r.indicateurs["procedures_gaspar_nb"] = len(items)
        r.items.extend({"categorie": "procedure_gaspar", **i} for i in pprs[:50])

    def set_radon(items: list) -> None:
        if items:
            r.indicateurs["radon_potentiel"] = items[0].get("classe_potentiel", items[0])

    def set_sismique(items: list) -> None:
        if items:
            r.indicateurs["zonage_sismique"] = items[0].get("zone_sismicite", items[0])

    tasks = [
        collect(r, "Retrait-gonflement des argiles", gr.rga(lon, lat), set_rga),
        collect(r, "Mouvements de terrain", gr.mouvements_terrain(lon, lat, radius), set_mvt),
        collect(r, "Cavités souterraines", gr.cavites(lon, lat, radius), set_cavites),
    ]
    if code_insee:
        tasks += [
            collect(r, "Atlas des zones inondables", gr.azi(code_insee), set_azi),
            collect(r, "TRI inondation", gr.tri(code_insee), set_tri),
            collect(r, "Procédures PPR (GASPAR)", gr.risques_gaspar(code_insee), set_ppr),
            collect(r, "Potentiel radon", gr.radon(code_insee), set_radon),
            collect(r, "Zonage sismique", gr.zonage_sismique(code_insee), set_sismique),
        ]
    else:
        r.avertissements.append(
            "Commune du centre de zone non identifiée : données communales (AZI, TRI, PPR, radon, sismicité) non interrogées."
        )
    await asyncio.gather(*tasks)

    if zone.small_radius_m > config.GEORISQUES_MAX_RADIUS_M:
        r.avertissements.append(
            f"Zone plus large que le rayon maximal Géorisques ({config.GEORISQUES_MAX_RADIUS_M} m) : "
            "les recensements ponctuels sont limités à ce rayon autour du centre."
        )
    return r
