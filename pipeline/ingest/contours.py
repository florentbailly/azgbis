"""Contours cadastraux (etalab-cadastre) + agrégats prix/m² de la carte des prix.

La couche carte « Prix au m² (DVF) » colore un prix médian par maille — département,
commune, section cadastrale ou parcelle selon le zoom. Les contours viennent
d'etalab-cadastre (Licence Ouverte), dont les identifiants sont ceux du DVF
géolocalisé : `id_parcelle` (14 car. = commune+préfixe+section+numéro) se joint
directement, et ses 10 premiers caractères donnent l'id de section.

Seules les parcelles portant au moins une vente avec prix sont conservées
(~25 000 pour le Rhône, contre ~500 000 parcelles au total) : les fichiers
parcellaires se téléchargent donc commune par commune, jamais en bloc.
"""
import gzip
import json

import httpx

from .common import db, download, register_source

CADASTRE = "https://cadastre.data.gouv.fr/data/etalab-cadastre/latest/geojson"

INSERT = """
    INSERT INTO contours (niveau, code, libelle, source_id, geom)
    VALUES (%s, %s, %s, %s,
            ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Force2D(
                ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 2154))), 3)))
    ON CONFLICT (niveau, code) DO NOTHING
"""


def _features(path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)["features"]


def _insert(cur, niveau: str, source_id: int, rows: list[tuple[str, str | None, dict]]) -> None:
    cur.executemany(
        INSERT,
        [(niveau, code, libelle, source_id, json.dumps(geom)) for code, libelle, geom in rows],
    )


def run(dept: str) -> None:
    conn = db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT code_commune FROM dvf_mutations WHERE code_commune LIKE %s ORDER BY 1",
            (dept + "%",),
        )
        communes = [r[0] for r in cur.fetchall()]
        cur.execute(
            "SELECT DISTINCT id_parcelle FROM dvf_locaux "
            "WHERE prix_m2 IS NOT NULL AND id_parcelle LIKE %s",
            (dept + "%",),
        )
        parcelles_vendues = {r[0] for r in cur.fetchall()}
    if not communes:
        raise SystemExit(f"Aucune mutation DVF pour le département {dept} : lancer `ingest dvf` d'abord.")

    source_id = register_source(
        conn, "cadastre", f"Cadastre Etalab (contours) dépt {dept}",
        f"{CADASTRE}/departements/{dept}/", millesime="latest",
    )
    with conn.cursor() as cur:
        # Import remplaçant, comme les autres familles du pipeline.
        cur.execute(
            "DELETE FROM contours WHERE code LIKE %s OR (niveau = 'departement' AND code = %s)",
            (dept + "%", dept),
        )

        path = download(f"{CADASTRE}/departements/{dept}/cadastre-{dept}-communes.json.gz",
                        f"cadastre_{dept}_communes.json.gz")
        rows = [(f["properties"]["id"], f["properties"]["nom"], f["geometry"]) for f in _features(path)]
        _insert(cur, "commune", source_id, rows)
        print(f"  communes : {len(rows)}")

        # Sections : le fichier départemental est léger ; on ne garde que celles
        # portant au moins une parcelle vendue (les autres n'auront jamais de prix).
        sections_vendues = {p[:10] for p in parcelles_vendues}
        path = download(f"{CADASTRE}/departements/{dept}/cadastre-{dept}-sections.json.gz",
                        f"cadastre_{dept}_sections.json.gz")
        rows = [
            (f["properties"]["id"],
             f"Section {f['properties']['code']} — {f['properties']['commune']}",
             f["geometry"])
            for f in _features(path) if f["properties"]["id"] in sections_vendues
        ]
        _insert(cur, "section", source_id, rows)
        print(f"  sections avec ventes : {len(rows)}")

        nb_parcelles = 0
        for i, insee in enumerate(communes, 1):
            url = f"{CADASTRE}/communes/{dept}/{insee}/cadastre-{insee}-parcelles.json.gz"
            try:
                path = download(url, f"cadastre_{insee}_parcelles.json.gz")
            except httpx.HTTPStatusError as e:
                print(f"  {insee} : parcellaire indisponible ({e.response.status_code}) — commune ignorée")
                continue
            rows = [
                (f["properties"]["id"],
                 f"Parcelle {f['properties']['section']} {f['properties']['numero']} — {insee}",
                 f["geometry"])
                for f in _features(path) if f["properties"]["id"] in parcelles_vendues
            ]
            _insert(cur, "parcelle", source_id, rows)
            nb_parcelles += len(rows)
            if i % 25 == 0 or i == len(communes):
                print(f"  parcelles vendues : {nb_parcelles} ({i}/{len(communes)} communes)")

        # Contour départemental : union des communes, aucune source supplémentaire.
        cur.execute(
            """INSERT INTO contours (niveau, code, libelle, source_id, geom)
               SELECT 'departement', %s, 'Département ' || %s, %s,
                      ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Union(geom)), 3))
               FROM contours WHERE niveau = 'commune' AND code LIKE %s""",
            (dept, dept, source_id, dept + "%"),
        )
    conn.commit()
    refresh(conn)
    conn.close()


