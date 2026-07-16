"""Import des zonages INPN via le WFS PatriNat de la Géoplateforme (data.geopf.fr).

Les jeux « INPN — Données du programme ZNIEFF / Natura 2000 » publiés par le MNHN sur
data.gouv.fr ne sont que des liens vers inpn.mnhn.fr/docs/Shape/*.zip, aujourd'hui morts
(404 constaté le 16/07/2026, data.gouv.fr signale lui-même les ressources indisponibles).
data.gouv.fr référence en revanche le WFS PatriNat, qui sert les mêmes zonages nationaux
avec un schéma harmonisé (id_mnhn, nom_site, url_fiche) et se télécharge sans intervention
manuelle — c'est la source retenue.

  python -m ingest inpn --famille znieff1
  python -m ingest inpn --famille natura2000              # SIC (Habitats) + ZPS (Oiseaux)
  python -m ingest inpn --famille znieff1 --file x.zip    # repli : extract local (shp/GPKG)

Le brut est conservé daté dans PIPELINE_RAW_DIR (spec §9) et son empreinte SHA-256
enregistrée dans `sources` : c'est ce qui alimente la page de traçabilité du rapport.
"""
import datetime
import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from .common import RAW_DIR, db, register_source, sha256, ssl_context

WFS = "https://data.geopf.fr/wfs/ows"
PAGE = 500  # features par requête WFS
GEN_TOLERANCE_M = 50  # tolérance de la géométrie généralisée d'affichage (colonne geom_gen)


@dataclass(frozen=True)
class Layer:
    key: str
    typename: str
    libelle: str
    territoire: bool = True  # la couche porte-t-elle le champ `territoire` (filtre métropole) ?


# Une famille = une ou plusieurs couches WFS (Natura 2000 = directive Habitats + Oiseaux).
LAYERS: dict[str, list[Layer]] = {
    "znieff1": [Layer("znieff1", "patrinat_znieff1:znieff1", "ZNIEFF de type I")],
    "znieff2": [Layer("znieff2", "patrinat_znieff2:znieff2", "ZNIEFF de type II")],
    "natura2000": [
        Layer("sic", "patrinat_sic:sic", "Natura 2000 — SIC/ZSC (directive Habitats)"),
        Layer("zps", "patrinat_zps:zps", "Natura 2000 — ZPS (directive Oiseaux)"),
    ],
    "espace_protege": [
        Layer("pn", "patrinat_pn:parc_national", "Parcs nationaux", territoire=False),
        Layer("pnr", "patrinat_pnr:pnr", "Parcs naturels régionaux"),
        Layer("rnn", "patrinat_rnn:rnn", "Réserves naturelles nationales"),
        Layer("rnr", "patrinat_rnr:rnr", "Réserves naturelles régionales"),
        Layer("apb", "patrinat_apb:apb", "Arrêtés de protection de biotope"),
        Layer("rb", "patrinat_rb:reserve_biologique", "Réserves biologiques", territoire=False),
        Layer("cdl", "patrinat_cdl:conservatoire_littoral", "Conservatoire du littoral", territoire=False),
        Layer("rncfs", "patrinat_rncfs:rncfs", "Réserves de chasse et faune sauvage", territoire=False),
        Layer("bios", "patrinat_bios:bios", "Réserves de biosphère (UNESCO)"),
    ],
    "patrimoine_geol": [
        Layer("inpg", "patrinat_inpg:inpg", "Inventaire national du patrimoine géologique"),
    ],
}
FAMILLES = list(LAYERS)

# Géométries stockées en Lambert-93 (spec §6) : demandées directement au WFS, qui les
# projette lui-même. ST_MakeValid + CollectionExtract(3) écartent les anneaux dégénérés
# (fréquents sur les gros contours ZNIEFF) qui feraient échouer ST_Intersects à l'analyse.
INSERT = """
    INSERT INTO env_zonages (famille, code_national, libelle, url_fiche_inpn, source_id, geom)
    VALUES (%s, %s, %s, %s, %s,
            ST_Multi(ST_CollectionExtract(ST_MakeValid(
                ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON(%s), 2154))), 3)))
"""


def _page_url(layer: Layer, start: int, territoire: str | None) -> str:
    url = (
        f"{WFS}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
        f"&TYPENAMES={layer.typename}&COUNT={PAGE}&STARTINDEX={start}"
        "&SRSNAME=EPSG:2154&OUTPUTFORMAT=application/json"
    )
    if territoire and layer.territoire:
        url += f"&CQL_FILTER=territoire%3D%27{territoire}%27"
    return url


