"""Libellés métier du rapport — mêmes intitulés que le panneau Analyse du front
(frontend/src/components/AnalysisPanel.tsx) : l'écran et le papier disent la même chose.
Toute évolution des libellés doit être répercutée des deux côtés.
"""

LABELS: dict[str, str] = {
    "argiles_rga": "Exposition retrait-gonflement des argiles",
    "mouvements_terrain_nb": "Mouvements de terrain recensés",
    "cavites_nb": "Cavités souterraines recensées",
    "azi_nb": "Atlas des zones inondables (AZI)",
    "tri_nb": "Territoires à risque important d'inondation (TRI)",
    "procedures_gaspar_nb": "Procédures de prévention des risques (GASPAR)",
    "radon_potentiel": "Potentiel radon (1 faible → 3 significatif)",
    "zonage_sismique": "Zonage sismique",
    "icpe_nb": "Installations classées (ICPE)",
    "seveso_nb": "dont établissements Seveso",
    "sites_pollues_casias_nb": "Anciens sites industriels (CASIAS)",
    "sis_nb": "Secteurs d'information sur les sols (SIS)",
    "conclusions_sup_nb": "Servitudes d'utilité publique « sols »",
    "zones_plu_nb": "Zones de PLU intersectées",
    "peb_present": "Plan d'exposition au bruit (PEB)",
    "natura2000_nb": "Sites Natura 2000",
    "znieff1_nb": "ZNIEFF de type I",
    "znieff2_nb": "ZNIEFF de type II",
    "espace_protege_nb": "Espaces protégés",
    "patrimoine_geol_nb": "Patrimoine géologique",
    "nb_transactions_zone_contexte": "Transactions (zone de contexte)",
}

CATEGORY_LABELS: dict[str, str] = {
    "icpe": "ICPE",
    "casias": "Site CASIAS",
    "sis": "SIS",
    "mouvement_terrain": "Mouvement de terrain",
    "cavite": "Cavité",
    "azi": "AZI",
    "tri": "TRI",
    "procedure_gaspar": "Procédure",
    "prescription": "Prescription",
    "servitude": "Servitude",
    "transaction": "Transaction",
    "natura2000": "Natura 2000",
    "znieff1": "ZNIEFF I",
    "znieff2": "ZNIEFF II",
    "espace_protege": "Espace protégé",
    "patrimoine_geol": "Patrimoine géol.",
}

# Champs servant de titre à un élément détaillé, par ordre de préférence
# (mêmes règles que le front).
TITLE_FIELDS = [
    "nom", "libelle", "nom_etablissement", "raisonSociale", "raison_sociale", "nom_ouvrage",
    "libelle_azi", "libelle_tri", "libelle_risque_long", "type", "identifiant_ssp", "id_mutation",
]
HIDDEN_FIELDS = {"categorie", "geog", "geom", "geometry", "bbox"}

# Notes méthodologiques courtes par thème (spec §8 ④).
NOTES_METHODO: dict[str, str] = {
    "risques_naturels": "Interrogation en direct des API Géorisques sur l'emprise de la zone "
                        "d'étude (rayon englobant). Les indicateurs reflètent l'état des bases "
                        "nationales au moment de la génération du rapport.",
    "risques_technologiques": "ICPE, SIS et anciens sites industriels (CASIAS) interrogés en "
                              "direct via Géorisques sur l'emprise de la zone d'étude.",
    "environnement": "Intersection exacte (PostGIS) entre la zone d'étude et les zonages INPN "
                     "importés (WFS PatriNat, géométries pleine résolution). La carte utilise "
                     "les mêmes données que le calcul.",
    "urbanisme": "Zonage PLU, prescriptions et servitudes interrogés via le Géoportail de "
                 "l'Urbanisme (API Carto). Une commune au RNU ou non couverte est signalée.",
    "marche_ventes": "Transactions DVF géolocalisées (Etalab) dans la zone de contexte. Prix/m² "
                     "calculé uniquement pour les mutations mono-local bâti ; médiane par "
                     "typologie. Typologie : niveau « dvf » (enrichissement BDNB/SIRENE à venir, "
                     "les locaux d'activité restent « tertiaire_non_qualifie »).",
}
