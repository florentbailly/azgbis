# Spécification détaillée — Lot 1

Outil de qualification de zone géographique (France) pour experts immobiliers.
Version 1.0 — 15/07/2026.

---

## 1. Périmètre du lot 1

### Inclus

- Carte de France interactive (fond open source), sélecteur de couches par thème.
- Couches **live** : risques naturels, risques technologiques, urbanisme (zonage PLU/prescriptions/servitudes via GPU), cadastre.
- Couches **batch** : biodiversité (INPN), transactions DVF enrichies (dont **typologie tertiaire fiabilisée** via BDNB + SIRENE), DPE.
- Sélection de zone : polygone dessiné, ou point + petit rayon + grand rayon.
- Analyse de zone : agrégats par thème sur la zone sélectionnée.
- Rapport PDF paginé (piste d'audit) sur les thèmes cochés, avec cartes statiques.
- Export Excel détaillé des transactions DVF de la zone.

### Exclus (lots ultérieurs)

- Authentification, comptes utilisateurs, mémoire côté serveur (zones privées : stockage navigateur uniquement).
- Stockage des PDF générés (l'expert télécharge, l'outil ne conserve rien).
- Loyers, équipements/BPE, transports/GTFS, gouvernance locale, INSEE socio-éco, RPLS, personnes morales (lot 2).
- Outils de calcul (taxe d'aménagement, capacité constructive) (lot 2).
- Extraction des règles écrites des PLU ; annonces de portails ; propriétaires personnes physiques (hors périmètre, décision du 15/07/2026).

### Dimensionnement cible

~10 utilisateurs simultanés max, ~100 rapports/mois, ~5 000 analyses de zone/mois. Aucun enjeu de montée en charge : une seule VM suffit (§10).

---

## 2. Charte graphique

Palette client (14 couleurs) et affectation :

| Hex | RGB | Usage |
|---|---|---|
| `#581D74` | 88,29,116 | **Primaire** : en-têtes UI et rapport, boutons |
| `#66327A` | 102,50,122 | Primaire hover / titres de section du rapport |
| `#8A5599` | 138,85,153 | Thème *Bâti & occupants* |
| `#B34A8C` | 179,74,140 | Thème *Territoire & gouvernance* (lot 2) |
| `#00A193` | 0,161,147 | Thème *Environnement & biodiversité* |
| `#EAB818` | 234,184,24 | Thème *Équipements & accessibilité* (lot 2) ; surlignage sélection |
| `#DB4B4B` | 219,75,75 | Thème *Risques naturels* |
| `#F08050` | 240,128,80 | Thème *Risques technologiques* |
| `#55579E` | 85,87,158 | Thème *Urbanisme & foncier* |
| `#00749D` | 0,116,157 | Thème *Marché — ventes (DVF)* |
| `#6694CE` | 102,148,206 | Thème *Marché — locatif* (lot 2) |
| `#D16B76` | 209,107,118 | Alertes secondaires, aplats de risque atténués |
| `#7F7F7F` | 127,127,127 | Texte secondaire, axes |
| `#BFBFBF` | 191,191,191 | Bordures, fonds neutres, grilles |

Ces couleurs sont déclarées comme design tokens CSS (`--color-theme-risques-nat`, etc.) et réutilisées à l'identique dans le PDF : la couleur d'un thème est la même à l'écran, dans la légende carte et dans le rapport. Le contour de la zone d'étude est toujours `#581D74` (petit rayon / polygone) et `#8A5599` pointillé (grand rayon).

À l'intérieur d'une couche, les gradations (ex. aléa faible→fort) sont des déclinaisons en luminosité de la couleur du thème, validées pour le contraste (règles du skill dataviz à appliquer à l'implémentation).

---

## 3. Catalogue des couches — lot 1

Colonne « Mode » : **live** = appelé à la volée (affichage WMS + interrogation API pour le rapport) ; **batch** = intégré en PostGIS par le pipeline (§9), puis affiché en tuiles vectorielles.

Deux voies de tuilage pour les couches batch, selon le volume :
- **MVT servies depuis PostGIS** (`ST_AsMVT`) : zonages INPN (`GET /api/tiles/env/…`, ~21 000 polygones) et carte des prix DVF (`GET /api/tiles/dvf/…`, agrégats précalculés). Mêmes données que l'analyse, donc aucun décalage possible entre la carte et les conclusions du rapport, et aucune étape de régénération après import. Généralisation d'affichage côté INPN : géométrie précalculée à 50 m sous z10 et masquage des zonages de moins de 2×2 pixels (le rapport, lui, lit toujours `geom` en pleine résolution).
- **PMTiles statiques** (tippecanoe, servies par Caddy) réservées à d'éventuels gros volumes figés (fond cadastral complet) — aucune en service à ce stade.

### 3.1 Risques naturels — `#DB4B4B`

| Couche | Source / flux | Mode |
|---|---|---|
| Retrait-gonflement des argiles (RGA) | API Géorisques `GET /v1/rga` + WMS Géorisques | live |
| Mouvements de terrain | API Géorisques `GET /v1/mvt` + WMS | live |
| Cavités souterraines | API Géorisques `GET /v1/cavites` + WMS | live |
| Inondation — débordement de cours d'eau, ruissellement, submersion marine (TRI/AZI) | API Géorisques (`/v1/gaspar/azi`, `/v1/gaspar/tri`) + WMS | live |
| Inondation — remontée de nappes | WMS Géorisques (couche nappes) + API | live |
| Zonages réglementaires : PPRI, PPRN, PPRMT | API Géorisques `/v1/gaspar/risques` + `/v1/ppr` + WMS | live |
| Radon (potentiel communal) | API Géorisques `/v1/radon` | live (rapport uniquement, pas de couche carte) |
| Zonage sismique | API Géorisques `/v1/zonage_sismique` | live (rapport uniquement) |

Base API : `https://www.georisques.gouv.fr/api/v1` (documentation : georisques.gouv.fr/doc-api). Les noms exacts des couches WMS Géorisques/BRGM sont à figer en début de sprint 1 (tâche T-01, §11).

### 3.2 Risques technologiques — `#F08050`

| Couche | Source / flux | Mode |
|---|---|---|
| Installations classées (ICPE), avec attribut et filtre **Seveso** (seuil haut/bas) | API Géorisques `/v1/installations_classees` + WMS | live |
| Secteurs d'information sur les sols (SIS) | API Géorisques `/v1/sis` + WMS | live |
| Sites et sols pollués ou potentiellement pollués (CASIAS, ex-BASOL/BASIAS) | API Géorisques `/v1/casias` + WMS | live |
| PPRT | API Géorisques `/v1/gaspar/risques` + WMS | live |
| Plan d'exposition au bruit (PEB) | API Carto GPU (servitudes, catégorie PEB) | live |
| Canalisations de matières dangereuses | API Géorisques `/v1/canalisations` | live (rapport uniquement) |

### 3.3 Environnement & biodiversité — `#00A193`

| Couche | Source / flux | Mode |
|---|---|---|
| Natura 2000 (ZSC/SIC + ZPS, fusionnés en une couche à deux styles) | WFS PatriNat (`data.geopf.fr`, couches `patrinat_sic`, `patrinat_zps`) | batch semestriel |
| ZNIEFF type I et II | WFS PatriNat (`patrinat_znieff1`, `patrinat_znieff2`) | batch semestriel |
| Espaces protégés (APB, réserves, parcs, conservatoire du littoral…) | WFS PatriNat (`patrinat_pn`, `pnr`, `rnn`, `rnr`, `apb`…) | batch semestriel |
| Inventaire national du patrimoine géologique | WFS PatriNat (`patrinat_inpg`) | batch annuel |

Choix : batch plutôt que WMS INPN — disponibilité et latence des WMS externes non maîtrisées, volumes faibles, styles homogènes avec notre charte. Le rapport interroge PostGIS (intersections exactes), pas un service tiers.

Source d'acquisition : les archives `inpn.mnhn.fr/docs/Shape/*.zip` référencées par data.gouv.fr sont mortes (404, constaté le 16/07/2026). Le WFS PatriNat, également référencé sur data.gouv.fr, sert les mêmes zonages nationaux avec un schéma harmonisé (`id_mnhn`, `nom_site`, `url_fiche`) et s'automatise sans téléchargement manuel.

### 3.4 Urbanisme & foncier — `#55579E`

| Couche | Source / flux | Mode |
|---|---|---|
| Parcelles cadastrales | GeoJSON Etalab `https://cadastre.data.gouv.fr/data/etalab-cadastre/` → PMTiles ; interrogation ponctuelle via API Carto `GET /api/cadastre/parcelle` | batch (affichage) + live (fiche parcelle) |
| Zonage PLU (zones U/AU/A/N + libellés) | API Carto GPU `GET /api/gpu/zone-urba?geom=…` | live |
| Prescriptions (surfaciques, linéaires, ponctuelles) | API Carto GPU `/api/gpu/prescription-{surf,lin,pct}` | live |
| Servitudes d'utilité publique | API Carto GPU `/api/gpu/assiette-sup-s` (et -l, -p) | live |
| Lien vers le règlement écrit officiel de la zone | Métadonnées du document GPU (URL du PDF) | live |

Base API Carto : `https://apicarto.ign.fr`. Comportement au clic sur une parcelle : fiche latérale avec référence cadastrale, surface, zone(s) PLU intersectée(s), prescriptions, servitudes, lien règlement PDF, et raccourci « analyser autour de cette parcelle » (pré-remplit point + rayons).

Communes au RNU ou non versées au GPU : l'outil l'affiche explicitement (« document non disponible au GPU — vérifier en mairie ») ; jamais de silence.

### 3.5 Marché — transactions (DVF enrichi) — `#00749D`

| Élément | Source / flux | Mode |
|---|---|---|
| Mutations et locaux DVF géolocalisés (5 dernières années glissantes + historique complet en base) | `https://files.data.gouv.fr/geo-dvf/latest/csv/` (Etalab) | batch semestriel (publication avril/octobre) |
| DPE logements + tertiaire | data.ademe.fr, jeux « DPE v2 » logements existants/neufs + tertiaire | batch trimestriel |
| BDNB (Base de données nationale des bâtiments, CSTB) — sous-ensemble : identifiants bâtiment/parcelle, usage principal, année de construction, surfaces | data.gouv.fr, jeu « Base de données nationale des bâtiments » | batch semestriel |
| SIRENE géolocalisé (établissements actifs, code NAF) | `https://files.data.gouv.fr/geo-sirene/` (dernier millésime) | batch mensuel |

Affichage carte : **choroplèthe du prix médian au m²** (rampe séquentielle violette, 5 classes), maille adaptée au zoom — département (≤ z8), commune/arrondissement (z9-11), section cadastrale (z12-13), parcelle (≥ z14) — avec infobulle (prix médian, nb de ventes) et légende ; rien n'est dessiné là où aucune vente avec prix n'est connue. Contours : cadastre Etalab (`ingest contours`), seules les parcelles vendues sont conservées. Évolution possible : points de transaction individuels filtrables (période, typologie §5, surface, DPE, nature de mutation) une fois `GET /dvf/transactions` livré.

### 3.6 Bâti & occupants — `#8A5599` (partiel en lot 1)

La BDNB étant importée pour l'enrichissement DVF, on expose sans coût supplémentaire une couche « typologie du bâti » (usage principal par bâtiment) et l'attribut année de construction. Résidences spécialisées, occupants INPI/greffe : lot 2.

---

## 4. Front — expérience utilisateur

### Stack

React 18 + TypeScript + Vite. Carte : **MapLibre GL JS** ; dessin : **Terra Draw** ; tuiles : protocole **PMTiles** (fichiers statiques). Fond de carte : plan vectoriel OSM (OpenFreeMap) par défaut, orthophotos IGN (flux WMTS open) en second fond. Pas de framework UI lourd : composants maison + tokens de la charte (§2).

### Écran unique (pas de navigation multi-pages en lot 1)

```
┌────────────┬──────────────────────────────┬─────────────┐
│ Panneau    │                              │ Panneau     │
│ COUCHES    │           CARTE              │ ANALYSE     │
│ (thèmes    │   (MapLibre, plein écran)    │ (résultats  │
│ dépliables,│                              │ de zone,    │
│ légendes,  │  [outils dessin] [recherche  │ filtres DVF,│
│ opacité,   │   adresse/commune (BAN)]     │ boutons     │
│ millésime) │                              │ rapport &   │
│            │                              │ export)     │
└────────────┴──────────────────────────────┴─────────────┘
```

### Sélection de zone

- **Polygone** : tracé libre Terra Draw, éditable (sommets déplaçables).
- **Point + 2 rayons** : clic ou adresse BAN → saisie petit rayon (zone d'étude) et grand rayon (contexte/comparables), en mètres. Le petit rayon délimite l'analyse réglementaire et risques ; le grand rayon délimite la recherche de comparables DVF. Pour un polygone, un buffer optionnel joue le rôle du grand rayon.
- Zones **privées, sans compte** : sauvegarde en `localStorage` (nom + géométrie + thèmes cochés) + export/import GeoJSON pour partage manuel entre experts.

### Comportement d'analyse

Bouton « Analyser la zone » → `POST /zones/analyze` → le panneau droit affiche, thème par thème (thèmes cochés uniquement) : indicateurs synthétiques, tableaux dépliables, et signale les données non disponibles (ex. commune absente du GPU). Depuis ce panneau : « Générer le rapport » et « Exporter les transactions (Excel) ».

### Recherche

Barre adresse/commune via la Base Adresse Nationale (`https://api-adresse.data.gouv.fr/search`), recentrage carte.

---

## 5. Enrichissement typologie tertiaire des transactions DVF (exigence phase 1)

**Problème** : DVF `type_local` ∈ {Maison, Appartement, Dépendance, Local industriel et commercial ou assimilé} — insuffisant pour distinguer bureaux / commerce / industriel / agricole.

**Chaîne d'enrichissement** (à l'import, ordre de priorité décroissante) :

1. **Résidentiel** : `type_local` Maison/Appartement → `residentiel` (confiance `haute`).
2. **BDNB** : jointure transaction → parcelle(s) → bâtiment(s) BDNB → `usage principal` (bureaux, commerce, industrie, agricole, enseignement, santé…) → mappé sur notre nomenclature (confiance `haute` si un seul bâtiment/usage sur la parcelle, `moyenne` si usages mixtes).
3. **SIRENE** : établissements actifs géolocalisés à l'adresse/parcelle au moment de la mutation ; code NAF dominant → typologie (confiance `moyenne`).
4. **Heuristiques DVF** : nature de culture des parcelles (agricole), surface et libellés (confiance `basse`).
5. Sinon : `tertiaire_non_qualifie` (confiance `nulle`), toujours affiché comme tel — jamais reclassé arbitrairement.

**Nomenclature cible** : `residentiel`, `bureaux`, `commerce`, `industriel`, `agricole`, `autre`, `tertiaire_non_qualifie`.

Chaque transaction porte `typologie`, `typologie_source` (dvf/bdnb/sirene/heuristique) et `typologie_confiance` — les trois colonnes figurent dans l'export Excel et la méthodologie est rappelée dans la page de traçabilité du rapport. Objectif de qualité mesuré à l'import : < 15 % de `tertiaire_non_qualifie` sur les locaux non résidentiels (indicateur suivi à chaque millésime).

---

## 6. Schéma de données (PostGIS)

Base PostgreSQL 16 + PostGIS 3.4. SRID de stockage : 2154 (Lambert-93, calculs métriques exacts) ; échanges API en WGS84.

```
-- Référentiel et traçabilité
sources(id, code, libelle, url_source, licence, millesime, date_import, checksum)

-- Marché
dvf_mutations(id_mutation PK, date_mutation, nature_mutation, valeur_fonciere,
              code_commune, geom Point)
dvf_locaux(id PK, id_mutation FK, type_local_dvf, surface_reelle_bati, surface_terrain,
           nb_pieces, id_parcelle, typologie, typologie_source, typologie_confiance,
           annee_construction, dpe_classe, dpe_id, prix_m2 GENERATED)
dpe(id PK, numero_dpe, classe_conso, classe_ges, date_etablissement, surface,
    annee_construction, id_batiment_bdnb, adresse_ban_id, geom Point)

-- Bâti
bdnb_batiments(id_batiment PK, usage_principal, annee_construction, surface_plancher_est,
               ids_parcelles text[], geom MultiPolygon)

-- Occupants (support d'enrichissement en lot 1)
sirene_etablissements(siret PK, denomination, naf, date_debut, etat, adresse_ban_id, geom Point)

-- Environnement (une table par famille, schéma commun)
env_zonages(id PK, famille /* natura2000|znieff1|znieff2|espace_protege|patrimoine_geol */,
            code_national, libelle, url_fiche_inpn, geom MultiPolygon,
            geom_gen MultiPolygon /* généralisée ~50 m, affichage carte only */,
            surface_m2 /* précalculée : filtre de lisibilité des tuiles */)

-- Carte des prix (affichage uniquement ; l'analyse recalcule toujours sur dvf_locaux)
contours(id PK, niveau /* parcelle|section|commune|departement */, code, libelle,
         geom MultiPolygon /* cadastre Etalab ; parcelles limitées à celles vendues */)
dvf_prix(id PK, niveau, code, libelle, nb_ventes,
         prix_m2_median /* même définition que le thème Marché */, geom MultiPolygon)
```

Index : GIST sur toutes les `geom` ; B-tree sur `code_commune`, `date_mutation`, `typologie`. Chaque table batch référence `sources.id` du millésime courant ; les imports sont **remplaçants** (nouvelle table, bascule par renommage) pour ne jamais servir un état partiel.

---

## 7. Contrats d'API (backend FastAPI)

Toutes les géométries en GeoJSON WGS84. Pas d'authentification en lot 1 (réseau interne) ; l'API est néanmoins structurée pour accueillir un middleware d'auth au lot 2.

### `GET /layers`
Catalogue des couches : id, thème, libellé, mode (live/batch), style, millésime, source — le front construit le panneau Couches à partir de cette réponse (ajout d'une couche = configuration, pas de code front).

### `GET /tiles/env/{familles}/{z}/{x}/{y}.pbf`
Tuiles vectorielles (MVT) des zonages INPN, servies depuis PostGIS (§3). `familles` = liste séparée par des virgules (ex. `znieff1,znieff2`) ; couche MVT `zonages`, attributs `famille`, `code_national`, `libelle`, `url_fiche_inpn`. Tuile sans zonage → `204` (et non `404` : l'absence de donnée est un résultat normal). Famille inconnue → `404`.

### `GET /tiles/dvf/{z}/{x}/{y}.pbf`
Tuiles vectorielles de la carte des prix : couche MVT `prix`, attributs `niveau`, `code`, `libelle`, `nb_ventes`, `prix_m2` (médiane, même définition que le thème Marché). Le niveau d'agrégation dépend du zoom demandé : `departement` (z ≤ 8), `commune` (9-11), `section` (12-13), `parcelle` (≥ 14). Les mailles sont précalculées dans `dvf_prix` par `ingest contours` et rafraîchies par chaque `ingest dvf`. Tuile sans vente → `204`.

### `POST /zones/analyze`
```json
{
  "zone": {"type": "polygon", "geometry": {…}}          // ou
  "zone": {"type": "point_radii", "center": [lon, lat],
           "small_radius_m": 500, "large_radius_m": 2000},
  "themes": ["risques_naturels", "risques_technologiques",
             "environnement", "urbanisme", "marche_ventes"]
}
```
Réponse : un objet par thème avec `indicateurs` (agrégats), `items` (listes détaillées), `avertissements` (données indisponibles), `sources` (millésimes). Le serveur orchestre en parallèle les appels Géorisques/GPU (live) et les requêtes PostGIS (batch). Timeout par source : 15 s ; une source en échec = avertissement explicite, jamais un blocage.

### `POST /reports` → `202 {"job_id"}` ; `GET /reports/{job_id}`
Corps = celui d'`analyze` + `client_ref`, `titre`, `auteur` (texte libre, repris en page de garde). `GET` renvoie `{"status": "pending|running|done|error", "download_url"?}`. Le PDF est servi depuis un répertoire temporaire **purgé après 24 h** (pas de stockage pérenne — décision du 15/07/2026).

### `GET /dvf/transactions` et `GET /dvf/export.xlsx`
Paramètres : `zone` (ou bbox), `date_min/max`, `typologies[]`, `surface_min/max`, `prix_m2_min/max`, `dpe[]`, `annee_construction_min/max`, `nature_mutation[]`. Le JSON est paginé ; l'Excel contient une feuille « Synthèse » (agrégats, filtres appliqués, millésime) et une feuille « Transactions » (toutes colonnes, dont les 3 colonnes de typologie enrichie).

### `GET /parcelles/lookup?lon=&lat=`
Proxy API Carto : parcelle + zonage PLU + prescriptions + servitudes + URL du règlement (une seule requête pour la fiche parcelle du front).

---

## 8. Rapport PDF

### Chaîne de génération

Job asynchrone (worker dédié) : ① exécution de l'analyse (mêmes fonctions que `/zones/analyze`) → ② rendu des cartes statiques : instance Playwright/Chromium headless chargeant l'appli carto en mode « rendu » (`/?rendu=1&couches=…&zone=…` : zone + couches du thème + légende + échelle, signal `#rendu-pret` quand les tuiles sont chargées), une capture PNG par section — le rendu papier est ainsi strictement identique au rendu écran → ③ gabarit HTML/Jinja2 + **WeasyPrint** → PDF paginé A4 portrait (cartes en pleine largeur, paysage pour l'annexe transactions). Objectif : < 3 min par rapport ; 2 jobs concurrents suffisent pour 100 rapports/mois. Les couches affichées sur la carte de chaque section sont configurées par thème dans le catalogue (`couches_rapport`) — sous-ensemble volontairement lisible, l'expert garde toutes les couches à l'écran. La file des jobs est la table `report_jobs` (PostGIS), consommée avec `FOR UPDATE SKIP LOCKED`.

### Structure du document

1. **Page de garde** : titre, référence dossier client, auteur, date/heure de génération, carte de situation, définition exacte de la zone (type, centre/rayons ou WKT du polygone, surface).
2. **Sommaire** paginé.
3. **Synthèse en une page** : tableau de bord des points d'attention par thème (code couleur charte : rouge `#DB4B4B` = point de vigilance, teal `#00A193` = conforme/sans objet), pour lecture rapide par le client final.
4. **Une section par thème coché** : carte statique + indicateurs + tableau détaillé + note méthodologique courte. Les rubriques sans donnée affichent la raison (« commune non couverte par le GPU »), jamais un blanc.
5. **Annexes** : liste complète des transactions DVF (référence croisée avec l'Excel joint), liste des ICPE/SIS avec identifiants Géorisques.
6. **Page de traçabilité** (piste d'audit) : pour chaque donnée utilisée — source, URL, licence, millésime ou date/heure de l'appel API, version de l'application, et méthodologie d'enrichissement typologique (§5). 

Pas de signature ni verrouillage du PDF ; pas d'archivage serveur (décisions du 15/07/2026).

---

## 9. Pipeline batch

Orchestration lot 1 : scripts Python autonomes (un par source, CLI commune `ingest <source>`) + planification cron ; journalisation structurée + alerte mail en échec. Dagster/Airflow seulement si le nombre de sources dépasse ~15 (lot 2+).

Chemin type : téléchargement (stockage brut daté sur disque) → contrôles (schéma, volumétrie vs millésime précédent ±20 %) → transformation (GDAL/ogr2ogr, pandas/pyarrow) → chargement PostGIS (table shadow puis bascule) → génération PMTiles (**tippecanoe**) → mise à jour de `sources` → invalidation du cache front.

| Source | Fréquence | Déclencheur |
|---|---|---|
| DVF géolocalisé | semestrielle | publications Etalab (avril, octobre) |
| DPE ADEME | trimestrielle | cron |
| BDNB | semestrielle | suivi manuel des releases CSTB |
| SIRENE géolocalisé | mensuelle | cron |
| INPN (5 familles) | semestrielle | cron (`ingest inpn --famille …`, WFS PatriNat) |
| Contours cadastre Etalab (carte des prix) | trimestrielle | cron (`ingest contours --dept …`) |

L'enrichissement typologique (§5) est un job dépendant, relancé après tout import DVF, BDNB ou SIRENE.

---

## 10. Infrastructure

Une VM (interne ou OVH/Scaleway — données souveraines) : 8 vCPU, 32 Go RAM, 500 Go SSD (PostGIS ~150 Go avec DVF national historique + BDNB sous-ensemble + SIRENE ; marge ×2).

Docker Compose, 5 services : `caddy` (reverse proxy + fichiers statiques front et PMTiles, avec support des requêtes Range requis par PMTiles), `api` (FastAPI), `worker` (rapports, Playwright + WeasyPrint), `postgis`, `ingest` (conteneur outillé lancé par cron). Sauvegarde : dump PostGIS quotidien + copie des PMTiles ; les données étant toutes reconstructibles depuis l'open data, la sauvegarde sert au délai de reprise, pas à la pérennité.

---

## 11. Points à valider en début de sprint 1

| # | Tâche | Risque couvert |
|---|---|---|
| T-01 | Figer les noms exacts des couches WMS Géorisques et des endpoints API v1 utilisés (l'API évolue régulièrement) | contrat d'interface |
| T-02 | POC jointure DVF↔BDNB↔SIRENE sur 2 départements contrastés (ex. 69 et 24) et mesure du taux de `tertiaire_non_qualifie` | exigence typologie tertiaire |
| T-03 | Vérifier la disponibilité et le format du dernier millésime BDNB en libre accès (certaines colonnes sont en accès restreint) | périmètre BDNB |
| T-04 | Tester la tenue de l'API Carto GPU sur des zones larges (pagination, limites de géométrie en paramètre) | rapport sur grandes zones |
| T-05 | Valider les gradations de couleurs par thème (contraste, daltonisme) sur les fonds plan et ortho | charte / lisibilité |

---

## Annexe A — Récapitulatif des URLs sources

| Source | URL |
|---|---|
| API Géorisques | `https://www.georisques.gouv.fr/api/v1` (doc : `/doc-api`) |
| API Carto (GPU + cadastre) | `https://apicarto.ign.fr` |
| Cadastre Etalab | `https://cadastre.data.gouv.fr/data/etalab-cadastre/` |
| DVF géolocalisé | `https://files.data.gouv.fr/geo-dvf/latest/csv/` |
| DPE ADEME | `https://data.ademe.fr` (jeux DPE v2) |
| BDNB | `https://www.data.gouv.fr/fr/datasets/base-de-donnees-nationale-des-batiments/` |
| SIRENE géolocalisé | `https://files.data.gouv.fr/geo-sirene/` |
| Zonages INPN | WFS PatriNat `https://data.geopf.fr/wfs/ows` (couches `patrinat_*`) ; fiches : `https://inpn.mnhn.fr` |
| Base Adresse Nationale | `https://api-adresse.data.gouv.fr` |
| Fond de plan vectoriel | OpenFreeMap / Protomaps (OSM) ; orthophotos : WMTS IGN open |
