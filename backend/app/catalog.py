"""Catalogue des couches carte (spec §3 et §7 /layers).

Le front construit son panneau Couches uniquement à partir de cette structure :
ajouter une couche = ajouter une entrée ici, aucun code front à modifier.

Noms WMS Géorisques vérifiés le 16/07/2026 contre le GetCapabilities de
https://www.georisques.gouv.fr/services (T-01) : chaque couche marquée
`flux_confirme: True` a renvoyé une tuile GetMap EPSG:3857 valide.
"""

THEME_COLORS = {
    "risques_naturels": "#DB4B4B",
    "risques_technologiques": "#F08050",
    "environnement": "#00A193",
    "urbanisme": "#55579E",
    "marche_ventes": "#00749D",
    "bati": "#8A5599",
}

GEORISQUES_WMS = "https://www.georisques.gouv.fr/services"


def _wms(id: str, theme: str, libelle: str, wms_layer: str, attribution: str = "Géorisques", **extra) -> dict:
    return {
        "id": id,
        "theme": theme,
        "libelle": libelle,
        "mode": "live",
        "type": "wms",
        "url": GEORISQUES_WMS,
        "wms_layer": wms_layer,
        "attribution": attribution,
        "flux_confirme": True,
        **extra,
    }


def _env(id: str, libelle: str, familles: str) -> dict:
    """Zonages INPN importés en base, servis en tuiles vectorielles par /api/tiles/env."""
    return {
        "id": id,
        "theme": "environnement",
        "libelle": libelle,
        "mode": "batch",
        "type": "vector",
        "url": f"/api/tiles/env/{familles}/{{z}}/{{x}}/{{y}}.pbf",
        "source_layer": "zonages",
        "attribution": "INPN / MNHN — WFS PatriNat",
        "flux_confirme": True,
    }


