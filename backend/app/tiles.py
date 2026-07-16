"""Tuiles vectorielles des zonages batch, servies depuis PostGIS (ST_AsMVT).

La spec §3.3 prévoyait des PMTiles produites par tippecanoe. Les zonages INPN (21 000
polygones, indexés en GIST) se servent directement depuis la base : mêmes données que
l'analyse — donc jamais de décalage entre ce que l'expert voit et ce que le rapport
conclut — sans build tippecanoe ni étape de régénération après chaque import.
Les PMTiles restent pertinentes pour les gros volumes statiques (cadastre, DVF).
"""
from fastapi import APIRouter, HTTPException, Response

from . import db
from .analyze.environnement import FAMILLES

router = APIRouter()

MVT_LAYER = "zonages"  # nom de la couche dans la tuile = `source-layer` côté front

# Surface minimale d'affichage, en multiples de la surface d'un pixel : un zonage
# occupant moins de 2×2 pixels n'est qu'un point à l'écran. À l'échelle France (z5) ce
# seuil vaut ~55 km² et ne laisse que les grands massifs — vue lisible et tuile légère ;
# à l'échelle de travail (z14) il tombe à ~23 m² et ne masque plus rien.
SEUIL_PIXELS2 = 4.0

# ST_TileEnvelope donne l'emprise 3857 ; le filtre porte sur la géométrie 2154 native
# (via l'index GIST) et non sur ST_Transform(geom), qui interdirait son usage.
# Simplification à la résolution de la tuile (un côté / 4096 = une cellule de la grille
# MVT) : invisible à l'écran, mais ramène une tuile France entière de 2 Mo à ~150 ko.
# L'analyse et le rapport lisent la géométrie non simplifiée, jamais ces tuiles.
SQL = f"""
WITH b AS (
    SELECT ST_TileEnvelope($1, $2, $3) AS g3857,
           ST_Transform(ST_TileEnvelope($1, $2, $3), 2154) AS g2154
),
p AS (
    SELECT (ST_XMax(b.g2154) - ST_XMin(b.g2154)) / 4096 AS tol,
           (ST_XMax(b.g2154) - ST_XMin(b.g2154)) / 256 AS pixel
    FROM b
),
src AS (
    -- En dessous de z10, la géométrie généralisée (~50 m, calculée à l'import) suffit :
    -- l'écart reste sous le pixel et évite de relire les contours ZNIEFF pleine résolution.
    SELECT z.famille, z.code_national, z.libelle, z.url_fiche_inpn,
           CASE WHEN $1 <= 9 THEN COALESCE(z.geom_gen, z.geom) ELSE z.geom END AS g
    FROM env_zonages z, b, p
    WHERE z.famille = ANY($4::text[]) AND z.geom && b.g2154
      -- Filtre de lisibilité (voir SEUIL_PIXELS2) appliqué sur la surface précalculée,
      -- donc avant tout traitement géométrique.
      AND COALESCE(z.surface_m2, ST_Area(z.geom)) >= p.pixel * p.pixel * {SEUIL_PIXELS2}
)
SELECT ST_AsMVT(q, '{MVT_LAYER}', 4096, 'geom') FROM (
    SELECT src.famille, src.code_national, src.libelle, src.url_fiche_inpn,
           ST_AsMVTGeom(
               ST_Transform(ST_SimplifyPreserveTopology(src.g, p.tol), 3857),
               b.g3857, 4096, 64, true) AS geom
    FROM src, b, p
) q
WHERE q.geom IS NOT NULL
"""


@router.get("/api/tiles/env/{familles}/{z}/{x}/{y}.pbf")
async def env_tile(familles: str, z: int, x: int, y: int) -> Response:
    demandees = familles.split(",")
    inconnues = set(demandees) - set(FAMILLES)
    if inconnues:
        raise HTTPException(404, f"Famille(s) inconnue(s) : {', '.join(sorted(inconnues))}")
    _check_zxy(z, x, y)
    p = await db.pool()
    if p is None:
        raise HTTPException(503, db.NO_DB_WARNING)
    return _mvt_response(await p.fetchval(SQL, z, x, y, demandees))


# --- Carte des prix DVF -------------------------------------------------------------
# Une maille par niveau de zoom : le prix médian au m² est précalculé dans dvf_prix
# par `ingest contours` (mêmes médianes que le thème Marché de l'analyse).
MVT_PRIX_LAYER = "prix"


def _niveau(z: int) -> str:
    if z <= 8:
        return "departement"
    if z <= 11:
        return "commune"
    if z <= 13:
        return "section"
    return "parcelle"  # au-delà de z14, MapLibre ré-agrandit les tuiles z14


SQL_PRIX = f"""
WITH b AS (
    SELECT ST_TileEnvelope($1, $2, $3) AS g3857,
           ST_Transform(ST_TileEnvelope($1, $2, $3), 2154) AS g2154
),
p AS (
    SELECT (ST_XMax(b.g2154) - ST_XMin(b.g2154)) / 4096 AS tol FROM b
)
SELECT ST_AsMVT(q, '{MVT_PRIX_LAYER}', 4096, 'geom') FROM (
    SELECT d.niveau, d.code, d.libelle, d.nb_ventes,
           round(d.prix_m2_median)::int AS prix_m2,
           ST_AsMVTGeom(
               ST_Transform(ST_SimplifyPreserveTopology(d.geom, p.tol), 3857),
               b.g3857, 4096, 64, true) AS geom
    FROM dvf_prix d, b, p
    WHERE d.niveau = $4 AND d.geom && b.g2154
) q
WHERE q.geom IS NOT NULL
"""


@router.get("/api/tiles/dvf/{z}/{x}/{y}.pbf")
async def dvf_tile(z: int, x: int, y: int) -> Response:
    _check_zxy(z, x, y)
    p = await db.pool()
    if p is None:
        raise HTTPException(503, db.NO_DB_WARNING)
    return _mvt_response(await p.fetchval(SQL_PRIX, z, x, y, _niveau(z)))


def _check_zxy(z: int, x: int, y: int) -> None:
    if not 0 <= z <= 22 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise HTTPException(400, "Coordonnées de tuile hors limites.")


def _mvt_response(mvt) -> Response:
    # Une tuile vide est un résultat normal (pas de donnée ici) : 204 plutôt que 404,
    # sinon MapLibre journalise une erreur sur chaque tuile sans donnée.
    if not mvt:
        return Response(status_code=204)
    return Response(
        bytes(mvt),
        media_type="application/vnd.mapbox-vector-tile",
        headers={"Cache-Control": "public, max-age=86400"},
    )
