"""Bâtiments BD TOPO (IGN, Géoplateforme) → table `bati`, par département.

Se substitue à la BDNB prévue par la spec §5 : depuis 2026 la BDNB n'est distribuée
qu'en export France entière (~39 Go) ou via une API à clé (constat du 22/07/2026).
La BD TOPO (Licence Ouverte) fournit, par département et par trimestre, l'usage de
chaque bâtiment (`usage_1`/`usage_2` : Résidentiel, Commercial et services,
Industriel, Agricole…) — le nécessaire pour la chaîne `ingest enrich`.

Le dernier millésime TOUSTHEMES GPKG du département est résolu via le flux Atom de
la Géoplateforme, téléchargé (7z ~0,5-1 Go), extrait dans pipeline/raw/, puis la
couche `batiment` est lue par lots (pyogrio) et copiée en base.

Sobriété disque (VPS 40 Go tout compris) : seuls les bâtiments « En service »
INTERSECTANT UNE PARCELLE VENDUE (`ingest contours`, prérequis) sont conservés —
les seuls que `ingest enrich` consulte. Division par ~20 du stockage (Rhône :
~45 000 bâtiments au lieu de 910 000). Archive 7z et gpkg extraits sont supprimés
après import (retéléchargés au millésime suivant) ; relancer `bati` après un
`contours` qui ajoute des parcelles.
"""
import re
import xml.etree.ElementTree as ET

import httpx

from .common import RAW_DIR, db, download, register_source, ssl_context

FLUX = "https://data.geopf.fr/telechargement/resource/BDTOPO"
TELECHARGEMENT = "https://data.geopf.fr/telechargement/download/BDTOPO"
ATOM = "{http://www.w3.org/2005/Atom}"
LOT = 100_000

COLONNES = ["cleabs", "nature", "usage_1", "usage_2", "construction_legere", "nombre_de_logements"]


def _derniere_archive(dept: str) -> str:
    """Nom de la dernière archive TOUSTHEMES GPKG du département (flux Atom paginé)."""
    zone = f"D{dept:0>3}"  # 69 -> D069, 2A -> D02A
    motif = re.compile(rf"^BDTOPO_[\d-]+_TOUSTHEMES_GPKG_LAMB93_{zone}_\d{{4}}-\d{{2}}-\d{{2}}$")
    titres: list[str] = []
    with httpx.Client(verify=ssl_context(), timeout=60) as client:
        for page in range(1, 20):
            r = client.get(FLUX, params={"zone": zone, "pagesize": "50", "page": str(page)})
            r.raise_for_status()
            entrees = ET.fromstring(r.content).findall(f"{ATOM}entry/{ATOM}title")
            if not entrees:
                break
            titres += [e.text for e in entrees if e.text and motif.match(e.text)]
    if not titres:
        raise SystemExit(f"Aucune archive BD TOPO TOUSTHEMES GPKG trouvée pour {zone}.")
    return max(titres, key=lambda t: t.rsplit("_", 1)[1])  # la date clôt le nom


def _extraire_gpkg(archive) -> str:
    """Extrait le seul .gpkg de l'archive 7z dans pipeline/raw/ (idempotent).

    La taille attendue est vérifiée : une extraction interrompue (disque plein…)
    laisse un fichier partiel qu'il faut ré-extraire, pas réutiliser.
    """
    import py7zr

    with py7zr.SevenZipFile(archive) as z:
        entrees = [e for e in z.list() if e.filename.lower().endswith(".gpkg")]
        if len(entrees) != 1:
            raise SystemExit(f"Archive inattendue : {len(entrees)} fichiers .gpkg ({archive})")
        entree = entrees[0]
        dest = RAW_DIR / entree.filename
        if not dest.exists() or dest.stat().st_size != entree.uncompressed:
            if dest.exists():
                print(f"  extraction incomplète détectée ({dest.stat().st_size}/{entree.uncompressed} octets) : reprise")
                dest.unlink()
            print(f"  extraction {entree.filename}")
            z.extract(path=RAW_DIR, targets=[entree.filename])
    return str(dest)


