# Pipeline batch — lot 1

Alimente PostGIS avec les données non appelées en live : DVF, zonages INPN
(puis BDNB, SIRENE, DPE — POC T-02 à venir). Sans ces imports, les thèmes
« Environnement » et « Marché » de l'analyse affichent « source non chargée ».

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
.\.venv\Scripts\python -m ingest status                          # vérifier
```

INPN (auto-téléchargé depuis le WFS PatriNat de la Géoplateforme) :
```powershell
.\.venv\Scripts\python -m ingest inpn --famille natura2000      # SIC (Habitats) + ZPS (Oiseaux)
.\.venv\Scripts\python -m ingest inpn --famille znieff1
.\.venv\Scripts\python -m ingest inpn --famille znieff2
.\.venv\Scripts\python -m ingest inpn --famille espace_protege  # parcs, réserves, APB, littoral…
.\.venv\Scripts\python -m ingest inpn --famille patrimoine_geol
```
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

- `ingest enrich` : POC T-02 — appariement BDNB + SIRENE pour la typologie tertiaire
  (l'import DVF pose déjà les colonnes typologie/source/confiance ; niveau « dvf » seul).
- `ingest dpe`, `ingest bdnb`, `ingest sirene`.
- `ingest tiles` : génération PMTiles (tippecanoe) pour les **gros volumes figés** — points DVF
  et cadastre. Les zonages INPN, eux, sont servis en tuiles vectorielles directement depuis
  PostGIS (`GET /api/tiles/env/...`) : rien à générer, et la carte ne peut pas diverger de
  l'analyse. Tant que ces PMTiles n'existent pas, la couche « Transactions DVF » de la carte
  reste marquée « flux à confirmer » et n'affiche rien (l'analyse DVF, elle, fonctionne).
