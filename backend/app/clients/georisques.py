"""Client API Géorisques v1.

Les chemins d'endpoints sont centralisés ici : c'est la tâche T-01 de la spec
(les figer contre la doc officielle georisques.gouv.fr/doc-api en début de sprint).
Tout échec lève SourceError, converti en avertissement par la couche analyze.
"""
from .. import config
from .http import get_json


def _latlon(lon: float, lat: float) -> str:
    return f"{lon},{lat}"


def _rayon(radius_m: float) -> int:
    return int(min(radius_m, config.GEORISQUES_MAX_RADIUS_M))


async def _paged(path: str, params: dict, max_items: int = 200) -> list[dict]:
    """Endpoints paginés Géorisques ({data: [...], next: url})."""
    out: list[dict] = []
    params = {**params, "page": 1, "page_size": 100}
    while len(out) < max_items:
        payload = await get_json(f"{config.GEORISQUES_API}{path}", params)
        data = payload.get("data", []) if isinstance(payload, dict) else payload
        out.extend(data)
        if not isinstance(payload, dict) or not payload.get("next") or not data:
            break
        params["page"] += 1
    return out[:max_items]


# --- Risques naturels ---------------------------------------------------------

async def rga(lon: float, lat: float) -> dict:
    """Exposition retrait-gonflement des argiles au point."""
    payload = await get_json(f"{config.GEORISQUES_API}/rga", {"latlon": _latlon(lon, lat)})
    return payload if isinstance(payload, dict) else {"data": payload}


async def mouvements_terrain(lon: float, lat: float, radius_m: float) -> list[dict]:
    return await _paged("/mvt", {"latlon": _latlon(lon, lat), "rayon": _rayon(radius_m)})


async def cavites(lon: float, lat: float, radius_m: float) -> list[dict]:
    return await _paged("/cavites", {"latlon": _latlon(lon, lat), "rayon": _rayon(radius_m)})


async def azi(code_insee: str) -> list[dict]:
    """Atlas des zones inondables de la commune."""
    return await _paged("/gaspar/azi", {"code_insee": code_insee})


async def tri(code_insee: str) -> list[dict]:
    """Territoires à risque important d'inondation."""
    return await _paged("/gaspar/tri", {"code_insee": code_insee})


async def risques_gaspar(code_insee: str) -> list[dict]:
    """Procédures GASPAR de la commune (PPRI, PPRN, PPRMT, PPRT...)."""
    return await _paged("/gaspar/risques", {"code_insee": code_insee})


async def radon(code_insee: str) -> list[dict]:
    return await _paged("/radon", {"code_insee": code_insee})


async def zonage_sismique(code_insee: str) -> list[dict]:
    return await _paged("/zonage_sismique", {"code_insee": code_insee})


# --- Risques technologiques ---------------------------------------------------

async def installations_classees(lon: float, lat: float, radius_m: float) -> list[dict]:
    return await _paged(
        "/installations_classees", {"latlon": _latlon(lon, lat), "rayon": _rayon(radius_m)}
    )


async def ssp(lon: float, lat: float, radius_m: float) -> dict:
    """Sites et sols pollués — composite vérifié le 15/07/2026 :
    /v1/ssp renvoie {casias, instructions, conclusions_sis, conclusions_sup},
    chacun au format paginé {results, data}. (Pas d'endpoint /sis ni /casias séparés en v1 ;
    /ssp/casias existe aussi. Canalisations de matières dangereuses : absent de l'API v1 → T-01.)
    """
    payload = await get_json(
        f"{config.GEORISQUES_API}/ssp",
        {"latlon": _latlon(lon, lat), "rayon": _rayon(radius_m), "page": 1, "page_size": 100},
    )
    return payload if isinstance(payload, dict) else {}
