"""API de l'outil de qualification de zone — lot 1 (spec docs/specification-lot1.md §7)."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import catalog, config, db
from .analyze import environnement, marche_ventes, risques_naturels, risques_technologiques, urbanisme
from .clients import apicarto, http
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await http.close()
    await db.close()


app = FastAPI(title="Qualification de zone — lot 1", version=config.APP_VERSION, lifespan=lifespan)

# Outil interne sans authentification (décision lot 1) : CORS ouvert pour le dev.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": config.APP_VERSION}


@app.get("/api/layers")
async def layers() -> dict:
    return {"themes": catalog.THEMES, "layers": catalog.LAYERS}


@app.post("/api/zones/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    if not req.themes:
        raise HTTPException(400, "Aucun thème demandé.")
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


@app.get("/api/parcelles/lookup")
async def parcelle_lookup(lon: float = Query(...), lat: float = Query(...)) -> dict:
    """Fiche parcelle : cadastre + zonage PLU + statut GPU en un appel (spec §7)."""
    out: dict = {"avertissements": []}

    async def safe(label: str, coro):
        try:
            return await coro
        except SourceError as e:
            out["avertissements"].append(f"{label} : {e}")
            return None

    point_geom = f'{{"type":"Point","coordinates":[{lon},{lat}]}}'
    parcelle, zonage, commune = await asyncio.gather(
        safe("cadastre", apicarto.cadastre_parcelle_at(lon, lat)),
        safe("zonage PLU", apicarto.gpu_zone_urba(point_geom)),
        safe("commune", apicarto.commune_at(lon, lat)),
    )
    feats = (parcelle or {}).get("features", [])
    # La requête cadastre porte sur une petite emprise : on retient la parcelle
    # qui contient effectivement le point cliqué, sinon la première.
    best = None
    if feats:
        from shapely.geometry import Point, shape

        pt = Point(lon, lat)
        for f in feats:
            try:
                if shape(f["geometry"]).contains(pt):
                    best = f
                    break
            except Exception:
                continue
        best = best or feats[0]
    out["parcelle"] = best
    out["zones_plu"] = [f.get("properties", {}) for f in (zonage or {}).get("features", [])]
    out["commune"] = commune
    if commune:
        muni = await safe("statut GPU", apicarto.gpu_municipality(commune["code"]))
        munifeats = (muni or {}).get("features", [])
        out["statut_gpu"] = munifeats[0].get("properties") if munifeats else muni
    return out


@app.get("/api/dvf/transactions")
async def dvf_transactions() -> dict:
    p = await db.pool()
    if p is None:
        return {"transactions": [], "avertissements": [db.NO_DB_WARNING]}
    raise HTTPException(501, "Filtres DVF : implémentation prévue après l'import du premier millésime (sprint 2).")


@app.post("/api/reports", status_code=501)
async def create_report() -> dict:
    raise HTTPException(
        501,
        "Génération de rapport : sprint 3 du lot 1 (worker Playwright + WeasyPrint, spec §8). "
        "Utiliser /api/zones/analyze en attendant.",
    )
