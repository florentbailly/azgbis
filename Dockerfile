# Image "web" : build du front puis service via Caddy (contexte de build : racine du dépôt).
# Ce fichier vit à la racine car podman-compose exige le Dockerfile au niveau du contexte.
FROM docker.io/node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM docker.io/caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv/www
