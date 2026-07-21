# Recette navigateur (Playwright)

Les scripts s'exécutent **dans le conteneur worker** (seul environnement du projet
avec Chromium ; il voit le front via `http://web:80`). Pas de navigateur sur l'hôte.

## Lancer la recette générale (pile locale)

```powershell
podman cp tools\qa\recette_generale.py azgbis_worker_1:/tmp/recette.py
podman exec azgbis_worker_1 python /tmp/recette.py
# captures : podman cp azgbis_worker_1:/tmp/qa/. .\qa-captures\
```

Sortie : JSON des contrôles + liste `echecs` (code retour 1 si non vide).
Prérequis données : imports du README effectués (dept 69 + admin + radon), sinon les
contrôles fraîcheur/prix/radon échouent normalement.

## Viser la préprod (azgbis.baillylab.fr)

```powershell
podman exec -e BASE=https://azgbis.baillylab.fr -e QA_AUTH_USER=azgbis `
  -e QA_AUTH_PASS=LeMotDePasse azgbis_worker_1 python /tmp/recette.py
```

## Écrire un nouveau contrôle

Compléter `recette_generale.py` (et son dict `ATTENDUS`) plutôt que créer un script
jetable : la recette doit rester rejouable en une commande. Points d'attention appris :
- `wait_for_selector("#rendu-pret", state="attached")` — le marqueur est invisible ;
- une capture d'écran après `wait_for_load_state("networkidle")` + petite marge ;
- les clics carte se font en coordonnées écran (`page.mouse.click(x, y)`).