# Communes et département sont simplifiés à l'insertion (20 m / 100 m) : ces mailles ne
# servent qu'aux petits zooms de la carte, où le trait cadastral complet coûterait cher.
# percentile_cont(0.5) sur dvf_locaux.prix_m2 : la même définition du prix médian que
# le thème Marché de l'analyse (marche_ventes.py) — carte et rapport ne peuvent pas diverger.
_REFRESH = {
    "parcelle": """
        INSERT INTO dvf_prix (niveau, code, libelle, nb_ventes, prix_m2_median, geom)
        SELECT 'parcelle', c.code, c.libelle, count(*),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY l.prix_m2), c.geom
        FROM contours c JOIN dvf_locaux l ON l.id_parcelle = c.code
        WHERE c.niveau = 'parcelle' AND l.prix_m2 IS NOT NULL
        GROUP BY c.id""",
    "section": """
        INSERT INTO dvf_prix (niveau, code, libelle, nb_ventes, prix_m2_median, geom)
        SELECT 'section', c.code, c.libelle, count(*),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY l.prix_m2), c.geom
        FROM contours c JOIN dvf_locaux l ON left(l.id_parcelle, 10) = c.code
        WHERE c.niveau = 'section' AND l.prix_m2 IS NOT NULL
        GROUP BY c.id""",
    "commune": """
        INSERT INTO dvf_prix (niveau, code, libelle, nb_ventes, prix_m2_median, geom)
        SELECT 'commune', c.code, c.libelle, count(*),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY l.prix_m2),
               ST_Multi(ST_CollectionExtract(ST_MakeValid(
                   ST_SimplifyPreserveTopology(c.geom, 20)), 3))
        FROM contours c
        JOIN dvf_mutations m ON m.code_commune = c.code
        JOIN dvf_locaux l ON l.id_mutation = m.id_mutation
        WHERE c.niveau = 'commune' AND l.prix_m2 IS NOT NULL
        GROUP BY c.id""",
    "departement": """
        INSERT INTO dvf_prix (niveau, code, libelle, nb_ventes, prix_m2_median, geom)
        SELECT 'departement', c.code, c.libelle, count(*),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY l.prix_m2),
               ST_Multi(ST_CollectionExtract(ST_MakeValid(
                   ST_SimplifyPreserveTopology(c.geom, 100)), 3))
        FROM contours c
        JOIN dvf_mutations m
          ON c.code = CASE WHEN m.code_commune LIKE '97%' THEN left(m.code_commune, 3)
                           ELSE left(m.code_commune, 2) END
        JOIN dvf_locaux l ON l.id_mutation = m.id_mutation
        WHERE c.niveau = 'departement' AND l.prix_m2 IS NOT NULL
        GROUP BY c.id""",
}


def refresh(conn) -> None:
    """Recalcule dvf_prix sur toute la base ; appelé ici et en fin d'`ingest dvf`."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM contours")
        if cur.fetchone()[0] == 0:
            print("  dvf_prix : aucun contour importé, calcul sauté (lancer `ingest contours`)")
            return
        cur.execute("DELETE FROM dvf_prix")
        for niveau, sql in _REFRESH.items():
            cur.execute(sql)
            print(f"  dvf_prix {niveau} : {cur.rowcount} mailles")
    conn.commit()
