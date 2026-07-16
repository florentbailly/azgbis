# Qualification de zone — lot 1

Outil interne de qualification d'une zone géographique (France) pour experts immobiliers :
carte open data en navigation libre + analyse de zone + (à venir) rapport PDF de piste d'audit.
Spécification : [docs/specification-lot1.md](docs/specification-lot1.md).

## Développement (Windows, sans conteneur pour le front/back)

```powershell
# Backend (terminal 1) — DATABASE_URL optionnel, requis pour les thèmes Environnement/Marché
# (port 5433 : un PostgreSQL natif occupe déjà 5432 sur ce poste)
$env:DATABASE_URL = "postgresql://azgbis:azgbis@localhost:5433/azgbis"
cd backend ; .\.venv\Scripts\uvicorn.exe app.main:app --port 8000

# Frontend (terminal 2)
cd frontend ; npm run dev        # → http://localhost:5173

# Base PostGIS locale via Podman (terminal 3, une fois)
podman run -d --name azgbis-pg -e POSTGRES_USER=azgbis -e POSTGRES_PASSWORD=azgbis `
  -e POSTGRES_DB=azgbis -p 5433:5432 docker.io/postgis/postgis:16-3.4
```

Pipeline de données (DVF, INPN…) : voir [pipeline/README.md](pipeline/README.md).

## Déploiement sur VM Linux (Podman)

```bash
git clone <repo> && cd azgbis
podman compose up -d --build              # postgis + api + web (port 80)
podman compose run --rm ingest schema     # créer les tables
podman compose run --rm ingest dvf --dept 69 --years 2021-2025
podman compose run --rm ingest status
```

- Le front est servi par Caddy ([deploy/Caddyfile](deploy/Caddyfile)) qui fait aussi
  reverse proxy `/api` → backend et sert `/tiles` (PMTiles du pipeline).
- HTTPS : remplacer `:80` par le nom de domaine dans le Caddyfile et publier `443:443`.
- `podman compose` nécessite `podman-compose` (`pip install podman-compose` ou paquet distro).
- Mot de passe base : changer `azgbis` dans docker-compose.yml pour la production.
