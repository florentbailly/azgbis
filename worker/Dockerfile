# Worker de rapports PDF (spec §8 et §10) : Playwright/Chromium pour les cartes
# statiques + WeasyPrint pour le PDF.
#
# Ce Dockerfile ne contient QUE les dépendances : le code backend (backend/app) est
# monté en volume par docker-compose — le worker exécute ainsi exactement le même
# code d'analyse que l'API, sans copie. (podman-compose sous Windows ignore la clé
# `build.dockerfile`, d'où ce contexte séparé — même contrainte que le Dockerfile racine.)
FROM docker.io/python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chromium et ses dépendances système (gérées par Playwright), puis les bibliothèques
# de rendu de WeasyPrint et une police complète pour le PDF.
RUN python -m playwright install --with-deps chromium \
 && apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangocairo-1.0-0 fonts-dejavu \
 && rm -rf /var/lib/apt/lists/*

CMD ["python", "-m", "app.reports.worker"]
