"""Orchestration d'une analyse de zone, partagée entre l'endpoint `/zones/analyze`
et le worker de rapports : le PDF exécute exactement le même code que l'écran,
condition de la piste d'audit (spec §8 ①)."""
import asyncio

from .analyze import environnement, marche_ventes, risques_naturels, risques_technologiques, urbanisme
from .clients import apicarto
from .clients.http import SourceError
from .geo import resolve_zone
from .schemas import AnalyzeRequest, AnalyzeResponse, ThemeResult

ANALYZERS = {
    "risques_naturels": risques_naturels.analyze,
    "risques_technologiques": risques_technologiques.analyze,
    "environnement": environnement.analyze,
    "urbanisme": urbanisme.analyze,
    "marche_ventes": marche_ventes.analyze,
}


async def run_analysis(req: AnalyzeRequest) -> AnalyzeResponse:
    zone = resolve_zone(req.zone)

    lon, lat = zone.centroid_lonlat
    code_insee: str | None = None
    commune_warning: str | None = None
    try:
        commune = await apicarto.commune_at(lon, lat)
        code_insee = commune["code"] if commune else None
    except SourceError as e:
        commune_warning = f"Identification de la commune impossible : {e}"

    results: list[ThemeResult] = list(
        await asyncio.gather(*(ANALYZERS[t](zone, code_insee) for t in req.themes))
    )
    if commune_warning:
        for r in results:
            r.avertissements.insert(0, commune_warning)
    return AnalyzeResponse(zone_resume=zone.resume | {"code_insee_centre": code_insee}, resultats=results)
