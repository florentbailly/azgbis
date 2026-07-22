"""Enrichissement typologique des locaux DVF (spec §5) : `ingest enrich`.

Qualifie les locaux `tertiaire_non_qualifie` (DVF « Local industriel et commercial
ou assimilé ») par croisement parcellaire, dans l'ordre de priorité de la spec :

  1. bâti BD TOPO de la parcelle (`ingest bati`) : usage dominant pondéré par la
     surface d'intersection — Industriel/Agricole concluent directement (source
     `bdtopo`, confiance haute si usage unique, moyenne si parcelle mixte) ;
  2. établissements SIRENE actifs de la parcelle (`ingest sirene`) : le code NAF
     dominant arbitre bureaux/commerce/industriel/agricole/autre (source `sirene`,
     confiance moyenne si net, basse si mélangé) — c'est lui qui départage l'usage
     BD TOPO « Commercial et services », muet sur cette distinction ;
  3. sinon le local RESTE `tertiaire_non_qualifie` (jamais reclassé arbitrairement).

Relançable après tout import DVF/BD TOPO/SIRENE : les typologies `bdtopo`/`sirene`
sont réinitialisées puis recalculées en une transaction. Le taux de non-qualifiés
parmi les locaux d'activité est affiché (objectif spec : < 15 %).

Les fonctions de décision sont pures (sans base) et testées dans backend/tests.
"""

# Usages BD TOPO retenus pour la dominance (les « Annexe », « Indifférencié »,
# « Religieux », « Sportif »… ne qualifient pas un local d'activité).
USAGES_UTILES = {"Résidentiel", "Commercial et services", "Industriel", "Agricole"}
USAGE_DIRECT = {"Industriel": "industriel", "Agricole": "agricole"}

SEUIL_DOMINANT = 0.5  # part de surface bâtie minimale pour conclure via BD TOPO
SEUIL_NET = 0.6       # part d'établissements minimale pour une confiance moyenne


def typologie_naf(naf: str) -> str | None:
    """Nomenclature azgbis depuis une division NAF rév. 2 (deux premiers chiffres).

    Regroupement assumé (documenté dans la note méthodologique du rapport) :
    industrie, construction, transport-entreposage -> industriel ; commerce,
    hébergement-restauration, réparation et services personnels -> commerce ;
    information, finance, immobilier, conseil, services administratifs, poste et
    administration publique -> bureaux ; enseignement, santé, arts -> autre.
    """
    try:
        division = int(naf[:2])
    except (TypeError, ValueError):
        return None
    # 68.20 (SCI, loueurs de biens) : domiciliés dans le bien qu'ils possèdent, quel
    # qu'en soit l'usage — 22 % des établissements du Rhône, ils écrasaient l'arbitrage
    # vers « bureaux » (constat du 22/07/2026). Écartés de la décision.
    if naf.startswith("68.20"):
        return None
    if division <= 3:
        return "agricole"
    if division in (45, 46, 47, 55, 56, 95, 96):
        return "commerce"
    if division <= 43 or division in (49, 50, 51, 52):
        return "industriel"
    if division == 53 or 58 <= division <= 84:
        return "bureaux"
    return "autre"  # 85-94 (enseignement, santé, arts…), 97-99


def decider(aires_usages: dict[str, float], nafs: dict[str, int]) -> tuple[str, str, str] | None:
    """(typologie, source, confiance) d'une parcelle, ou None si rien ne conclut.

    `aires_usages` : surface bâtie par usage_1 BD TOPO sur la parcelle (m²).
    `nafs` : nombre d'établissements actifs par code NAF sur la parcelle.
    """
    utiles = {u: a for u, a in aires_usages.items() if u in USAGES_UTILES and a > 0}
    if utiles:
        usage = max(utiles, key=utiles.get)
        part = utiles[usage] / sum(utiles.values())
        if usage in USAGE_DIRECT and part >= SEUIL_DOMINANT:
            return USAGE_DIRECT[usage], "bdtopo", "haute" if len(utiles) == 1 else "moyenne"

    comptes: dict[str, int] = {}
    for naf, nb in nafs.items():
        typo = typologie_naf(naf)
        if typo:
            comptes[typo] = comptes.get(typo, 0) + nb
    if comptes:
        typo = max(comptes, key=comptes.get)
        part = comptes[typo] / sum(comptes.values())
        return typo, "sirene", "moyenne" if part >= SEUIL_NET else "basse"
    return None