# Bâtiment retenu : intersecte une parcelle vendue du département (l'index GIST de
# contours sert de filtre). Appliqué par lot pour ne jamais matérialiser les ~900 000
# bâtiments d'un département — seuls les quelques milliers utiles atterrissent dans bati.
SQL_FILTRE_LOT = """
    INSERT INTO bati (id_bdtopo, dept, usage_1, usage_2, nature,
                      nb_logements, legere, source_id, geom)
    SELECT t.id_bdtopo, %s, t.usage_1, t.usage_2, t.nature,
           t.nb_logements, t.legere, %s, t.g
    FROM (SELECT *, ST_Multi(ST_CollectionExtract(ST_MakeValid(
                      ST_Force2D(ST_GeomFromWKB(wkb, 2154))), 3)) AS g
          FROM bati_tmp) t
    WHERE EXISTS (SELECT 1 FROM contours c
                  WHERE c.niveau = 'parcelle' AND c.code LIKE %s
                    AND c.geom && t.g AND ST_Intersects(c.geom, t.g))
    ON CONFLICT (id_bdtopo) DO NOTHING
"""


def run(dept: str) -> None:
    import pyogrio
    import shutil
    from pathlib import Path

    conn = db()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM contours WHERE niveau = 'parcelle' AND code LIKE %s",
                    (dept + "%",))
        if cur.fetchone()[0] == 0:
            raise SystemExit(f"Aucune parcelle vendue en base pour le département {dept} : "
                             "lancer `ingest contours` d'abord.")

    nom = _derniere_archive(dept)
    millesime = nom.rsplit("_", 1)[1]
    archive = download(f"{TELECHARGEMENT}/{nom}/{nom}.7z", f"{nom}.7z")
    gpkg = _extraire_gpkg(archive)
    # L'archive ne sert plus une fois le gpkg extrait : la supprimer avant la phase base
    # libère ~0,7 Go pendant la partie la plus gourmande (déterminant sur un VPS de 40 Go).
    Path(archive).unlink(missing_ok=True)

    try:
        info = pyogrio.read_info(gpkg, layer="batiment")
        manquantes = [c for c in COLONNES if c not in info["fields"]]
        if manquantes:
            raise SystemExit(f"Colonnes absentes de la couche batiment : {manquantes} "
                             f"(disponibles : {sorted(info['fields'])})")

        source_id = register_source(
            conn, "bdtopo", f"BD TOPO bâtiments (IGN) dépt {dept}",
            f"{TELECHARGEMENT}/{nom}/{nom}.7z", millesime=millesime,
        )
        with conn.cursor() as cur:
            cur.execute("""CREATE TEMP TABLE bati_tmp (id_bdtopo text, nature text,
                           usage_1 text, usage_2 text, legere boolean, nb_logements int, wkb bytea)""")
            # Import remplaçant en une transaction : purge du département, puis chaque
            # lot lu du gpkg est filtré et inséré immédiatement (temp jamais > LOT lignes).
            cur.execute("DELETE FROM bati WHERE dept = %s", (dept,))
            total = 0
            inseres = 0
            while True:
                df = pyogrio.read_dataframe(
                    gpkg, layer="batiment", columns=COLONNES,
                    where="etat_de_l_objet = 'En service'",
                    skip_features=total, max_features=LOT,
                )
                if df.empty:
                    break
                import pandas as pd
                from shapely import to_wkb

                cur.execute("TRUNCATE bati_tmp")
                with cur.copy("COPY bati_tmp FROM STDIN") as copy:
                    for r in df.itertuples():
                        copy.write_row((
                            r.cleabs, r.nature, r.usage_1, r.usage_2,
                            None if pd.isna(r.construction_legere) else bool(r.construction_legere),
                            None if pd.isna(r.nombre_de_logements) else int(r.nombre_de_logements),
                            to_wkb(r.geometry),
                        ))
                cur.execute(SQL_FILTRE_LOT, (dept, source_id, dept + "%"))
                inseres += cur.rowcount
                total += len(df)
                print(f"  bâtiments lus : {total} (retenus : {inseres})")
                if len(df) < LOT:
                    break
            print(f"  bati dépt {dept} : {inseres} bâtiments sur parcelles vendues "
                  f"(millésime {millesime})")
        conn.commit()
    finally:
        conn.close()
        # Le gpkg (~2 Go) est un dérivé de l'archive : tout l'arbre d'extraction est
        # supprimé (dossiers imbriqués du 7z compris) même en cas d'échec, sinon un
        # import interrompu sature le disque au département suivant.
        racine = RAW_DIR / Path(gpkg).relative_to(RAW_DIR).parts[0]
        shutil.rmtree(racine, ignore_errors=True)
