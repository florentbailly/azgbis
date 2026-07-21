"""Tuiles vectorielles des zonages batch, servies depuis PostGIS (ST_AsMVT).

La spec §3.3 prévoyait des PMTiles produites par tippecanoe. Les zonages INPN (21 000
polygones, indexés en GIST) se servent directement depuis la base : mêmes données que
l'analyse — donc jamais de décalage entre ce que l'expert voit et ce que le rapport
conclut — sans build tippecanoe ni étape de régénération après chaque import.
Les PMTiles restent pertinentes pour les gros volumes statiques (cadastre, DVF).
"""
import datetime

from fastapi import APIRouter, HTTPException, Query, Response

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


# Variante filtrée par période de mutation (`?debut=…&fin=…`) : dvf_prix agrège toute
# la base, il faut donc recalculer les médianes à la volée sur les ventes de la période.
# Mêmes jointures que le précalcul (ingest contours), mais restreintes aux contours
# intersectant la tuile — les index (GIST sur contours, id_parcelle/date sur DVF)
# gardent la latence sous celle d'un aller-retour réseau, sauf tuiles départementales.
_JOINTURES_PERIODE = {
    "parcelle": """JOIN dvf_locaux l ON l.id_parcelle = c.code
                   JOIN dvf_mutations m ON m.id_mutation = l.id_mutation""",
    "section": """JOIN dvf_locaux l ON left(l.id_parcelle, 10) = c.code
                  JOIN dvf_mutations m ON m.id_mutation = l.id_mutation""",
    "commune": """JOIN dvf_mutations m ON m.code_commune = c.code
                  JOIN dvf_locaux l ON l.id_mutation = m.id_mutation""",
    "departement": """JOIN dvf_mutations m
                        ON c.code = CASE WHEN m.code_commune LIKE '97%' THEN left(m.code_commune, 3)
                                         ELSE left(m.code_commune, 2) END
                      JOIN dvf_locaux l ON l.id_mutation = m.id_mutation""",
}

SQL_PRIX_PERIODE = {
    niveau: f"""
WITH b AS (
    SELECT ST_TileEnvelope($1, $2, $3) AS g3857,
           ST_Transform(ST_TileEnvelope($1, $2, $3), 2154) AS g2154
),
p AS (
    SELECT (ST_XMax(b.g2154) - ST_XMin(b.g2154)) / 4096 AS tol FROM b
),
agg AS (
    SELECT c.code, c.libelle, c.geom, count(*) AS nb_ventes,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY l.prix_m2) AS prix_m2_median
    FROM contours c
    {jointure}, b
    WHERE c.niveau = $4 AND c.geom && b.g2154
      AND l.prix_m2 IS NOT NULL
      AND m.date_mutation BETWEEN $5 AND $6
    GROUP BY c.id
)
SELECT ST_AsMVT(q, '{MVT_PRIX_LAYER}', 4096, 'geom') FROM (
    SELECT $4::text AS niveau, agg.code, agg.libelle, agg.nb_ventes,
           round(agg.prix_m2_median)::int AS prix_m2,
           ST_AsMVTGeom(
               ST_Transform(ST_SimplifyPreserveTopology(agg.geom, p.tol), 3857),
               b.g3857, 4096, 64, true) AS geom
    FROM agg, b, p
) q
WHERE q.geom IS NOT NULL
"""
    for niveau, jointure in _JOINTURES_PERIODE.items()
}


@router.get("/api/tiles/dvf/{z}/{x}/{y}.pbf")
async def dvf_tile(
    z: int, x: int, y: int,
    debut: datetime.date | None = Query(None),
    fin: datetime.date | None = Query(None),
) -> Response:
    _check_zxy(z, x, y)
    p = await db.pool()
    if p is None:
        raise HTTPException(503, db.NO_DB_WARNING)
    niveau = _niveau(z)
    if debut is not None and fin is not None:
        if fin < debut:
            raise HTTPException(400, "Période invalide : fin antérieure au début.")
        mvt = await p.fetchval(SQL_PRIX_PERIODE[niveau], z, x, y, niveau, debut, fin)
    else:
        mvt = await p.fetchval(SQL_PRIX, z, x, y, niveau)
    return _mvt_response(mvt)


@router.get("/api/dvf/periode")
async def dvf_periode() -> dict:
    """Bornes temporelles des mutations importées — alimente le curseur de période."""
    p = await db.pool()
    if p is None:
        return {"min": None, "max": None}
    row = await p.fetchrow("SELECT min(date_mutation) AS mini, max(date_mutation) AS maxi FROM dvf_mutations")
    return {
        "min": row["mini"].isoformat() if row["mini"] else None,
        "max": row["maxi"].isoformat() if row["maxi"] else None,
    }


# --- Choroplèthes par classes (générique) --------------------------------------------
# Une couche = un jeu de mailles précalculées dans carto_classes par son ingest
# (ex. radon : classe 1-3 par commune, classe majoritaire par département).
MVT_CLASSES_LAYER = "classes"

# Par couche : zoom au-delà duquel on passe de la maille département à la commune.
CLASSES_COUCHES = {"radon": 8}

SQL_CLASSES = f"""
WITH b AS (
    SELECT ST_TileEnvelope($1, $2, $3) AS g3857,
           ST_Transform(ST_TileEnvelope($1, $2, $3), 2154) AS g2154
),
p AS (
    SELECT (ST_XMax(b.g2154) - ST_XMin(b.g2154)) / 4096 AS tol FROM b
)
SELECT ST_AsMVT(q, '{MVT_CLASSES_LAYER}', 4096, 'geom') FROM (
    SELECT c.niveau, c.code, c.libelle, c.classe,
           ST_AsMVTGeom(
               ST_Transform(ST_SimplifyPreserveTopology(c.geom, p.tol), 3857),
               b.g3857, 4096, 64, true) AS geom
    FROM carto_classes c, b, p
    WHERE c.couche = $4 AND c.niveau = $5 AND c.geom && b.g2154
) q
WHERE q.geom IS NOT NULL
"""


@router.get("/api/tiles/classes/{couche}/{z}/{x}/{y}.pbf")
async def classes_tile(couche: str, z: int, x: int, y: int) -> Response:
    if couche not in CLASSES_COUCHES:
        raise HTTPException(404, f"Couche par classes inconnue : {couche}")
    _check_zxy(z, x, y)
    p = await db.pool()
    if p is None:
        raise HTTPException(503, db.NO_DB_WARNING)
    niveau = "departement" if z <= CLASSES_COUCHES[couche] else "commune"
    return _mvt_response(await p.fetchval(SQL_CLASSES, z, x, y, couche, niveau))


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
