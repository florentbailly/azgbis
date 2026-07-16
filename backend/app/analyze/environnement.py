"""Thème Environnement & biodiversité — table batch env_zonages (INPN, spec §3.3)."""
import json

from .. import db
from ..geo import Zone
from ..schemas import ThemeResult
from .common import source

FAMILLES = ["natura2000", "znieff1", "znieff2", "espace_protege", "patrimoine_geol"]


async def analyze(zone: Zone, code_insee: str | None) -> ThemeResult:
    r = ThemeResult(theme="environnement")
    p = await db.pool()
    if p is None:
        r.avertissements.append(db.NO_DB_WARNING)
        return r
    try:
        rows = await p.fetch(
            """
            SELECT z.famille, z.code_national, z.libelle, z.url_fiche_inpn,
                   ST_Area(ST_Intersection(z.geom, zone.g)) AS surface_intersect_m2,
                   s.millesime
            FROM env_zonages z
            JOIN sources s ON s.id = z.source_id
            CROSS JOIN (SELECT ST_Transform(ST_GeomFromGeoJSON($1), 2154) AS g) zone
            WHERE z.geom && zone.g AND ST_Intersects(z.geom, zone.g)
            ORDER BY surface_intersect_m2 DESC
            LIMIT 200
            """,
            json.dumps(zone.small_wgs84.__geo_interface__),
        )
    except Exception:
        r.avertissements.append(db.NO_DB_WARNING)
        return r

    if not rows:
        # Distinguer « aucun zonage sur la zone » (conclusion valable) de « source jamais
        # importée » (rien à conclure) — indispensable pour la piste d'audit.
        total = await p.fetchval("SELECT count(*) FROM env_zonages")
        if total == 0:
            r.avertissements.append(
                "Zonages INPN non importés en base : lancer `ingest inpn` (pipeline/README.md). "
                "Aucune conclusion environnementale possible."
            )
            return r

    for fam in FAMILLES:
        r.indicateurs[f"{fam}_nb"] = sum(1 for row in rows if row["famille"] == fam)
    r.items = [
        {
            "categorie": row["famille"],
            "code_national": row["code_national"],
            "libelle": row["libelle"],
            "surface_intersect_m2": round(row["surface_intersect_m2"] or 0),
            "url_fiche_inpn": row["url_fiche_inpn"],
        }
        for row in rows
    ]
    if rows:
        source(r, "inpn", "INPN (MNHN) — import batch", "https://inpn.mnhn.fr", rows[0]["millesime"])
    return r
