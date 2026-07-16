"""Import DVF géolocalisé (Etalab) : https://files.data.gouv.fr/geo-dvf/latest/csv/

Classification typologique initiale (spec §5, niveaux 1 et 5) :
  - Maison / Appartement          -> residentiel   (source dvf, confiance haute)
  - Dépendance                    -> autre         (source dvf, confiance haute)
  - Local industriel/commercial   -> tertiaire_non_qualifie (confiance nulle)
Les niveaux 2-4 (BDNB, SIRENE, heuristiques) sont le POC T-02 : `ingest enrich` (à venir).
"""
import datetime

import httpx
import pandas as pd

from .common import db, download, register_source, sha256

GEODVF = "https://files.data.gouv.fr/geo-dvf/latest/csv"

TYPO_DVF = {
    "Maison": ("residentiel", "haute"),
    "Appartement": ("residentiel", "haute"),
    "Dépendance": ("autre", "haute"),
}


def run(dept: str, years: list[int]) -> None:
    conn = db()
    for year in years:
        url = f"{GEODVF}/{year}/departements/{dept}.csv.gz"
        try:
            path = download(url, f"dvf_{year}_{dept}.csv.gz")
        except httpx.HTTPStatusError as e:
            # Le « latest » geo-dvf ne conserve que les 5 dernières années publiées :
            # une année sortie de la fenêtre renvoie 404 (constaté pour 2020 le 16/07/2026).
            print(f"  {year}/{dept} : indisponible ({e.response.status_code}) — année ignorée")
            continue
        df = pd.read_csv(path, compression="gzip", dtype={"code_commune": str, "id_parcelle": str}, low_memory=False)
        df = df.dropna(subset=["longitude", "latitude", "id_mutation", "date_mutation"])
        source_id = register_source(
            conn, "dvf", f"DVF géolocalisé {year} dépt {dept}", url,
            millesime=str(year), checksum=sha256(path),
        )

        mutations = df.drop_duplicates("id_mutation")
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO dvf_mutations (id_mutation, date_mutation, nature_mutation,
                       valeur_fonciere, code_commune, source_id, geom)
                   VALUES (%s, %s, %s, %s, %s, %s,
                           ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 2154))
                   ON CONFLICT (id_mutation) DO NOTHING""",
                [
                    (r.id_mutation, r.date_mutation, r.nature_mutation,
                     None if pd.isna(r.valeur_fonciere) else float(r.valeur_fonciere),
                     r.code_commune, source_id, float(r.longitude), float(r.latitude))
                    for r in mutations.itertuples()
                ],
            )
            # Un local par ligne ayant un type_local ; prix/m² seulement si la mutation
            # ne compte qu'un local bâti (sinon la ventilation est arbitraire).
            locaux = df[df["type_local"].notna()].copy()
            nb_locaux = locaux.groupby("id_mutation")["type_local"].transform("size")
            rows = []
            for r, nb in zip(locaux.itertuples(), nb_locaux):
                typo, conf = TYPO_DVF.get(r.type_local, ("tertiaire_non_qualifie", "nulle"))
                surface = None if pd.isna(r.surface_reelle_bati) else float(r.surface_reelle_bati)
                prix_m2 = None
                if nb == 1 and surface and surface > 0 and not pd.isna(r.valeur_fonciere):
                    prix_m2 = round(float(r.valeur_fonciere) / surface, 2)
                rows.append((
                    r.id_mutation, r.type_local, surface,
                    None if pd.isna(r.surface_terrain) else float(r.surface_terrain),
                    None if pd.isna(r.nombre_pieces_principales) else int(r.nombre_pieces_principales),
                    r.id_parcelle, typo, "dvf", conf, prix_m2,
                ))
            cur.executemany(
                """INSERT INTO dvf_locaux (id_mutation, type_local_dvf, surface_reelle_bati,
                       surface_terrain, nb_pieces, id_parcelle,
                       typologie, typologie_source, typologie_confiance, prix_m2)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                rows,
            )
        conn.commit()
        print(f"  {year}/{dept} : {len(mutations)} mutations, {len(rows)} locaux importés "
              f"({datetime.datetime.now():%H:%M:%S})")
    conn.close()
