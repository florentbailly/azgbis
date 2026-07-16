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


def _wms(id: str, theme: str, libelle: str, wms_layer: str, attribution: str = "Géorisques") -> dict:
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
    _wms("eaip", "risques_naturels", "Inondations potentielles (EAIP)", "MASQ_EAIP"),
    _wms("ppri_zonage", "risques_naturels", "Zonage réglementaire PPR Inondation", "PPRN_ZONE_INOND"),
    _wms("mvt", "risques_naturels", "Mouvements de terrain", "MVT_LOCALISE", "Géorisques / BRGM"),
    _wms("cavites", "risques_naturels", "Cavités souterraines", "CAVITE_LOCALISEE", "Géorisques / BRGM"),
    # --- Risques technologiques -------------------------------------------------
    _wms("icpe", "risques_technologiques", "Installations classées (ICPE / Seveso)", "INSTALLATIONS_CLASSEES_SIMPLIFIE"),
    _wms("sis", "risques_technologiques", "Secteurs d'information sur les sols (SIS)", "SSP_CLASSIFICATION_SIS"),
    _wms("casias", "risques_technologiques", "Anciens sites industriels (CASIAS)", "SSP_ETABLISSEMENT"),
    _wms("basol", "risques_technologiques", "Sites pollués — action publique (ex-BASOL)", "SSP_INSTRUCTION"),
    _wms("pprt_zonage", "risques_technologiques", "Zonage réglementaire PPR technologique", "PPRT_ZONE_RISQIND"),
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
    # --- Environnement (batch : PMTiles produites par le pipeline) --------------
    {
        "id": "natura2000",
        "theme": "environnement",
        "libelle": "Natura 2000",
        "mode": "batch",
        "type": "pmtiles",
        "url": "/tiles/env_natura2000.pmtiles",
        "attribution": "INPN / MNHN",
        "flux_confirme": True,
    },
    {
        "id": "znieff",
        "theme": "environnement",
        "libelle": "ZNIEFF I & II",
        "mode": "batch",
        "type": "pmtiles",
        "url": "/tiles/env_znieff.pmtiles",
        "attribution": "INPN / MNHN",
        "flux_confirme": True,
    },
    {
        "id": "espaces_proteges",
        "theme": "environnement",
        "libelle": "Espaces protégés",
        "mode": "batch",
        "type": "pmtiles",
        "url": "/tiles/env_espaces_proteges.pmtiles",
        "attribution": "INPN / MNHN",
        "flux_confirme": True,
    },
    # --- Marché (batch) ----------------------------------------------------------
    {
        "id": "dvf",
        "theme": "marche_ventes",
        "libelle": "Transactions DVF (typologie enrichie)",
        "mode": "batch",
        "type": "pmtiles",
        "url": "/tiles/dvf.pmtiles",
        "attribution": "DGFiP / Etalab — enrichi BDNB, SIRENE",
        "flux_confirme": True,
    },
]

THEMES = [
    {"id": "risques_naturels", "libelle": "Risques naturels", "couleur": THEME_COLORS["risques_naturels"], "analyse": True},
    {"id": "risques_technologiques", "libelle": "Risques technologiques", "couleur": THEME_COLORS["risques_technologiques"], "analyse": True},
    {"id": "environnement", "libelle": "Environnement & biodiversité", "couleur": THEME_COLORS["environnement"], "analyse": True},
    {"id": "urbanisme", "libelle": "Urbanisme & foncier", "couleur": THEME_COLORS["urbanisme"], "analyse": True},
    {"id": "marche_ventes", "libelle": "Marché — ventes (DVF)", "couleur": THEME_COLORS["marche_ventes"], "analyse": True},
    {"id": "fonds", "libelle": "Fonds de carte", "couleur": "#7F7F7F", "analyse": False},
]