SQL_RESET = """
    UPDATE dvf_locaux SET typologie = 'tertiaire_non_qualifie',
           typologie_source = 'dvf', typologie_confiance = 'nulle'
    WHERE typologie_source <> 'dvf'
"""

# Parcelles des locaux à qualifier (contours importés par `ingest contours`).
SQL_CIBLES = """
    CREATE TEMP TABLE cible AS
    SELECT DISTINCT c.code AS id_parcelle, c.geom
    FROM dvf_locaux l
    JOIN contours c ON c.niveau = 'parcelle' AND c.code = l.id_parcelle
    WHERE l.typologie = 'tertiaire_non_qualifie'
"""

SQL_AIRES = """
    SELECT t.id_parcelle, b.usage_1, sum(ST_Area(ST_Intersection(b.geom, t.geom)))
    FROM cible t JOIN bati b ON ST_Intersects(b.geom, t.geom)
    WHERE b.usage_1 IS NOT NULL
    GROUP BY 1, 2
"""

# 10 m de tolérance : les points SIRENE (géocodage adresse) tombent parfois sur la
# voie, juste hors de la parcelle.
SQL_NAFS = """
    SELECT t.id_parcelle, e.naf, count(*)
    FROM cible t JOIN sirene_etablissements e ON ST_DWithin(e.geom, t.geom, 10)
    GROUP BY 1, 2
"""

# Dénominateur : les locaux d'activité DVF (tout sauf Maison/Appartement/Dépendance).
SQL_TAUX = """
    SELECT count(*) FILTER (WHERE typologie = 'tertiaire_non_qualifie'), count(*)
    FROM dvf_locaux
    WHERE type_local_dvf NOT IN ('Maison', 'Appartement', 'Dépendance')
"""


def run() -> None:
    from .common import db

    conn = db()
    with conn.cursor() as cur:
        for table, message in (("bati", "`ingest bati`"), ("sirene_etablissements", "`ingest sirene`")):
            cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 — noms internes
            if cur.fetchone()[0] == 0:
                raise SystemExit(f"Table {table} vide : lancer {message} d'abord.")

        cur.execute(SQL_RESET)
        cur.execute(SQL_CIBLES)
        cur.execute("SELECT count(*) FROM cible")
        nb_parcelles = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FROM dvf_locaux l
                       WHERE l.typologie = 'tertiaire_non_qualifie'
                         AND NOT EXISTS (SELECT 1 FROM contours c
                                         WHERE c.niveau = 'parcelle' AND c.code = l.id_parcelle)""")
        sans_parcelle = cur.fetchone()[0]
        print(f"  parcelles à qualifier : {nb_parcelles} "
              f"(locaux sans contour parcellaire, non enrichis : {sans_parcelle})")

        aires: dict[str, dict[str, float]] = {}
        cur.execute(SQL_AIRES)
        for id_parcelle, usage, aire in cur.fetchall():
            aires.setdefault(id_parcelle, {})[usage] = float(aire)
        nafs: dict[str, dict[str, int]] = {}
        cur.execute(SQL_NAFS)
        for id_parcelle, naf, nb in cur.fetchall():
            nafs.setdefault(id_parcelle, {})[naf] = nb

        decisions = []
        par_source: dict[str, int] = {}
        for id_parcelle in aires.keys() | nafs.keys():
            d = decider(aires.get(id_parcelle, {}), nafs.get(id_parcelle, {}))
            if d:
                decisions.append((*d, id_parcelle))
                par_source[d[1]] = par_source.get(d[1], 0) + 1
        cur.executemany(
            """UPDATE dvf_locaux SET typologie = %s, typologie_source = %s,
                   typologie_confiance = %s
               WHERE id_parcelle = %s AND typologie = 'tertiaire_non_qualifie'""",
            decisions,
        )
        print(f"  parcelles qualifiées : {len(decisions)} "
              f"({', '.join(f'{k} : {v}' for k, v in sorted(par_source.items()))})")

        cur.execute(SQL_TAUX)
        restants, activite = cur.fetchone()
        if activite:
            print(f"  locaux d'activité non qualifiés : {restants}/{activite} "
                  f"({100 * restants / activite:.1f} % — objectif spec < 15 %)")
    conn.commit()
    conn.close()
