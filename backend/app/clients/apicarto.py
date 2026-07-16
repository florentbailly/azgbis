"""Client API Carto (IGN) : modules GPU et cadastre."""
from .. import config
from .http import get_json


async def gpu_zone_urba(geom_geojson: str) -> dict:
    return await get_json(f"{config.APICARTO_API}/gpu/zone-urba", {"geom": geom_geojson})  # type: ignore[return-value]


async def gpu_prescriptions_surf(geom_geojson: str) -> dict:
    return await get_json(f"{config.APICARTO_API}/gpu/prescription-surf", {"geom": geom_geojson})  # type: ignore[return-value]


async def gpu_servitudes_surf(geom_geojson: str) -> dict:
    return await get_json(f"{config.APICARTO_API}/gpu/assiette-sup-s", {"geom": geom_geojson})  # type: ignore[return-value]


async def gpu_municipality(code_insee: str) -> dict:
    """Statut de la commune au GPU (RNU, document en vigueur...)."""
    return await get_json(f"{config.APICARTO_API}/gpu/municipality", {"insee": code_insee})  # type: ignore[return-value]


async def cadastre_parcelle_at(lon: float, lat: float) -> dict:
    # L'intersection ponctuelle renvoie 0 résultat en zone urbaine, et l'API arrondit les
    # géométries : en dessous de 0.0001° de demi-côté, 0 résultat (constaté le 16/07/2026).
    # On interroge donc avec un carré d'environ 20 m, l'appelant garde la parcelle contenant le point.
    d = 0.0001
    ring = f"[[{lon-d},{lat-d}],[{lon+d},{lat-d}],[{lon+d},{lat+d}],[{lon-d},{lat+d}],[{lon-d},{lat-d}]]"
    geom = f'{{"type":"Polygon","coordinates":[{ring}]}}'
    return await get_json(f"{config.APICARTO_API}/cadastre/parcelle", {"geom": geom})  # type: ignore[return-value]


async def commune_at(lon: float, lat: float) -> dict | None:
    """Commune au point (geo.api.gouv.fr)."""
    payload = await get_json(
        f"{config.GEO_API}/communes", {"lat": lat, "lon": lon, "fields": "code,nom,codeEpci"}
    )
    return payload[0] if isinstance(payload, list) and payload else None
