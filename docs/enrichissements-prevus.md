# Enrichissements de données — prochaines actions

Récapitulatif des imports et enrichissements restant à mener (état au 20/07/2026),
par ordre de valeur métier. Tout reste 100 % open data, dans la continuité de la
[spécification lot 1](specification-lot1.md) (§5 enrichissement, §9 pipeline).

## 1. ✅ Typologie des bâtiments — FAIT (22/07/2026, via BD TOPO + SIRENE)

Réalisé par `ingest bati` + `ingest sirene` + `ingest enrich` (spec §5 révisée).
La BDNB prévue initialement n'est plus distribuée par département (export France
~39 Go ou API à clé) : l'usage du bâti vient de la **BD TOPO (IGN)** et l'arbitrage
bureaux/commerce du **code NAF SIRENE** (fichiers INSEE, l'ancien geo-sirene est
décommissionné). Reste de l'ambition BDNB reportée sur l'item 4 :

- année de construction et classe DPE → `ingest dpe` (ADEME) ;
- à terme : couche carte « typologie du bâti » (la table `bati` contient déjà
  l'usage et la géométrie de chaque bâtiment).

Le filtre par typologie sur la carte des prix est fait (22/07/2026) : cases à
cocher sous la couche dans le panneau Couches, paramètre `?typologies=` des
tuiles `/api/tiles/dvf`, cumulable avec le filtre de période.

## 2. Transports en commun (OpenStreetMap)

Nouveau thème « Équipements & services » (couleur `#EAB818` déjà réservée dans la
charte). Source : extraits régionaux **Geofabrik** (licence ODbL — attribution
« © OpenStreetMap contributors » à ajouter aux couches et au rapport).

- `ingest osm --famille transports` : gares (`railway=station|halt`), arrêts
  (`highway=bus_stop`, `public_transport=platform`), stations métro/tram
  (`railway=tram_stop`, `station=subway`) → table `osm_poi` (catégorie, nom, geom).
- Affichage en tuiles vectorielles depuis PostGIS (même mécanique que l'INPN) ;
  analyse : nombre d'arrêts par catégorie dans la zone, distance au plus proche,
  gare la plus proche. Option ultérieure : fréquences via les GTFS de
  transport.data.gouv.fr (hors périmètre du premier jet).

## 3. Services du quotidien (OpenStreetMap)

Même pipeline `ingest osm`, familles supplémentaires :

- **écoles** : `amenity=school|kindergarten|college|university` ;
- **commerces** : `shop=*` (agrégés en grandes catégories : alimentaire, autre) ;
- **santé** : `amenity=pharmacy|hospital|doctors|clinic` ;
- **services publics** : `amenity=townhall|post_office|police`.

Indicateurs d'analyse : compteurs par catégorie en zone d'étude et de contexte,
distance au plus proche. C'est le même modèle de table et de tuiles que les
transports — les deux se font ensemble dans `ingest osm`.

## 4. DPE et bâtiments en propre

- `ingest dpe` (ADEME, open data) : classes DPE à l'adresse — complète la BDNB
  quand elle est en retard sur les diagnostics récents.
- `ingest bdnb` : conserver les attributs bâtiment utiles au-delà de la jointure
  DVF (année, matériaux, hauteur) pour de futurs indicateurs de bâti.

## Mécanisme réutilisable : choroplèthes par classes

Depuis juillet 2026, toute donnée « une classe par commune » (radon aujourd'hui ;
demain : zonage sismique communal, potentiel géothermique…) suit le même circuit :
un ingest qui remplit `carto_classes` (mailles commune + département, contours
`admin_contours` importés une fois pour toutes par `ingest admin`), servi par
`/api/tiles/classes/{couche}`, avec légende et couleurs déclarées dans le
catalogue — **zéro code front**. Voir le skill `/add-new-data`.

## 5. Dette restante côté données

- Import DVF + contours des **autres départements** couverts par l'équipe (VPS).
- **Millésime DVF réel** dans la traçabilité du rapport (aujourd'hui : horodatage
  de l'appel).
- Endpoint filtres DVF (`GET /api/dvf/transactions`) encore en 501 — l'export
  Excel de la zone est fait, restent les filtres à façon (période, typologie).
- Poids du rapport PDF (~24 Mo, cartes retina) à compresser.
