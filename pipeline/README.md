# Pipeline batch — lot 1

Alimente PostGIS avec les données non appelées en live : DVF, zonages INPN,
contours administratifs, radon, bâtiments BD TOPO, établissements SIRENE (puis
DPE). Sans ces imports, les thèmes « Environnement » et « Marché » de l'analyse
affichent « source non chargée ».

## Prérequis : une base PostGIS

Le poste de dev actuel n'a ni PostgreSQL ni Docker. Deux options :

**Option A — PostgreSQL local (Windows)**
1. Installer PostgreSQL 16 : https://www.enterprisedb.com/downloads/postgres-postgresql-downloads
2. Dans Stack Builder (lancé en fin d'installation), cocher **PostGIS** (Spatial Extensions).
3. Créer la base :
   ```powershell
   & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE USER azgbis PASSWORD 'azgbis'; CREATE DATABASE azgbis OWNER azgbis;"
   ```

**Option B — conteneur (Podman/Docker)** — c'est l'option utilisée sur ce poste :
```powershell
podman run -d --name azgbis-pg -e POSTGRES_USER=azgbis -e POSTGRES_PASSWORD=azgbis `
  -e POSTGRES_DB=azgbis -p 5433:5432 docker.io/postgis/postgis:16-3.4
```
⚠️ Sur ce poste, un PostgreSQL natif Windows occupe déjà le port 5432 : le conteneur
est donc publié sur **5433** et `DATABASE_URL` doit pointer sur `localhost:5433`.

## Lancer les imports

```powershell
cd c:\Users\flore\azgbis\pipeline
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
$env:DATABASE_URL = "postgresql://azgbis:azgbis@localhost:5433/azgbis"
# Si le poste est derrière un proxy d'inspection SSL : $env:SSL_NO_VERIFY = "1"

.\.venv\Scripts\python -m ingest schema                          # 1. tables
.\.venv\Scripts\python -m ingest dvf --dept 69 --years 2021-2025 # 2. DVF (auto-téléchargé ; « latest » = 5 dernières années)
.\.venv\Scripts\python -m ingest contours --dept 69              # 3. carte des prix (cadastre Etalab)
.\.venv\Scripts\python -m ingest status                          # vérifier
```

`ingest contours` alimente la couche carte « Prix au m² (ventes DVF) » : il télécharge
les contours cadastraux Etalab du département (communes, sections, et uniquement les
parcelles portant une vente), puis calcule dans `dvf_prix` le prix médian au m² par
maille — département, commune, section, parcelle — avec la même définition de médiane
que le thème Marché de l'analyse. À lancer **après** `ingest dvf` du département ;
les imports DVF suivants recalculent `dvf_prix` automatiquement.

INPN (auto-téléchargé depuis le WFS PatriNat de la Géoplateforme) :
```powershell
.\.venv\Scripts\python -m ingest inpn --famille natura2000      # SIC (Habitats) + ZPS (Oiseaux)
.\.venv\Scripts\python -m ingest inpn --famille znieff1
.\.venv\Scripts\python -m ingest inpn --famille znieff2
.\.venv\Scripts\python -m ingest inpn --famille espace_protege  # parcs, réserves, APB, littoral…
.\.venv\Scripts\python -m ingest inpn --famille patrimoine_geol
```
Enrichissement typologique des locaux DVF (spec §5, après `dvf` + `contours`) :
```powershell
.\.venv\Scripts\python -m ingest bati --dept 69   # bâtiments BD TOPO des parcelles vendues (7z ~0,7 Go, purgé après)
.\.venv\Scripts\python -m ingest sirene           # établissements actifs INSEE (parquet ~3 Go, tous dépts DVF)
.\.venv\Scripts\python -m ingest enrich           # croisement parcellaire → typologie (relançable)
```
`ingest enrich` affiche le taux de locaux d'activité restant « tertiaire_non_qualifie »
(objectif spec : < 15 %). À relancer après tout import `dvf`, `bati` ou `sirene`.
Sobriété disque : `bati` ne garde que les bâtiments intersectant une parcelle vendue
(~45 000 pour le Rhône au lieu de 910 000) et supprime archive et gpkg après import —
le relancer si un `contours` ultérieur ajoute des parcelles.

Les cinq familles sont nationales : un import suffit pour tout le territoire. Chaque import
calcule aussi les colonnes d'affichage `geom_gen` (contour généralisé à 50 m) et `surface_m2`,
utilisées par les tuiles carte — l'analyse, elle, lit toujours `geom` en pleine résolution.
Les jeux « INPN — Données du programme … » du MNHN sur data.gouv.fr ne sont que des liens
vers `inpn.mnhn.fr/docs/Shape/*.zip`, morts (404 constaté le 16/07/2026). data.gouv.fr
référence en revanche le **WFS PatriNat** (`data.geopf.fr/wfs/ows`), qui sert les mêmes
zonages nationaux avec un schéma harmonisé : c'est la source retenue, sans manipulation
manuelle. Import remplaçant (purge de la famille puis recharge), filtré sur la métropole
par défaut (`--territoire ALL` pour tout importer — le stockage est en Lambert-93, projection
métropole). `--file` reste possible pour réimporter un extract local hors ligne.

## Brancher le backend

```powershell
$env:DATABASE_URL = "postgresql://azgbis:azgbis@localhost:5433/azgbis"
cd ..\backend ; .\.venv\Scripts\uvicorn.exe app.main:app --port 8000
```
Les thèmes Environnement et Marché de « Analyser la zone » utilisent alors la base.

## Reste à faire (ordre spec §9)

- `ingest dpe` (ADEME) : classes DPE et année de construction à l'adresse.
- `ingest tiles` : génération PMTiles (tippecanoe), désormais réservée à d'éventuels
  **gros volumes figés** (fond cadastral complet, par exemple). Les zonages INPN
  (`/api/tiles/env/...`) comme la carte des prix DVF (`/api/tiles/dvf/...`) sont servis
  en tuiles vectorielles directement depuis PostGIS : rien à générer, et la carte ne
  peut pas diverger de l'analyse.
