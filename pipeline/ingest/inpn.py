"""Import des zonages INPN (Natura 2000, ZNIEFF, espaces protégés, patrimoine géologique).

Les téléchargements INPN se font manuellement (les URLs de leurs archives changent) :
https://inpn.mnhn.fr → « Téléchargement des données de référence » → shapefile/GPKG métropole,
puis :  python -m ingest inpn --famille natura2000 --file raw/n2000.zip
Colonnes reconnues automatiquement : SITECODE/ID_MNHN (code), SITENAME/NOM (libellé).
"""
from pathlib import Path

import geopandas as gpd

from .common import db, register_source, sha256

CODE_FIELDS = ["SITECODE", "ID_MNHN", "ID_SPN", "CODE", "id_local"]
NAME_FIELDS = ["SITENAME", "NOM", "NOM_SITE", "LIB", "nom"]
FAMILLES = ["natura2000", "znieff1", "znieff2", "espace_protege", "patrimoine_geol"]


def _pick(row, fields):
    for f in fields:
        if f in row and row[f] is not None:
            return str(row[f])
    return None


def run(famille: str, file: str) -> None:
    if famille not in FAMILLES:
        raise SystemExit(f"famille inconnue : {famille} (attendu : {', '.join(FAMILLES)})")
    path = Path(file)
    gdf = gpd.read_file(path)
    gdf = gdf.to_crs(2154)
    # MultiPolygon homogène (le schéma l'exige)
    gdf["geometry"] = gdf.geometry.apply(
        lambda g: g if g.geom_type == "MultiPolygon" else __import__("shapely").geometry.MultiPolygon([g])
        if g.geom_type == "Polygon" else None
    )
    gdf = gdf.dropna(subset=["geometry"])

    conn = db()
    source_id = register_source(
        conn, f"inpn_{famille}", f"INPN — {famille}", "https://inpn.mnhn.fr",
        millesime=path.stem, checksum=sha256(path),
    )
    with conn.cursor() as cur:
        # Import remplaçant : on purge la famille avant recharge (spec §6).
        cur.execute("DELETE FROM env_zonages WHERE famille = %s", (famille,))
        for _, row in gdf.iterrows():
            code = _pick(row, CODE_FIELDS)
            cur.execute(
                """INSERT INTO env_zonages (famille, code_national, libelle, url_fiche_inpn, source_id, geom)
                   VALUES (%s, %s, %s, %s, %s, ST_GeomFromText(%s, 2154))""",
                (
                    famille, code, _pick(row, NAME_FIELDS),
                    f"https://inpn.mnhn.fr/site/natura2000/{code}" if famille == "natura2000" and code else None,
                    source_id, row.geometry.wkt,
                ),
            )
    conn.commit()
    conn.close()
    print(f"  {famille} : {len(gdf)} zonages importés depuis {path.name}")
