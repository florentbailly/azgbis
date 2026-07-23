# Déployer sur un VPS public (OVHcloud, Ubuntu) — pas à pas

Ce guide couvre l'installation initiale (§1-7, ~30 min de manipulations), les imports
de données (§8 : 1-2 h pour un département, 24-48 h pour la France métropolitaine),
la recette (§9) et la maintenance (§10). Il est écrit pour être suivi commande par
commande. Production actuelle : `https://azgbis.baillylab.fr` (VPS OVH,
IP 51.210.46.150).

**Ce qui sera en place à la fin** : l'application accessible en **HTTPS**, protégée
par un **mot de passe partagé** (l'outil n'a pas de comptes individuels avant le
lot 2 — sur un VPS public, sans cela, tout Internet y accéderait), les 4 conteneurs
relancés automatiquement au démarrage de la machine.

Prérequis : un VPS OVH Ubuntu (≥ 4 Go RAM ; disque : ≥ 20 Go libres pour un
département, ~40 Go tout compris pour la France métropolitaine — voir §8), son
adresse IP, et l'accès SSH fourni par OVH.

**Règle d'or à retenir pour toute la suite** : l'image d'import `ingest` est derrière
le profil Docker `tools`. `up -d --build` ne la reconstruit **jamais**. Après chaque
`git pull`, avant tout import :

```bash
docker compose --profile tools build ingest
docker compose --profile tools run --rm ingest schema   # idempotent, crée les tables manquantes
```

