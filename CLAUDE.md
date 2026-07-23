# azgbis — instructions projet

Outil interne de qualification de zone pour ~10 experts immobiliers. 100 % open data.
Tout est en **français** : code (identifiants métier), commentaires, docs, UI, commits.
Spécification de référence : [docs/specification-lot1.md](docs/specification-lot1.md) ;
feuille de route données : [docs/enrichissements-prevus.md](docs/enrichissements-prevus.md).
Pour ajouter une source de données, utiliser le skill `/add-new-data`.

## Carte du dépôt

- `backend/app/` — API FastAPI : `catalog.py` (catalogue des couches, consommé tel quel
  par le front), `tiles.py` (MVT depuis PostGIS : env, dvf, classes), `analysis.py` +
  `analyze/` (un module par thème), `reports/` (file report_jobs → worker : Playwright
  capture le front en « mode rendu », WeasyPrint compose le PDF), `dvf_export.py` (Excel).
- `frontend/src/` — React + MapLibre : `App.tsx` (état global, mode rendu `?rendu=1`),
  `MapView.tsx` (couches, choroplèthes, légendes), `components/`, `theme.css`
  (**source de vérité des couleurs de la charte**).
- `pipeline/` — `schema.sql` + `ingest/` (CLI `python -m ingest <source>`), un module
  par source. `worker/` et `Dockerfile` racine : contextes de build (voir pièges).
- `deploy/` — Caddyfile interne ; `Caddyfile.vps` + `docker-compose.vps.yml` pour le
  VPS public (HTTPS + basic auth) ; guide : docs/deploiement-vps.md.
- `tools/qa/` — recette navigateur Playwright (s'exécute DANS le conteneur worker).
- `backend/tests/` — tests unitaires sans base ni réseau (`pytest`).

## Commandes

```powershell
podman machine start ; podman compose up -d        # pile locale (4 conteneurs)
podman compose --profile tools run --rm ingest …   # imports (README pour la liste)
cd frontend ; npm run build                        # typecheck + build (obligatoire avant livraison)
cd backend ; .\.venv\Scripts\python.exe -m pytest  # tests unitaires
# recette navigateur : voir tools/qa/README.md
```

## Conventions non négociables

- Géométries **2154** en base (calculs métriques), GeoJSON **WGS84** dans l'API.
- Import batch = **remplaçant, en une transaction**, avec `register_source()` (table
  `sources` = traçabilité du rapport et fraîcheur affichée). Téléchargements bruts
  conservés dans `pipeline/raw/` (idempotents).
- Tuile sans donnée → **204** (jamais 404). Nouvelle couche WMS : `flux_confirme: True`
  seulement après un GetMap réel vérifié sur un secteur où la donnée existe.
- L'analyse et le rapport recalculent depuis les tables sources (`dvf_locaux`…) ;
  `dvf_prix`/`carto_classes` ne servent **que** l'affichage carte.
- `backend/app/reports/libelles.py` doit rester synchrone avec les libellés
  d'`AnalysisPanel.tsx` (rapport = écran).
- Couleurs : uniquement celles de la charte (`theme.css`, `THEME_COLORS` de
  `catalog.py`). Rampes carte validées par le skill dataviz.
- Secrets dans `.env` (jamais commité) ; défauts de dev inchangés (`azgbis`).
- RGPD : jamais de propriétaires personnes physiques. Rapports PDF purgés à 24 h.

## Pièges connus (tous constatés, ne pas re-découvrir)

- **podman-compose** ignore `build.dockerfile` (d'où les contextes dédiés `worker/` et
  `Dockerfile` racine) et **ne recrée pas les conteneurs après un build** :
  `podman compose build X` puis `podman rm -f azgbis_worker_1 azgbis_web_1 azgbis_api_1`
  puis `podman compose up -d` (l'ordre importe : worker dépend d'api/web).
- `git push` échoue (proxy SSL du poste) → `git -c http.sslBackend=schannel push`.
- Recette navigateur : **Playwright dans le conteneur worker** (`podman cp` le script,
  `podman exec azgbis_worker_1 python …`), cible `http://web:80`. Pas de navigateur hôte.
- Après un reboot/redémarrage de la machine podman : si `http://localhost` répond à
  vide alors que les conteneurs sont Up, c'est un `wslrelay` orphelin → `podman machine
  stop ; wsl --shutdown ; podman machine start ; podman compose up -d`.
- Ne pas lancer `up --force-recreate` pendant un `ingest` : recréer postgis tue l'import.
- Playwright `wait_for_selector` sur `#rendu-pret` : `state="attached"` (div invisible).
- Jinja : ne jamais nommer une clé de dict `items` (collision avec `dict.items`).
- WeasyPrint : `break-before: page` (pas `page-break-before`).
- En production VPS, le worker capture via l'écoute interne `http://web:8080` **sans**
  basic auth (non publiée) — ne jamais publier ce port ni le protéger.

## Production

`https://azgbis.baillylab.fr` (VPS OVH ~40 Go tout compris, Docker + Caddy, basic
auth partagé — temporairement désactivé depuis le 22/07/2026). Mise à jour, toujours
la séquence complète (l'image ingest est derrière le profil `tools`, `up --build`
ne la reconstruit pas) :
`git pull`, `docker compose -f docker-compose.yml -f docker-compose.vps.yml up -d --build`,
`docker compose --profile tools build ingest`, `… run --rm ingest schema`.
Je n'ai pas d'accès SSH au VPS : donner à l'utilisateur les commandes à exécuter.
