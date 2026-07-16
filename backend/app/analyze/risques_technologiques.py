"""Thème Risques technologiques — sources live Géorisques (spec §3.2)."""
import asyncio

from .. import config
from ..clients import georisques as gr
from ..geo import Zone
from ..schemas import ThemeResult
from .common import collect, source


def _is_seveso(icpe: dict) -> bool:
    statut = str(icpe.get("statutSeveso") or icpe.get("seveso") or "").lower()
    return "haut" in statut or "bas" in statut


async def analyze(zone: Zone, code_insee: str | None) -> ThemeResult:
    r = ThemeResult(theme="risques_technologiques")
    source(r, "georisques", "Géorisques (BRGM / MTE)", config.GEORISQUES_API)
    lon, lat = zone.centroid_lonlat
    radius = zone.small_radius_m

    def set_icpe(items: list) -> None:
        seveso = [i for i in items if _is_seveso(i)]
        r.indicateurs["icpe_nb"] = len(items)
        r.indicateurs["seveso_nb"] = len(seveso)
        r.items.extend({"categorie": "icpe", "seveso": _is_seveso(i), **i} for i in items[:100])

    def set_ssp(payload: dict) -> None:
        def block(key: str) -> tuple[int, list]:
            b = payload.get(key) or {}
            return int(b.get("results") or 0), b.get("data") or []

        casias_nb, casias_data = block("casias")
        sis_nb, sis_data = block("conclusions_sis")
        sup_nb, _ = block("conclusions_sup")
        r.indicateurs["sites_pollues_casias_nb"] = casias_nb
        r.indicateurs["sis_nb"] = sis_nb
        r.indicateurs["conclusions_sup_nb"] = sup_nb
        r.items.extend({"categorie": "sis", **i} for i in sis_data[:50])
        r.items.extend({"categorie": "casias", **i} for i in casias_data[:100])

    await asyncio.gather(
        collect(r, "Installations classées (ICPE)", gr.installations_classees(lon, lat, radius), set_icpe),
        collect(r, "Sites et sols pollués / SIS (SSP)", gr.ssp(lon, lat, radius), set_ssp),
    )
    return r