Symptôme typique de l'oubli : `ingest: error: argument cmd: invalid choice: 'xxx'`
(l'image en service ne connaît pas encore la nouvelle commande), ou une erreur
`relation … does not exist` (schéma pas à jour).

---

## 1. Sur votre poste : pousser l'état du code

Le VPS clonera GitHub : ce qui n'est pas commité/poussé n'existera pas pour lui.

```powershell
cd c:\Users\flore\azgbis
git status          # voir ce qui part
git add -A
git commit -m "description des changements"
git -c http.sslBackend=schannel push   # le -c contourne le proxy SSL du poste
```

## 2. Se connecter au VPS et le mettre à jour

```bash
ssh ubuntu@VOTRE_IP_VPS        # utilisateur "ubuntu" sur les images OVH récentes
sudo apt update && sudo apt -y upgrade
free -h                        # vérifier ≥ 4 Go de RAM
df -h /                        # vérifier ≥ 20 Go libres
```

`sudo` exécute une commande en administrateur ; `apt` est le gestionnaire de paquets
d'Ubuntu (équivalent d'un magasin d'applications en ligne de commande).

## 3. Installer Docker

Sur ce VPS on utilise **Docker** plutôt que Podman : même fichier compose, mais les
conteneurs marqués `restart: unless-stopped` redémarrent seuls après un reboot, sans
configuration supplémentaire.

```bash
sudo apt -y install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER   # autoriser votre utilisateur à parler à Docker
exit                            # puis se reconnecter en ssh pour activer ce droit
```

Après reconnexion, vérifier :

```bash
docker run --rm hello-world     # doit afficher "Hello from Docker!"
```

## 4. Pare-feu : ne laisser entrer que le nécessaire

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp           # redirection HTTP -> HTTPS
sudo ufw allow 443/tcp          # l'application (HTTPS)
sudo ufw enable                 # répondre "y"
sudo ufw status
```

Tout le reste est fermé. Le port interne 8080 (captures de cartes des rapports)
n'apparaît volontairement pas ici : il n'existe que sur le réseau Docker interne.

## 5. Récupérer le code

```bash
git clone https://github.com/florentbailly/azgbis.git
cd azgbis
```

## 6. Les secrets : fichier `.env`

Trois secrets vivent dans un fichier `.env` à côté du compose — jamais commité
(il est dans le `.gitignore`).

1. **Nom de domaine servi en HTTPS** (`SITE_ADDRESS`) : soit le nom OVH du VPS
   (`vps-a1b2c3d4.vps.ovh.net`, visible dans le manager ou via `hostname -f`), soit
   un domaine à vous — c'est le cas en production : `azgbis.baillylab.fr`, déclaré
   chez le registrar par un enregistrement DNS **A** pointant vers l'IP du VPS.
   Vérifier la résolution avant de continuer :
   ```bash
   nslookup azgbis.baillylab.fr    # doit répondre l'IP du VPS
   ```
2. **Mot de passe base de données** (interne aux conteneurs, mais un vrai secret) :
   ```bash
   openssl rand -base64 24      # copier le résultat
   ```
3. **Hash du mot de passe partagé** demandé par le navigateur (choisissez le mot de
   passe à communiquer aux experts, ex. généré aussi par openssl) :
   ```bash
   docker run --rm caddy:2-alpine caddy hash-password --plaintext 'LeMotDePasseDesExperts'
   ```
   Le résultat commence par `$2a$14$…` : c'est le hash, pas le mot de passe.

Créer le fichier :

```bash
nano .env
```

Contenu (adapter les 4 valeurs, coller le hash tel quel, sans guillemets) :

```
AZGBIS_DB_PASSWORD=le_resultat_de_openssl
SITE_ADDRESS=azgbis.baillylab.fr
BASIC_AUTH_USER=azgbis
BASIC_AUTH_HASH=$2a$14$le_hash_produit_par_caddy
```

Enregistrer : `Ctrl+O`, `Entrée`, puis `Ctrl+X`.

> **État temporaire (depuis le 22/07/2026)** : le mot de passe partagé est
> **désactivé** — le bloc `basic_auth` est commenté dans `deploy/Caddyfile.vps`,
> le site est donc ouvert à tout Internet. Pour le réactiver : décommenter le bloc,
> commiter/pousser, puis sur le VPS `git pull` et
> `docker compose -f docker-compose.yml -f docker-compose.vps.yml restart web`.
> Les variables `BASIC_AUTH_*` du `.env` restent nécessaires dans les deux cas.

## 7. Construire et démarrer l'application

```bash
docker compose -f docker-compose.yml -f docker-compose.vps.yml up -d --build
```

Le second fichier (`-f docker-compose.vps.yml`) adapte la pile au VPS public :
HTTPS + mot de passe via le Caddyfile VPS, certificats persistants, et l'écoute
interne sans mot de passe réservée au worker de rapports. Comptez ~10 minutes
(builds + image worker de 1,5 Go). Puis :

```bash
docker compose ps                      # attendu : 4 services Up, postgis "healthy"
docker compose logs web | tail -20     # "certificate obtained" = HTTPS prêt
```

Si Let's Encrypt échoue sur le nom OVH, Caddy réessaie puis bascule seul sur ZeroSSL.
Dernier recours : ajouter `tls internal` sous `{$SITE_ADDRESS} {` dans
`deploy/Caddyfile.vps` (certificat auto-signé : l'application fonctionne, le
navigateur affiche un avertissement à accepter).

## 8. Importer les données

### 8.0 Avant tout import : image et schéma à jour (obligatoire)

C'est la « règle d'or » de l'introduction — l'oublier est la première cause de panne :

```bash
cd ~/azgbis
docker compose --profile tools build ingest
docker compose --profile tools run --rm ingest schema
```

`tmux` garde ensuite la session vivante même si votre SSH se coupe :

```bash
sudo apt -y install tmux
tmux new -s imports        # se détacher : Ctrl+B puis D ; revenir : tmux attach -t imports
```

### 8.1 Ordre des imports et dépendances

| Commande | Portée | Dépend de |
|---|---|---|
| `ingest dvf --dept N --years 2021-2025` | département | — |
| `ingest contours --dept N` | département | `dvf` du même département |
| `ingest bati --dept N` | département | `contours` du même département (ne garde que les bâtiments des parcelles vendues) |
| `ingest sirene [--dept N …]` | tous les dépts DVF (ou liste) | `dvf` |
| `ingest enrich` | toute la base | `contours` + `bati` + `sirene` |
| `ingest admin`, `ingest radon`, `ingest inpn --famille …` | France entière, une seule fois | `admin` avant `radon` |

Tous les imports sont **remplaçants et rejouables** : relancer une commande écrase
proprement son périmètre, jamais d'état partiel.

### 8.2 Un seul département (~1 à 2 h)

Dans tmux (les commandes s'enchaînent grâce aux `&&`) :

```bash
docker compose --profile tools run --rm ingest dvf --dept 69 --years 2021-2025 && \
docker compose --profile tools run --rm ingest contours --dept 69 && \
docker compose --profile tools run --rm ingest bati --dept 69 && \
docker compose --profile tools run --rm ingest sirene && \
docker compose --profile tools run --rm ingest enrich && \
docker compose --profile tools run --rm ingest admin && \
docker compose --profile tools run --rm ingest radon && \
docker compose --profile tools run --rm ingest inpn --famille znieff1 && \
docker compose --profile tools run --rm ingest inpn --famille znieff2 && \
docker compose --profile tools run --rm ingest inpn --famille natura2000 && \
docker compose --profile tools run --rm ingest inpn --famille espace_protege && \
docker compose --profile tools run --rm ingest inpn --famille patrimoine_geol && \
docker compose --profile tools run --rm ingest status
```

Ajouter un département ensuite = `dvf` → `contours` → `bati` avec le bon `--dept`,
puis `sirene` et `enrich` (les couches France entière ne sont pas à refaire).

### 8.3 France métropolitaine (24-48 h, VPS 40 Go)

Budget disque tout compris ≈ 40 Go : DVF national ≈ 9 Go, bâtiments filtrés ≈ 2 Go,
SIRENE ≈ 1 Go, zonages/choroplèthes ≈ 0,5 Go, images Docker ≈ 4-5 Go, système et
marge. Surveiller avec `df -h /`. Dans tmux, après le §8.0 :

```bash
# 1. Par département : DVF, cadastre, bâtiments (un échec n'arrête pas la boucle, il est journalisé)
DEPTS="$(seq -w 1 19) 2A 2B $(seq 21 95)"
for d in $DEPTS; do
  docker compose --profile tools run --rm ingest dvf --dept $d --years 2021-2025 && \
  docker compose --profile tools run --rm ingest contours --dept $d && \
  docker compose --profile tools run --rm ingest bati --dept $d || echo "$d" >> ~/imports-echecs.log
done

# 2. SIRENE par lots de ~20 départements (4 Go de RAM : ne pas tout charger d'un coup)
for lot in "$(seq -w 1 19) 2A 2B" "$(seq 21 40)" "$(seq 41 60)" "$(seq 61 80)" "$(seq 81 95)"; do
  args=""; for d in $lot; do args="$args --dept $d"; done
  docker compose --profile tools run --rm ingest sirene $args
done

# 3. Couches France entière (une seule fois) + enrichissement + contrôle
docker compose --profile tools run --rm ingest admin && \
docker compose --profile tools run --rm ingest radon && \
docker compose --profile tools run --rm ingest inpn --famille znieff1 && \
docker compose --profile tools run --rm ingest inpn --famille znieff2 && \
docker compose --profile tools run --rm ingest inpn --famille natura2000 && \
docker compose --profile tools run --rm ingest inpn --famille espace_protege && \
docker compose --profile tools run --rm ingest inpn --famille patrimoine_geol && \
docker compose --profile tools run --rm ingest enrich && \
docker compose --profile tools run --rm ingest status

# 4. Départements en échec à rejouer (dvf → contours → bati) :
sort -u ~/imports-echecs.log 2>/dev/null
```

**Disque saturé (`No space left on device`)** — récupérer de l'espace sans perdre de
données (le volume raw n'est qu'un cache d'import ; tout est retéléchargeable) :

```bash
df -h /                                                    # constat
docker run --rm -v azgbis_raw:/r alpine du -sh /r          # poids du cache d'import
docker run --rm -v azgbis_raw:/r alpine sh -c 'rm -rf /r/*'   # purge du cache (sans risque)
docker builder prune -af                                   # cache de build Docker
docker compose exec postgis psql -U azgbis -d azgbis -c 'VACUUM FULL bati;'  # bloat des imports interrompus
df -h /                                                    # vérifier l'espace regagné
```

Puis reprendre le département en cours. `ingest bati` supprime désormais archive et
gpkg même en cas d'échec : un import interrompu ne laisse plus de résidus.

## 9. Recette

1. Ouvrir `https://azgbis.baillylab.fr` → la carte s'affiche (si le basic auth est
   réactivé — voir §6 — le navigateur demande d'abord identifiant et mot de passe).
2. Activer les couches Environnement, « Prix au m² (ventes DVF) » et « Potentiel
   radon » → zonages verts, choroplèthe violette (avec filtres période et typologies),
   choroplèthe radon fluide à l'échelle France.
3. Rechercher « Place Bellecour Lyon », tracer un point + rayons, « Analyser la zone »
   → les 5 thèmes répondent ; la section Marché affiche des typologies en toutes
   lettres (« Bureaux », « Commerce »…) et propose l'export Excel.
4. **Générer un rapport PDF** et l'ouvrir : les cartes doivent y figurer (c'est le
   test de l'écoute interne 8080).
5. Test de robustesse : `sudo reboot`, attendre 2 minutes, se reconnecter,
   `docker compose ps` → les 4 services sont revenus seuls.

## 10. Maintenance courante

- **Mettre à jour l'application** — séquence complète, toujours la même :
  ```bash
  cd ~/azgbis && git pull && \
  docker compose -f docker-compose.yml -f docker-compose.vps.yml up -d --build && \
  docker compose --profile tools build ingest && \
  docker compose --profile tools run --rm ingest schema
  ```
  Les deux dernières lignes sont la « règle d'or » (§8.0) : sans elles, l'image
  d'import reste l'ancienne et les nouvelles commandes/tables n'existent pas.
- **Sauvegarde quotidienne de la base** (optionnelle — tout est reconstructible depuis
  l'open data, la sauvegarde raccourcit juste le délai de reprise) :
  ```bash
  docker compose exec postgis pg_dump -U azgbis -Fc azgbis > ~/azgbis-$(date +%F).dump
  ```
- **Rafraîchir le DVF** (publications avril/octobre) : par département, `ingest dvf`
  puis `ingest contours` puis `ingest bati`, et un `ingest enrich` final.
- **Rafraîchir la typologie** : `ingest bati --dept …` à chaque millésime BD TOPO
  (mars/juin/septembre/décembre), `ingest sirene` mensuel, puis `ingest enrich`.
- **Réimport annuel** : `ingest admin` (millésime COG) puis `ingest radon` ;
  `ingest inpn` semestriel.
- Les rapports PDF sont purgés automatiquement après 24 h ; rien à faire.

## En cas de problème

| Symptôme | Piste |
|---|---|
| Page inaccessible | `docker compose ps` (tout Up ?), `sudo ufw status` (443 ouvert ?) |
| Avertissement de certificat | `docker compose logs web` — délivrance en cours ou échouée (voir §7) |
| Erreur 502 sur /api | `docker compose logs api` |
| `ingest: error: … invalid choice: 'xxx'` | image d'import périmée — §8.0 (`--profile tools build ingest`) |
| `relation "…" does not exist` pendant un import | schéma pas à jour — §8.0 (`ingest schema`) |
| Disque plein pendant les imports | `df -h /`, purger le volume raw (§8.3), relancer le département en cours |
| Thèmes « source non chargée » | imports du §8 non terminés — `ingest status` |
| Rapport généré sans cartes | `docker compose logs worker` ; vérifier que `RENDER_URL` vaut `http://web:8080` (override VPS) |
| Mot de passe refusé | régénérer le hash (§6) puis `docker compose ... up -d --force-recreate web` |
