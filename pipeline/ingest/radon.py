"""Potentiel radon des communes (IRSN via l'API Géorisques) → carto_classes.

Remplace le WMS Géorisques RADON sur la carte : à l'échelle France, ce WMS redessine
~35 000 communes par tuile et met plusieurs secondes par image. Ici la donnée (une
classe 1-3 par commune, quasi statique — arrêté du 27 juin 2018) est importée puis
servie par nos tuiles vectorielles multi-niveaux (/api/tiles/classes/radon).

L'API couvre la quasi-totalité des communes (34 175/35 014 au 21/07/2026) ; les
absentes (collectivités d'outre-mer surtout) retombent en classe 1 par défaut.
Interrogation par lots de 20 codes INSEE (taille testée OK), ~5-10 min au total.
Prérequis : `ingest admin` (les codes et contours communaux viennent d'admin_contours).
"""
import datetime
import time

import httpx

from .common import db, register_source, ssl_context

API = "https://www.georisques.gouv.fr/api/v1/radon"
LOT = 20

# Niveau département : classe MAJORITAIRE des communes (mode). La classe max serait
# systématiquement alarmiste (presque chaque département a une poche granitique) ;
# la méthode est rappelée dans la légende de la couche.
SQL_COMMUNES = """
    INSERT INTO carto_classes (couche, niveau, code, libelle, classe, source_id, geom)
    SELECT 'radon', 'commune', a.code, a.libelle, r.classe, %s, a.geom
    FROM admin_contours a JOIN radon_tmp r ON r.code = a.code
    WHERE a.niveau = 'commune'
"""
SQL_DEPARTEMENTS = """
    INSERT INTO carto_classes (couche, niveau, code, libelle, classe, source_id, geom)
    SELECT 'radon', 'departement', a.code, a.libelle, m.classe, %s, a.geom
    FROM admin_contours a
    JOIN LATERAL (
        SELECT mode() WITHIN GROUP (ORDER BY r.classe) AS classe
        FROM radon_tmp r
        WHERE a.code = CASE WHEN r.code LIKE '97%%' THEN left(r.code, 3)
                            ELSE left(r.code, 2) END
    ) m ON m.classe IS NOT NULL  -- écarte les territoires sans commune classée (ex. 984, TAAF)
    WHERE a.niveau = 'departement'
"""


def _classes_api(codes: list[str]) -> dict[str, int]:
    """classe par code INSEE, via l'API par lots ; absent de la réponse = classe 1."""
    classes: dict[str, int] = {}
    with httpx.Client(verify=ssl_context(), timeout=60) as client:
        for i in range(0, len(codes), LOT):
            lot = codes[i:i + LOT]
            for tentative in range(3):
                try:
                    r = client.get(API, params={"code_insee": ",".join(lot), "page_size": str(LOT)})
                    r.raise_for_status()
                    break
                except httpx.HTTPError:
                    if tentative == 2:
                        raise
                    time.sleep(5)
            for d in r.json()["data"]:
                classes[d["code_insee"]] = int(d["classe_potentiel"])
            if (i // LOT) % 100 == 0:
                print(f"  API radon : {i}/{len(codes)} communes interrogées")
            time.sleep(0.05)  # politesse
    return classes


def run() -> None:
    conn = db()
    with conn.cursor() as cur:
        cur.execute("SELECT code FROM admin_contours WHERE niveau = 'commune' ORDER BY code")
        codes = [r[0] for r in cur.fetchall()]
    if not codes:
        raise SystemExit("admin_contours vide : lancer `ingest admin` d'abord.")

    classes = _classes_api(codes)
    print(f"  communes classées par l'API : {len(classes)} ; classe 1 par défaut (absentes) : {len(codes) - len(classes)}")

    source_id = register_source(
        conn, "radon", "Potentiel radon des communes (IRSN / Géorisques)", API,
        millesime=datetime.date.today().isoformat(),
    )
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE radon_tmp (code text PRIMARY KEY, classe smallint)")
        rows = [(c, classes.get(c, 1)) for c in codes]
        for i in range(0, len(rows), 5000):
            cur.executemany("INSERT INTO radon_tmp VALUES (%s, %s)", rows[i:i + 5000])
        cur.execute("DELETE FROM carto_classes WHERE couche = 'radon'")  # remplaçant
        cur.execute(SQL_COMMUNES, (source_id,))
        print(f"  carto_classes commune : {cur.rowcount}")
        cur.execute(SQL_DEPARTEMENTS, (source_id,))
        print(f"  carto_classes departement : {cur.rowcount}")
    conn.commit()
    conn.close()
