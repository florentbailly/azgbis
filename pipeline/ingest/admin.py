"""Contours administratifs France entière (communes + départements, etalab).

Support des choroplèthes par classes (radon…) : contrairement aux contours cadastraux
(`ingest contours`, départementaux et liés au DVF), cet import couvre toute la France
en une passe. Résolution 100 m : suffisante pour des cartes de classes (la maille
commune n'est affichée qu'à partir du zoom 9), et ~4× moins de RAM que le 50 m à
l'import — le VPS n'a que 4 Go.

URLs vérifiées le 20/07/2026 (HEAD 200) : millésime 2025, ~8 Mo (communes) et
~0,8 Mo (départements) compressés.
"""
import gzip
import json

from .common import db, download, register_source

MILLESIME = "2025"
BASE = f"http://etalab-datasets.geo.data.gouv.fr/contours-administratifs/{MILLESIME}/geojson"

INSERT = """
    INSERT INTO admin_contours (niveau, code, libelle, source_id, geom)
    VALUES (%s, %s, %s, %s,
            ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Force2D(
                ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 2154))), 3)))
    ON CONFLICT (niveau, code) DO NOTHING
"""


def _inserer(cur, niveau: str, source_id: int, path) -> int:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        features = json.load(f)["features"]
    rows = [
        (niveau, f["properties"]["code"], f["properties"]["nom"], source_id,
         json.dumps(f["geometry"]))
        for f in features
    ]
    del features
    # Par paquets : 35 000 communes en un executemany unique gonflerait la mémoire.
    for i in range(0, len(rows), 2000):
        cur.executemany(INSERT, rows[i:i + 2000])
    return len(rows)


def run() -> None:
    conn = db()
    source_id = register_source(
        conn, "admin", "Contours administratifs simplifiés (etalab)", BASE,
        millesime=MILLESIME,
    )
    with conn.cursor() as cur:
        cur.execute("DELETE FROM admin_contours")  # import remplaçant, une transaction
        for niveau, fichier in (("departement", "departements"), ("commune", "communes")):
            path = download(f"{BASE}/{fichier}-100m.geojson.gz", f"admin_{fichier}_{MILLESIME}.geojson.gz")
            n = _inserer(cur, niveau, source_id, path)
            print(f"  {niveau} : {n}")
    conn.commit()
    conn.close()
