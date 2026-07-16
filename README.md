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

## Tester en local avec Podman (pas à pas)

Rappel des concepts : une **image** est un modèle figé (construite depuis un Dockerfile) ;
un **conteneur** est une instance en cours d'exécution d'une image ; un **volume** stocke
les données qui doivent survivre aux conteneurs (ici `azgbis_pgdata` contient la base).
Chaque conteneur est isolé : `localhost` y désigne le conteneur lui-même.

L'application est composée de 3 conteneurs qui doivent se parler : `postgis` (base),
`api` (backend, qui joint la base via le nom d'hôte `postgis`) et `web` (Caddy : front +
reverse proxy `/api`). Ce nom d'hôte n'existe que sur le réseau créé par `podman compose`
(`azgbis_default`). **Ne pas lancer les conteneurs un par un avec `podman run`** : sans
réseau commun, l'API ne résout pas `postgis` et la connexion base échoue (le back et le
front démarrent quand même, seuls les thèmes lisant la base tombent en avertissement).

```powershell
podman machine start          # après un reboot (Podman tourne dans une VM Linux)
podman compose up -d          # démarre les 3 conteneurs sur le même réseau
                              #   ajouter --build seulement si le code a changé
podman ps                     # attendu : 3 conteneurs Up, postgis "(healthy)"
podman logs azgbis_api_1      # journaux d'un conteneur en cas de problème
# tester : http://localhost
podman compose down           # arrêt propre (les volumes, donc les données, restent)
```

Les conteneurs ne redémarrent pas seuls après un reboot du poste : relancer
`podman machine start` puis `podman compose up -d`.

**Persistance** : les données importées (DVF, INPN…) vivent dans le volume `azgbis_pgdata`,
pas dans le conteneur. Elles survivent donc à un `podman compose down`, à la reconstruction
des images et au redémarrage du poste — inutile de réimporter. Seul `podman compose down -v`
(ou `podman volume rm azgbis_pgdata`) les détruit : c'est le `-v` qui efface, ne l'utilisez
que pour repartir de zéro volontairement.

Les volumes sont **locaux à la machine** : la VM aura les siens, vides au départ. Il faudra
donc y rejouer les imports (`ingest schema` puis `ingest dvf` / `ingest inpn`), ou bien
transférer la base existante :
```powershell
podman exec azgbis_postgis_1 pg_dump -U azgbis -Fc azgbis > azgbis.dump   # sur le poste
# puis sur la VM, une fois la pile démarrée :
#   podman exec -i azgbis_postgis_1 pg_restore -U azgbis -d azgbis --clean < azgbis.dump
```
Rejouer les imports est généralement préférable : c'est reproductible et ça récupère les
millésimes à jour. Le dump sert surtout à éviter de retélécharger de gros volumes.

## Déploiement sur VM Linux (Podman)

```bash
git clone <repo> && cd azgbis
podman compose up -d --build                              # postgis + api + web (port 80)
podman compose --profile tools run --rm ingest schema     # créer les tables
podman compose --profile tools run --rm ingest dvf --dept 69 --years 2021-2025
podman compose --profile tools run --rm ingest inpn --famille znieff1        # ~17 000 zonages
podman compose --profile tools run --rm ingest inpn --famille znieff2
podman compose --profile tools run --rm ingest inpn --famille natura2000     # SIC + ZPS
podman compose --profile tools run --rm ingest inpn --famille espace_protege
podman compose --profile tools run --rm ingest inpn --famille patrimoine_geol
podman compose --profile tools run --rm ingest status
```

- La VM part avec des volumes vides : les imports ci-dessus sont à rejouer (un
  département DVF par territoire couvert ; les zonages INPN sont nationaux, une fois
  suffit). Voir [pipeline/README.md](pipeline/README.md).

- Le front est servi par Caddy ([deploy/Caddyfile](deploy/Caddyfile)) qui fait aussi
  reverse proxy `/api` → backend et sert `/tiles` (PMTiles du pipeline). Son image se
  construit depuis le [Dockerfile](Dockerfile) racine (contrainte podman-compose).
- HTTPS : remplacer `:80` par le nom de domaine dans le Caddyfile et publier `443:443`.
- `podman compose` nécessite `podman-compose` (`pip install podman-compose` ou paquet distro)
  et que son exécutable soit dans le PATH.
- Mot de passe base : changer `azgbis` dans docker-compose.yml pour la production.
