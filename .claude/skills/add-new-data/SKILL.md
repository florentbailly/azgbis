---
name: add-new-data
description: Ajouter une source de données (couche carte, analyse, rapport) en suivant les conventions du projet — qualification live/batch, vérification des flux, ingest, tuiles, catalogue, recette.
---

# Ajouter une source de données à azgbis

Procédure complète, dans l'ordre. Chaque étape encode une leçon apprise sur ce projet :
ne pas en sauter. En cas de doute sur un choix structurant (live vs batch, intégration
à l'analyse), poser la question à l'utilisateur avant de coder.

## 1. Qualifier la source : live ou batch ?

**Live** (WMS/WMTS affiché tel quel, API interrogée par l'analyse) si : service public
stable (Géorisques, IGN, GPU), rendu acceptable à toutes les échelles utiles, pas de
jointure locale nécessaire. **Batch** (import PostGIS + tuiles maison) si : le service
est lent ou limité en échelle (ex. radon WMS : ~35 000 communes redessinées par tuile),
la donnée doit se joindre au DVF/cadastre, ou il faut des agrégations multi-niveaux.
Une même donnée peut être hybride : couche carte batch + analyse live (ex. radon).

## 2. Vérifier le flux AVANT d'écrire du code

Jamais de `flux_confirme: True` sur la foi de la documentation.

- **WMS** : télécharger le GetCapabilities ; noter `Min/MaxScaleDenominator` de la
  couche → convertir en zooms tuile (`échelle ≈ 559 082 264 / 2^z`) → `zoom_natif_min`
  (1:500 000 → 11 ; 1:100 000 → 13) et `zoom_natif_max`. Puis un **GetMap réel**
  EPSG:3857 256×256 sur un secteur où la donnée existe (attention : une bbox en mer ou
  hors emprise renvoie un PNG vide de ~116 octets qui ressemble à un succès).
  Rendu trop pâle sur OSM → `renforcement: True` + `opacite` (précédent : EAIP).
- **Fichier/API batch** : télécharger un échantillon, inspecter colonnes/valeurs,
  vérifier la licence (open data obligatoire), estimer la volumétrie et la RAM
  d'import (le VPS a 4 Go — préférer les variantes simplifiées, ex. contours 100 m).
- Sous Windows, `curl.exe` peut échouer (proxy SSL) : utiliser
  `Invoke-WebRequest -UseBasicParsing`.

## 3. Batch : schéma et ingest

- Table dans `pipeline/schema.sql` : geom `2154`, index GIST, `source_id REFERENCES
  sources(id)`, contrainte `UNIQUE` naturelle. Gros polygones affichés à petite
  échelle → colonne `geom_gen` généralisée à l'import + `surface_m2` précalculée
  (modèle : `env_zonages`).
- Module `pipeline/ingest/<source>.py` sur le modèle de `contours.py`/`radon.py` :
  import **remplaçant** (DELETE ciblé puis insert) **en une transaction**,
  `register_source()` systématique, `download()` (idempotent, brut conservé),
  affichage de compteurs. Sous-commande dans `ingest/__main__.py` + docstring.
- **Choix du tuilage** :
  - donnée « une classe par commune/département » → remplir `carto_classes`
    (contours : `admin_contours`, prérequis `ingest admin`) + une entrée dans
    `CLASSES_COUCHES` de `backend/app/tiles.py`. **Aucun code front** : le rendu,
    la légende et l'infobulle sont pilotés par le catalogue (`rendu: "classes"`,
    `classes: [{classe, couleur, libelle}]`, `note_legende`).
  - zonages polygonaux → endpoint MVT dédié sur le modèle `/tiles/env` (simplification
    à `tol = côté_tuile/4096`, filtre sub-pixel, 204 si vide).
  - agrégats continus multi-mailles → modèle `dvf_prix`/`/tiles/dvf`.

## 4. Entrée catalogue (`backend/app/catalog.py`)

Le front construit tout depuis le catalogue : panneau Couches, rendu, légendes.
Conventions : id court stable (il est dans les URLs et le localStorage des experts),
`libelle` métier, `attribution` avec l'organisme, couleurs de la charte uniquement
(rampes validées par le skill **dataviz** — luminosité monotone pour l'ordinal,
séparation daltonisme ≥ 8, distinctes des rampes existantes : violet = prix,
chaud = radon). `couches_rapport` d'un thème : avec parcimonie (lisibilité des cartes
PDF). Ajouter le libellé de la source dans `SOURCE_LABELS` (LayerPanel, fraîcheur).

## 5. Analyse et rapport (si la donnée alimente un thème)

- Analyzer dans `backend/app/analyze/` (fonction `analyze(zone, code_insee)` →
  `ThemeResult`), enregistré dans `ANALYZERS`. Toujours : dégradé propre sans base
  (`db.NO_DB_WARNING` en avertissement, jamais d'exception).
- Libellés : `AnalysisPanel.tsx` (LABELS/CATEGORY_LABELS) **et** son miroir
  `backend/app/reports/libelles.py` (le rapport doit dire la même chose que l'écran).
- Règle de synthèse dans `reports/synthese.py` (VIGILANCE/OK/INDISPONIBLE) et note
  méthodologique dans `NOTES_METHODO`.

## 6. Documentation

- `docs/specification-lot1.md` : §3 (couche et thème), §6 (tables), §7 (endpoints),
  §9 (ligne cron : fréquence + déclencheur).
- `README.md` (liste d'imports VM) et `docs/deploiement-vps.md` §8 (liste VPS).
- `docs/enrichissements-prevus.md` : retirer la donnée de la dette si elle y figurait.

## 7. Recette (obligatoire avant de livrer)

1. `pytest` (les tests du catalogue attrapent les entrées incohérentes) et
   `npm run build`.
2. Import local réel, `ingest status`, puis tuile/endpoint à la main
   (200 avec données, 204 à vide, 404 pour un id inconnu ; latence < 1 s).
3. Recette navigateur `tools/qa/` (voir son README) : couche visible, légende,
   infobulle, et si thème d'analyse : analyse + rapport PDF avec cartes.
4. Rebuild conteneurs : `podman compose build api` ne recrée PAS les conteneurs —
   `podman rm -f` worker/web/api puis `up -d` (voir CLAUDE.md, pièges).