def _import_layer(conn, client: httpx.Client, famille: str, layer: Layer, territoire: str | None) -> int:
    stamp = datetime.date.today().isoformat()
    raw = RAW_DIR / f"inpn_{layer.key}_{stamp}.geojson"
    source_id = register_source(
        conn, f"inpn_{layer.key}", f"INPN — {layer.libelle}",
        f"{WFS}?TYPENAMES={layer.typename}", millesime=stamp,
    )

    total = 0
    # Écriture au fil de l'eau : un contour ZNIEFF national pèse plusieurs centaines de Mo
    # en GeoJSON, on ne le charge jamais entièrement en mémoire.
    with open(raw, "w", encoding="utf-8") as f:
        f.write('{"type":"FeatureCollection","features":[')
        with conn.cursor() as cur:
            while True:
                r = client.get(_page_url(layer, total, territoire), timeout=300)
                r.raise_for_status()
                feats = r.json()["features"]
                if not feats:
                    break
                for feat in feats:
                    f.write(("," if total else "") + json.dumps(feat, ensure_ascii=False))
                    p = feat["properties"]
                    cur.execute(INSERT, (
                        famille, p.get("id_mnhn"), p.get("nom_site"), p.get("url_fiche"),
                        source_id, json.dumps(feat["geometry"]),
                    ))
                    total += 1
                print(f"    {layer.key} : {total} zonages…", end="\r")
                if len(feats) < PAGE:
                    break
        f.write("]}")

    with conn.cursor() as cur:
        cur.execute("UPDATE sources SET checksum = %s WHERE id = %s", (sha256(raw), source_id))
    conn.commit()
    print(f"    {layer.key:8} {total:>6} zonages  ({raw.name}, {raw.stat().st_size / 1e6:.0f} Mo)")
    return total


def _generaliser(conn, famille: str) -> None:
    """Calcule les colonnes d'affichage : `geom_gen` (~50 m) et `surface_m2`."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE env_zonages
               SET geom_gen = ST_Multi(ST_CollectionExtract(
                       ST_MakeValid(ST_SimplifyPreserveTopology(geom, %s)), 3)),
                   surface_m2 = ST_Area(geom)
               WHERE famille = %s""",
            (GEN_TOLERANCE_M, famille),
        )
        # Un petit zonage peut disparaître à la simplification : on garde alors l'original.
        cur.execute(
            """UPDATE env_zonages SET geom_gen = geom
               WHERE famille = %s AND (geom_gen IS NULL OR ST_IsEmpty(geom_gen))""",
            (famille,),
        )
    conn.commit()


def _import_file(conn, famille: str, file: str) -> int:
    """Repli hors ligne : archive shapefile/GPKG déjà téléchargée."""
    import geopandas as gpd
    from shapely.geometry import MultiPolygon

    path = Path(file)
    gdf = gpd.read_file(path).to_crs(2154)
    gdf["geometry"] = gdf.geometry.apply(
        lambda g: g if g.geom_type == "MultiPolygon"
        else MultiPolygon([g]) if g.geom_type == "Polygon" else None
    )
    gdf = gdf.dropna(subset=["geometry"])

    source_id = register_source(
        conn, f"inpn_{famille}", f"INPN — {famille} (fichier local)", str(path),
        millesime=path.stem, checksum=sha256(path),
    )
    code_fields = ["id_mnhn", "SITECODE", "ID_MNHN", "ID_SPN", "CODE", "id_local"]
    name_fields = ["nom_site", "SITENAME", "NOM", "NOM_SITE", "LIB", "nom"]
    pick = lambda row, fields: next(  # noqa: E731
        (str(row[f]) for f in fields if f in row and row[f] is not None), None
    )
    with conn.cursor() as cur:
        for _, row in gdf.iterrows():
            cur.execute(INSERT, (
                famille, pick(row, code_fields), pick(row, name_fields),
                row["url_fiche"] if "url_fiche" in row else None,
                source_id, json.dumps(row.geometry.__geo_interface__),
            ))
    conn.commit()
    return len(gdf)


def run(famille: str, file: str | None = None, territoire: str | None = "METROP") -> None:
    if famille not in LAYERS:
        raise SystemExit(f"famille inconnue : {famille} (attendu : {', '.join(FAMILLES)})")

    conn = db()
    # Import remplaçant : purge de la famille entière avant recharge (spec §6). Pour
    # natura2000 la purge précède les deux couches, sinon ZPS effacerait les SIC.
    with conn.cursor() as cur:
        cur.execute("DELETE FROM env_zonages WHERE famille = %s", (famille,))
    conn.commit()

    if file:
        n = _import_file(conn, famille, file)
        origine = f"depuis {Path(file).name}"
    else:
        n = 0
        with httpx.Client(verify=ssl_context(), follow_redirects=True) as client:
            for layer in LAYERS[famille]:
                n += _import_layer(conn, client, famille, layer, territoire)
        origine = f"(WFS PatriNat{', métropole' if territoire else ''})"

    _generaliser(conn, famille)
    print(f"  {famille} : {n} zonages importés {origine}")
    conn.close()
