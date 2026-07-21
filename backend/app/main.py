"""API de l'outil de qualification de zone — lot 1 (spec docs/specification-lot1.md §7)."""
import asyncio

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import catalog, config, db, dvf_export, tiles
from .analysis import run_analysis
from .clients import apicarto, http
from .clients.http import SourceError
from .reports import store as report_store
from .schemas import AnalyzeRequest, AnalyzeResponse, ExportRequest, ReportRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await http.close()
    await db.close()


app = FastAPI(title="Qualification de zone — lot 1", version=config.APP_VERSION, lifespan=lifespan)

# Outil interne sans authentification (décision lot 1) : CORS ouvert pour le dev.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(tiles.router)


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
    return await run_analysis(req)


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


@app.get("/api/sources")
async def sources_fraicheur() -> dict:
    """Fraîcheur des données importées : par code source, le millésime couvert (ou la
    plage de millésimes, ex. DVF multi-années) et la date du dernier import."""
    p = await db.pool()
    if p is None:
        return {"sources": [], "avertissements": [db.NO_DB_WARNING]}
    rows = await p.fetch(
        """SELECT code,
                  (array_agg(libelle ORDER BY date_import DESC))[1] AS libelle,
                  CASE WHEN min(millesime) = max(millesime) THEN max(millesime)
                       ELSE min(millesime) || ' – ' || max(millesime) END AS millesime,
                  max(date_import) AS date_import
           FROM sources GROUP BY code ORDER BY code"""
    )
    return {
        "sources": [
            {
                "code": r["code"],
                "libelle": r["libelle"],
                "millesime": r["millesime"],
                "date_import": r["date_import"].isoformat(),
            }
            for r in rows
        ],
        "avertissements": [],
    }


@app.get("/api/dvf/transactions")
async def dvf_transactions() -> dict:
    p = await db.pool()
    if p is None:
        return {"transactions": [], "avertissements": [db.NO_DB_WARNING]}
    raise HTTPException(501, "Filtres DVF : implémentation prévue après l'import du premier millésime (sprint 2).")


@app.post("/api/dvf/export.xlsx")
async def dvf_export_xlsx(req: ExportRequest) -> Response:
    """Excel des transactions DVF de la zone de contexte (même périmètre que l'analyse)."""
    contenu = await dvf_export.xlsx_transactions(req.zone)
    if contenu is None:
        raise HTTPException(503, db.NO_DB_WARNING)
    return Response(
        contenu,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="transactions-dvf.xlsx"'},
    )


# --- Rapports PDF (spec §8) : l'API dépose le job, le worker dédié le consomme. -----

@app.post("/api/reports", status_code=202)
async def create_report(req: ReportRequest) -> dict:
    if not req.themes:
        raise HTTPException(400, "Aucun thème demandé.")
    p = await db.pool()
    if p is None:
        raise HTTPException(503, "Rapports indisponibles : " + db.NO_DB_WARNING)
    job_id = await report_store.creer(p, req)
    return {"job_id": job_id}


@app.get("/api/reports/{job_id}")
async def report_status(job_id: str) -> dict:
    p = await db.pool()
    if p is None:
        raise HTTPException(503, db.NO_DB_WARNING)
    job = await report_store.lire(p, job_id)
    if job is None:
        raise HTTPException(404, "Rapport inconnu (les rapports sont purgés après 24 h).")
    out = {"status": job["statut"]}
    if job["statut"] == "done":
        out["download_url"] = f"/api/reports/{job_id}/download"
    if job["statut"] == "error":
        out["erreur"] = job["erreur"]
    return out


@app.get("/api/reports/{job_id}/download")
async def report_download(job_id: str) -> FileResponse:
    p = await db.pool()
    if p is None:
        raise HTTPException(503, db.NO_DB_WARNING)
    job = await report_store.lire(p, job_id)
    if job is None or job["statut"] != "done" or not job["fichier"]:
        raise HTTPException(404, "Rapport indisponible (non terminé, en erreur, ou purgé après 24 h).")
    path = report_store.chemin_pdf(job["fichier"])
    if not path.exists():
        raise HTTPException(404, "Fichier purgé (les rapports sont conservés 24 h).")
    return FileResponse(path, media_type="application/pdf", filename=job["fichier"])