LAYERS: list[dict] = [
    # --- Fonds de carte -------------------------------------------------------
    {
        "id": "fond_ortho",
        "theme": "fonds",
        "libelle": "Orthophotos IGN",
        "mode": "live",
        "type": "xyz",
        "url": (
            "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
            "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM"
            "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg"
        ),
        "attribution": "IGN — Géoplateforme",
        "flux_confirme": True,
    },
    # --- Risques naturels (WMS Géorisques, noms vérifiés T-01) -----------------
    _wms("rga", "risques_naturels", "Retrait-gonflement des argiles", "ALEARG", "Géorisques / BRGM"),
    _wms("remontee_nappes", "risques_naturels", "Inondations — remontée de nappes", "REMNAPPE_FR", "Géorisques / BRGM"),
    # EAIP : le WMS ne sert cette couche qu'entre 1:500 000 et 1:90 000 (zooms tuile
    # 11-12, vérifié au GetCapabilities le 16/07/2026) et dans un bleu très pâle.
    # `zoom_natif_*` borne les requêtes sur la fenêtre servie (MapLibre ré-agrandit
    # au-delà) et `renforcement` assombrit/sature le rendu, sinon invisible sur OSM.
    _wms("eaip", "risques_naturels", "Inondations potentielles (EAIP)", "MASQ_EAIP",
         zoom_natif_min=11, zoom_natif_max=12, renforcement=True, opacite=0.9),
    # `zoom_natif_min` des zonages PPR : le WMS ne les sert qu'à partir du 1:100 000
    # (MaxScaleDenominator au GetCapabilities, vérifié le 20/07/2026) — inutile de
    # demander des tuiles vides en dessous du zoom 13.
    _wms("ppri_zonage", "risques_naturels", "Zonage réglementaire PPR Inondation", "PPRN_ZONE_INOND",
         zoom_natif_min=13),
    _wms("tri_debordement", "risques_naturels", "Surface inondable TRI — crue centennale", "ALEA_SYNT_01_02MOY_FXX",
         zoom_natif_min=11),
    _wms("mvt", "risques_naturels", "Mouvements de terrain", "MVT_LOCALISE", "Géorisques / BRGM",
         zoom_natif_min=10),
    _wms("cavites", "risques_naturels", "Cavités souterraines", "CAVITE_LOCALISEE", "Géorisques / BRGM"),
    _wms("pprn_mvt_zonage", "risques_naturels", "Zonage réglementaire PPR Mouvement de terrain", "PPRN_ZONE_MVT",
         zoom_natif_min=13),
    _wms("pprn_feu_zonage", "risques_naturels", "Zonage réglementaire PPR Feu de forêt", "PPRN_ZONE_FEU",
         zoom_natif_min=13),
    _wms("pprn_littoral_zonage", "risques_naturels", "Zonage réglementaire PPR Littoraux (submersion)", "PPRN_ZONE_SUBMAR",
         zoom_natif_min=13),
    _wms("sismicite", "risques_naturels", "Zonage sismique réglementaire", "risq_zonage_sismique"),
    # Radon : servi depuis la base (ingest admin + ingest radon) et non plus par le WMS
    # Géorisques — celui-ci redessinait ~35 000 communes par tuile à l'échelle France
    # (plusieurs secondes par image). Choroplèthe générique « classes » : maille
    # département ≤ z8 (classe majoritaire), commune ensuite.
    {
        "id": "radon",
        "theme": "risques_naturels",
        "libelle": "Potentiel radon (communes)",
        "mode": "batch",
        "type": "vector",
        "url": "/api/tiles/classes/radon/{z}/{x}/{y}.pbf",
        "source_layer": "classes",
        "rendu": "classes",
        # Rampe ordinale chaude clair→foncé (validée dataviz : luminosité monotone,
        # séparation daltonisme ≥ 14), distincte du violet séquentiel des prix.
        "classes": [
            {"classe": 1, "couleur": "#EDC96B", "libelle": "Catégorie 1 — potentiel faible"},
            {"classe": 2, "couleur": "#E0862F", "libelle": "Catégorie 2 — faible, facteurs aggravants"},
            {"classe": 3, "couleur": "#C03B2E", "libelle": "Catégorie 3 — potentiel significatif"},
        ],
        "note_legende": "Maille département (classe majoritaire des communes) puis commune selon le zoom.",
        "attribution": "Géorisques / IRSN",
        "flux_confirme": True,
    },
    # --- Risques technologiques -------------------------------------------------
    _wms("icpe", "risques_technologiques", "Installations classées (ICPE / Seveso)", "INSTALLATIONS_CLASSEES_SIMPLIFIE"),
    _wms("sis", "risques_technologiques", "Secteurs d'information sur les sols (SIS)", "SSP_CLASSIFICATION_SIS"),
    _wms("casias", "risques_technologiques", "Anciens sites industriels (CASIAS)", "SSP_ETABLISSEMENT"),
    _wms("basol", "risques_technologiques", "Sites pollués — action publique (ex-BASOL)", "SSP_INSTRUCTION"),
    _wms("pprt_zonage", "risques_technologiques", "Zonage réglementaire PPR technologique", "PPRT_ZONE_RISQIND",
         zoom_natif_min=13),
    _wms("pprm_zonage", "risques_technologiques", "Zonage réglementaire PPR minier", "PPRM_ZONE_MINIER",
         zoom_natif_min=13),
    _wms("canalisations", "risques_technologiques", "Canalisations de matières dangereuses", "CANALISATIONS"),
    _wms("inb", "risques_technologiques", "Installations nucléaires de base (INB)", "INSTALLATIONS_NUCLEAIRES"),
    # --- Urbanisme & foncier ----------------------------------------------------
    {
        "id": "zonage_plu",
        "theme": "urbanisme",
        "libelle": "Zonage PLU (GPU)",
        "mode": "live",
        "type": "wms",
        "url": "https://data.geopf.fr/wms-v/ows",
        "wms_layer": "du,psmv",
        "attribution": "Géoportail de l'Urbanisme",
        "flux_confirme": True,
    },
    {
        "id": "parcelles",
        "theme": "urbanisme",
        "libelle": "Parcelles cadastrales",
        "mode": "live",
        "type": "xyz",
        "url": (
            "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
            "&LAYER=CADASTRALPARCELS.PARCELLAIRE_EXPRESS&STYLE=normal&TILEMATRIXSET=PM"
            "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/png"
        ),
        "attribution": "IGN — Parcellaire Express",
        "flux_confirme": True,
    },
    # --- Environnement (batch : tuiles vectorielles servies depuis PostGIS) ------
    _env("natura2000", "Natura 2000", "natura2000"),
    _env("znieff", "ZNIEFF I & II", "znieff1,znieff2"),
    _env("espaces_proteges", "Espaces protégés", "espace_protege"),
    _env("patrimoine_geol", "Patrimoine géologique", "patrimoine_geol"),
    # --- Marché (batch) ----------------------------------------------------------
    {
        "id": "dvf",
        "theme": "marche_ventes",
        "libelle": "Prix au m² (ventes DVF)",
        "mode": "batch",
        "type": "vector",
        "url": "/api/tiles/dvf/{z}/{x}/{y}.pbf",
        "source_layer": "prix",
        # Le front rend cette couche en choroplèthe : prix médian au m² par maille,
        # du département (petits zooms) à la parcelle (grands zooms). Rien n'est
        # dessiné là où aucune vente avec prix n'est connue.
        "rendu": "prix_m2",
        "attribution": "DVF (DGFiP / Etalab) — contours cadastre Etalab",
        "flux_confirme": True,
    },
]

# `couches_rapport` : couches activées sur la carte statique de la section du thème
# dans le rapport PDF (spec §8 ②). Volontairement restreint — superposer les 6 WMS
# de risques naturels rendrait la carte illisible ; l'expert garde tout à l'écran.
THEMES = [
    {"id": "risques_naturels", "libelle": "Risques naturels", "couleur": THEME_COLORS["risques_naturels"], "analyse": True,
     "couches_rapport": ["rga", "ppri_zonage"]},
    {"id": "risques_technologiques", "libelle": "Risques technologiques", "couleur": THEME_COLORS["risques_technologiques"], "analyse": True,
     "couches_rapport": ["icpe", "sis", "pprt_zonage"]},
    {"id": "environnement", "libelle": "Environnement & biodiversité", "couleur": THEME_COLORS["environnement"], "analyse": True,
     "couches_rapport": ["natura2000", "znieff", "espaces_proteges", "patrimoine_geol"]},
    {"id": "urbanisme", "libelle": "Urbanisme & foncier", "couleur": THEME_COLORS["urbanisme"], "analyse": True,
     "couches_rapport": ["zonage_plu"]},
    {"id": "marche_ventes", "libelle": "Marché — ventes (DVF)", "couleur": THEME_COLORS["marche_ventes"], "analyse": True,
     "couches_rapport": ["dvf"]},
    {"id": "fonds", "libelle": "Fonds de carte", "couleur": "#7F7F7F", "analyse": False, "couches_rapport": []},
]
