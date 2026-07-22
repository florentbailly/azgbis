"""Établissements SIRENE actifs géolocalisés (INSEE) → table `sirene_etablissements`.

Deux fichiers nationaux mensuels, résolus dynamiquement via l'API data.gouv (les URLs
datées changent chaque mois ; l'ancien miroir files.data.gouv.fr/geo-sirene est
décommissionné depuis avril 2026) :
  - StockEtablissement (parquet ~2,2 Go) : SIRET, code NAF, état administratif ;
  - Géolocalisation des établissements (parquet ~0,8 Go) : SIRET, x/y (Lambert-93 en
    métropole, EPSG local en outre-mer — colonne `epsg` respectée à l'insertion).

Lecture en flux par lots pyarrow (jamais tout en mémoire : compatible VPS 4 Go) ;
seuls les établissements ACTIFS des départements couverts par le DVF sont conservés.
"""
import json
import re

import httpx

from .common import db, download, register_source, ssl_context

API_DATAGOUV = "https://www.data.gouv.fr/api/1/datasets"
JEU_STOCK = "base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret"
JEU_GEOLOC = "geolocalisation-des-etablissements-du-repertoire-sirene-pour-les-etudes-statistiques"


def _resoudre(jeu: str, motif_titre: str) -> tuple[str, str]:
    """(url, millésime AAAA-MM) de la ressource parquet dont le titre matche."""
    with httpx.Client(verify=ssl_context(), timeout=60) as client:
        r = client.get(f"{API_DATAGOUV}/{jeu}/")
        r.raise_for_status()
    for res in json.loads(r.content)["resources"]:
        if res["format"] == "parquet" and re.search(motif_titre, res["title"]):
            m = re.search(r"/(\d{4})(\d{2})\d{2}-", res["url"])
            millesime = f"{m.group(1)}-{m.group(2)}" if m else "inconnu"
            return res["url"], millesime
    raise SystemExit(f"Ressource parquet « {motif_titre} » introuvable dans {jeu}.")


def _dept(commune: str) -> str:
    return commune[:3] if commune.startswith("97") else commune[:2]


def _etablissements_actifs(path, depts: set[str]) -> dict[str, tuple[str, str | None, str]]:
    """siret -> (naf, enseigne, dept) pour les établissements actifs des départements visés."""
    import pyarrow.dataset as ds

    colonnes = ["siret", "activitePrincipaleEtablissement", "etatAdministratifEtablissement",
                "codeCommuneEtablissement", "enseigne1Etablissement"]
    actifs: dict[str, tuple[str, str | None, str]] = {}
    lus = 0
    for lot in ds.dataset(path).scanner(columns=colonnes, batch_size=200_000).to_batches():
        d = lot.to_pydict()
        for siret, naf, etat, commune, enseigne in zip(
            d["siret"], d["activitePrincipaleEtablissement"], d["etatAdministratifEtablissement"],
            d["codeCommuneEtablissement"], d["enseigne1Etablissement"],
        ):
            if etat == "A" and commune and _dept(commune) in depts and naf:
                actifs[siret] = (naf, enseigne, _dept(commune))
        lus += lot.num_rows
        if lus % 4_000_000 < 200_000:
            print(f"  StockEtablissement : {lus} lignes lues, {len(actifs)} actifs retenus")
    return actifs


def run(depts_arg: list[str] | None) -> None:
    conn = db()
    if depts_arg:
        depts = set(depts_arg)
    else:
        with conn.cursor() as cur:
            cur.execute("""SELECT DISTINCT CASE WHEN code_commune LIKE '97%'
                               THEN left(code_commune, 3) ELSE left(code_commune, 2) END
                           FROM dvf_mutations""")
            depts = {r[0] for r in cur.fetchall()}
    if not depts:
        raise SystemExit("Aucun département DVF en base : lancer `ingest dvf` (ou --dept).")
    print(f"  départements visés : {', '.join(sorted(depts))}")

    url_stock, millesime = _resoudre(JEU_STOCK, r"StockEtablissement - ")
    url_geoloc, _ = _resoudre(JEU_GEOLOC, r"g[ée]olocalisation", )
    stock = download(url_stock, f"sirene_stock_{millesime}.parquet")
    geoloc = download(url_geoloc, f"sirene_geoloc_{millesime}.parquet")

    actifs = _etablissements_actifs(stock, depts)
    print(f"  établissements actifs retenus : {len(actifs)}")

    source_id = register_source(
        conn, "sirene", "Établissements SIRENE actifs géolocalisés (INSEE)",
        url_stock, millesime=millesime,
    )
    import pyarrow.dataset as ds

    with conn.cursor() as cur:
        cur.execute("""CREATE TEMP TABLE sirene_tmp (siret text, dept text, naf text,
                       enseigne text, x double precision, y double precision, epsg int)""")
        inseres = 0
        for lot in ds.dataset(geoloc).scanner(
            columns=["siret", "x", "y", "epsg"], batch_size=200_000
        ).to_batches():
            d = lot.to_pydict()
            lignes = []
            for siret, x, y, epsg in zip(d["siret"], d["x"], d["y"], d["epsg"]):
                infos = actifs.get(siret)
                if infos and x is not None and y is not None and epsg:
                    naf, enseigne, dept = infos
                    lignes.append((siret, dept, naf, enseigne, float(x), float(y), int(epsg)))
            if lignes:
                with cur.copy("COPY sirene_tmp FROM STDIN") as copy:
                    for ligne in lignes:
                        copy.write_row(ligne)
                inseres += len(lignes)
        print(f"  établissements géolocalisés : {inseres}")

        # Import remplaçant en une transaction, département par département.
        cur.execute("DELETE FROM sirene_etablissements WHERE dept = ANY(%s)", (sorted(depts),))
        cur.execute(
            """INSERT INTO sirene_etablissements (siret, dept, naf, enseigne, source_id, geom)
               SELECT DISTINCT ON (siret) siret, dept, naf, enseigne, %s,
                      ST_Transform(ST_SetSRID(ST_MakePoint(x, y), epsg), 2154)
               FROM sirene_tmp""",
            (source_id,),
        )
        print(f"  sirene_etablissements : {cur.rowcount} lignes (millésime {millesime})")
    conn.commit()
    conn.close()
