# Déployer sur un VPS public (OVHcloud, Ubuntu) — pas à pas

Ce guide déploie l'application complète (carte, analyse, rapports PDF) sur un VPS
Ubuntu nu, en ~30 minutes de manipulations + 1 à 2 h d'imports de données sans
surveillance. Il est écrit pour être suivi commande par commande.

**Ce qui sera en place à la fin** : l'application accessible en **HTTPS** sur le nom
OVH du VPS, protégée par un **mot de passe partagé** (l'outil n'a pas de comptes
individuels avant le lot 2 — sur un VPS public, sans cela, tout Internet y accéderait),
les 4 conteneurs relancés automatiquement au démarrage de la machine.

Prérequis : un VPS OVH Ubuntu (≥ 4 Go RAM, ≥ 20 Go de disque libre : ~4 Go d'images,
~2 Go de données, marge), son adresse IP, et l'accès SSH fourni par OVH.

---

## 1. Sur votre poste : pousser l'état du code

Le VPS clonera GitHub : ce qui n'est pas commité/poussé n'existera pas pour lui.

```powershell
cd c:\Users\flore\azgbis
git status          # voir ce qui part
git add -A
git commit -m "heatmap prix DVF + rapport PDF + deploiement VPS"
git push
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

1. **Nom DNS du VPS** : dans le manager OVH (ou `hostname -f` sur le VPS), de la forme
   `vps-a1b2c3d4.vps.ovh.net`. Vérifier qu'il pointe bien vers l'IP :
   ```bash
   nslookup vps-a1b2c3d4.vps.ovh.net
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
SITE_ADDRESS=vps-a1b2c3d4.vps.ovh.net
BASIC_AUTH_USER=azgbis
BASIC_AUTH_HASH=$2a$14$le_hash_produit_par_caddy
```

Enregistrer : `Ctrl+O`, `Entrée`, puis `Ctrl+X`.

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

## 8. Importer les données (~1 à 2 h)

`tmux` garde la session vivante même si votre SSH se coupe :

```bash
sudo apt -y install tmux
tmux new -s imports
```

Puis, dans tmux (les commandes s'enchaînent seules grâce aux `&&`) :

```bash
docker compose --profile tools run --rm ingest schema && \
docker compose --profile tools run --rm ingest dvf --dept 69 --years 2021-2025 && \
docker compose --profile tools run --rm ingest contours --dept 69 && \
docker compose --profile tools run --rm ingest admin && \
docker compose --profile tools run --rm ingest radon && \
docker compose --profile tools run --rm ingest bati --dept 69 && \
docker compose --profile tools run --rm ingest sirene && \
docker compose --profile tools run --rm ingest enrich && \
docker compose --profile tools run --rm ingest inpn --famille znieff1 && \
docker compose --profile tools run --rm ingest inpn --famille znieff2 && \
docker compose --profile tools run --rm ingest inpn --famille natura2000 && \
docker compose --profile tools run --rm ingest inpn --famille espace_protege && \
docker compose --profile tools run --rm ingest inpn --famille patrimoine_geol && \
docker compose --profile tools run --rm ingest status
```

Se détacher de tmux : `Ctrl+B` puis `D` (la session continue) ; y revenir :
`tmux attach -t imports`. Ajouter d'autres départements = rejouer `ingest dvf`,
`ingest contours` puis `ingest bati` avec le bon `--dept` (dans cet ordre — bati ne
garde que les bâtiments des parcelles vendues), et refaire `ingest enrich`.

### France métropolitaine sur un VPS de 40 Go

Le pipeline est dimensionné pour tenir tout compris dans ~40 Go : DVF national
≈ 9 Go, bâtiments filtrés ≈ 2 Go, SIRENE ≈ 1 Go, zonages/choroplèthes ≈ 0,5 Go,
plus images Docker et système. Boucle type (24-48 h, dans tmux) :

```bash
DEPTS="$(seq -w 1 19) 2A 2B $(seq 21 95)"
for d in $DEPTS; do
  docker compose --profile tools run --rm ingest dvf --dept $d --years 2021-2025 && \
  docker compose --profile tools run --rm ingest contours --dept $d && \
  docker compose --profile tools run --rm ingest bati --dept $d || echo "$d" >> ~/imports-echecs.log
done
# SIRENE par lots de ~20 départements (4 Go de RAM : ne pas tout charger d'un coup)
for lot in "$(seq -w 1 19) 2A 2B" "$(seq 21 40)" "$(seq 41 60)" "$(seq 61 80)" "$(seq 81 95)"; do
  args=""; for d in $lot; do args="$args --dept $d"; done
  docker compose --profile tools run --rm ingest sirene $args
done
docker compose --profile tools run --rm ingest enrich
cat ~/imports-echecs.log 2>/dev/null && echo "→ relancer ces départements"
```

Si le disque se tend, le volume raw peut être purgé sans risque (tout est
retéléchargeable ; les fichiers cadastre/DVF servent de cache d'import) :
`docker run --rm -v azgbis_raw:/r alpine sh -c 'rm -rf /r/*'`.

## 9. Recette

1. Ouvrir `https://vps-a1b2c3d4.vps.ovh.net` → le navigateur demande
   l'identifiant (`azgbis`) et le mot de passe partagé → la carte s'affiche.
2. Activer les couches Environnement et « Prix au m² (ventes DVF) » → zonages verts
   et choroplèthe violette visibles sur le Rhône.
3. Rechercher « Place Bellecour Lyon », tracer un point + rayons, « Analyser la zone »
   → les 5 thèmes répondent.
4. **Générer un rapport PDF** et l'ouvrir : les cartes doivent y figurer (c'est le
   test de l'écoute interne 8080).
5. Test de robustesse : `sudo reboot`, attendre 2 minutes, se reconnecter,
   `docker compose ps` → les 4 services sont revenus seuls.

## 10. Maintenance courante

- **Mettre à jour l'application** :
  ```bash
  cd ~/azgbis && git pull && \
  docker compose -f docker-compose.yml -f docker-compose.vps.yml up -d --build
  ```
- **Sauvegarde quotidienne de la base** (optionnelle — tout est reconstructible depuis
  l'open data, la sauvegarde raccourcit juste le délai de reprise) :
  ```bash
  docker compose exec postgis pg_dump -U azgbis -Fc azgbis > ~/azgbis-$(date +%F).dump
  ```
- **Rafraîchir le DVF** (publications avril/octobre) : rejouer `ingest dvf` puis
  `ingest contours` par département, puis `ingest enrich`.
- **Rafraîchir la typologie** : `ingest bati --dept …` à chaque millésime BD TOPO
  (mars/juin/septembre/décembre), `ingest sirene` mensuel, puis `ingest enrich`.
- Les rapports PDF sont purgés automatiquement après 24 h ; rien à faire.
- Après un `git pull` qui touche `pipeline/` : `docker compose --profile tools build ingest`
  avant les imports — `up --build` ignore les services derrière un profil.

## En cas de problème

| Symptôme | Piste |
|---|---|
| Page inaccessible | `docker compose ps` (tout Up ?), `sudo ufw status` (443 ouvert ?) |
| Avertissement de certificat | `docker compose logs web` — délivrance en cours ou échouée (voir §7) |
| Erreur 502 sur /api | `docker compose logs api` |
| Thèmes « source non chargée » | imports du §8 non terminés — `ingest status` |
| Rapport généré sans cartes | `docker compose logs worker` ; vérifier que `RENDER_URL` vaut `http://web:8080` (override VPS) |
| Mot de passe refusé | régénérer le hash (§6) puis `docker compose ... up -d --force-recreate web` |
