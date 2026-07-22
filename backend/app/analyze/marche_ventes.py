"""Thème Marché — transactions DVF enrichies (batch, spec §3.5 et §5).

Les comparables sont cherchés dans la zone de CONTEXTE (grand rayon), conformément à la spec §4.
"""
import json

from .. import db
from ..geo import Zone
from ..schemas import ThemeResult
from .common import source


async def analyze(zone: Zone, code_insee: str | None) -> ThemeResult:
    r = ThemeResult(theme="marche_ventes")
    p = await db.pool()
    if p is None:
        r.avertissements.append(db.NO_DB_WARNING)
        return r
    zone_json = json.dumps(zone.large_wgs84.__geo_interface__)
    try:
        stats = await p.fetch(
            """
            SELECT l.typologie,
                   count(*) AS nb,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY l.prix_m2) AS prix_m2_median,
                   min(m.date_mutation) AS premiere, max(m.date_mutation) AS derniere
            FROM dvf_locaux l
            JOIN dvf_mutations m ON m.id_mutation = l.id_mutation
            WHERE ST_Intersects(m.geom, ST_Transform(ST_GeomFromGeoJSON($1), 2154))
              AND l.prix_m2 IS NOT NULL
            GROUP BY l.typologie ORDER BY nb DESC
            """,
            zone_json,
        )
        recentes = await p.fetch(
            """
            SELECT m.id_mutation, m.date_mutation, m.nature_mutation, m.valeur_fonciere,
                   l.typologie, l.typologie_confiance, l.surface_reelle_bati, l.prix_m2, l.dpe_classe
            FROM dvf_locaux l
            JOIN dvf_mutations m ON m.id_mutation = l.id_mutation
            WHERE ST_Intersects(m.geom, ST_Transform(ST_GeomFromGeoJSON($1), 2154))
            ORDER BY m.date_mutation DESC
            LIMIT 200
            """,
            zone_json,
        )
    except Exception:
        r.avertissements.append(db.NO_DB_WARNING)
        return r

    r.indicateurs["par_typologie"] = [
        {
            "typologie": row["typologie"],
            "nb_transactions": row["nb"],
            "prix_m2_median": round(row["prix_m2_median"]) if row["prix_m2_median"] else None,
            "periode": [str(row["premiere"]), str(row["derniere"])],
        }
        for row in stats
    ]
    r.indicateurs["nb_transactions_zone_contexte"] = sum(row["nb"] for row in stats)
    r.items = [dict(row) | {"categorie": "transaction"} for row in recentes]
    source(r, "dvf", "DVF géolocalisé (Etalab), typologie enrichie BD TOPO/SIRENE", "https://files.data.gouv.fr/geo-dvf/")
    return r
