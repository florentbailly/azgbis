-- Schéma PostGIS lot 1 (spec §6). Stockage en Lambert-93 (EPSG:2154).
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS sources (
    id          serial PRIMARY KEY,
    code        text NOT NULL,
    libelle     text NOT NULL,
    url_source  text,
    licence     text,
    millesime   text,
    date_import timestamptz NOT NULL DEFAULT now(),
    checksum    text
);

CREATE TABLE IF NOT EXISTS dvf_mutations (
    id_mutation     text PRIMARY KEY,
    date_mutation   date NOT NULL,
    nature_mutation text,
    valeur_fonciere numeric,
    code_commune    text,
    source_id       int REFERENCES sources(id),
    geom            geometry(Point, 2154)
);
CREATE INDEX IF NOT EXISTS dvf_mutations_geom_idx ON dvf_mutations USING gist (geom);
CREATE INDEX IF NOT EXISTS dvf_mutations_commune_idx ON dvf_mutations (code_commune);
CREATE INDEX IF NOT EXISTS dvf_mutations_date_idx ON dvf_mutations (date_mutation);

CREATE TABLE IF NOT EXISTS dvf_locaux (
    id                   bigserial PRIMARY KEY,
    id_mutation          text NOT NULL REFERENCES dvf_mutations(id_mutation) ON DELETE CASCADE,
    type_local_dvf       text,
    surface_reelle_bati  numeric,
    surface_terrain      numeric,
    nb_pieces            int,
    id_parcelle          text,
    -- Enrichissement typologique (spec §5)
    typologie            text NOT NULL DEFAULT 'tertiaire_non_qualifie',
    typologie_source     text NOT NULL DEFAULT 'dvf',
    typologie_confiance  text NOT NULL DEFAULT 'nulle',
    annee_construction   int,
    dpe_classe           text,
    dpe_id               text,
    prix_m2              numeric
);
CREATE INDEX IF NOT EXISTS dvf_locaux_mutation_idx ON dvf_locaux (id_mutation);
CREATE INDEX IF NOT EXISTS dvf_locaux_typologie_idx ON dvf_locaux (typologie);
CREATE INDEX IF NOT EXISTS dvf_locaux_parcelle_idx ON dvf_locaux (id_parcelle);

-- Contours cadastraux et administratifs (etalab-cadastre), support de la carte des
-- prix : parcelles (seulement celles ayant une vente), sections, communes, département.
CREATE TABLE IF NOT EXISTS contours (
    id          bigserial PRIMARY KEY,
    niveau      text NOT NULL, -- parcelle | section | commune | departement
    code        text NOT NULL, -- id cadastral (14 c. parcelle, 10 c. section) ou code INSEE
    libelle     text,
    source_id   int REFERENCES sources(id),
    geom        geometry(MultiPolygon, 2154),
    UNIQUE (niveau, code)
);
CREATE INDEX IF NOT EXISTS contours_geom_idx ON contours USING gist (geom);

-- Prix médian au m² par maille, précalculé par `ingest contours` (et rafraîchi par
-- `ingest dvf`) : sert uniquement aux tuiles carte /api/tiles/dvf. L'analyse et le
-- rapport recalculent toujours leurs médianes sur dvf_locaux, jamais sur cette table.
CREATE TABLE IF NOT EXISTS dvf_prix (
    id              bigserial PRIMARY KEY,
    niveau          text NOT NULL,
    code            text NOT NULL,
    libelle         text,
    nb_ventes       int NOT NULL,
    prix_m2_median  double precision,
    geom            geometry(MultiPolygon, 2154),
    UNIQUE (niveau, code)
);
CREATE INDEX IF NOT EXISTS dvf_prix_geom_idx ON dvf_prix USING gist (geom);
CREATE INDEX IF NOT EXISTS dvf_prix_niveau_idx ON dvf_prix (niveau);

-- Contours administratifs France entière (etalab, simplifiés 100 m) : support des
-- choroplèthes par classes (radon…). Séparés de `contours` (cadastre), dont l'import
-- et les suppressions sont départementaux et liés au DVF.
CREATE TABLE IF NOT EXISTS admin_contours (
    id          bigserial PRIMARY KEY,
    niveau      text NOT NULL, -- commune | departement
    code        text NOT NULL, -- code INSEE
    libelle     text,
    source_id   int REFERENCES sources(id),
    geom        geometry(MultiPolygon, 2154),
    UNIQUE (niveau, code)
);
CREATE INDEX IF NOT EXISTS admin_contours_geom_idx ON admin_contours USING gist (geom);

-- Choroplèthes par classes (générique) : une ligne par maille et par couche de données
-- (ex. couche 'radon', classes 1-3). Rempli par les ingest dédiés (radon…), servi par
-- /api/tiles/classes/{couche}. La maille est précalculée par niveau : le front bascule
-- département → commune selon le zoom.
CREATE TABLE IF NOT EXISTS carto_classes (
    id          bigserial PRIMARY KEY,
    couche      text NOT NULL,
    niveau      text NOT NULL,
    code        text NOT NULL,
    libelle     text,
    classe      smallint NOT NULL,
    source_id   int REFERENCES sources(id),
    geom        geometry(MultiPolygon, 2154),
    UNIQUE (couche, niveau, code)
);
CREATE INDEX IF NOT EXISTS carto_classes_geom_idx ON carto_classes USING gist (geom);
CREATE INDEX IF NOT EXISTS carto_classes_couche_idx ON carto_classes (couche, niveau);

-- Bâtiments BD TOPO (IGN) : support de l'enrichissement typologique des locaux DVF
-- (spec §5 ; la BDNB n'est plus distribuée par département — constat 07/2026) et, à
-- terme, d'une couche carte « typologie du bâti ». Import départemental remplaçant.
CREATE TABLE IF NOT EXISTS bati (
    id           bigserial PRIMARY KEY,
    id_bdtopo    text UNIQUE, -- cleabs BD TOPO (stable entre millésimes)
    dept         text NOT NULL,
    usage_1      text,        -- Résidentiel | Commercial et services | Industriel | Agricole | …
    usage_2      text,
    nature       text,
    nb_logements int,
    legere       boolean,
    source_id    int REFERENCES sources(id),
    geom         geometry(MultiPolygon, 2154)
);
CREATE INDEX IF NOT EXISTS bati_geom_idx ON bati USING gist (geom);
CREATE INDEX IF NOT EXISTS bati_dept_idx ON bati (dept);

-- Établissements SIRENE actifs géolocalisés (INSEE) : arbitrage bureaux/commerce de
-- l'enrichissement typologique via le code NAF. Import limité aux départements DVF.
CREATE TABLE IF NOT EXISTS sirene_etablissements (
    siret     text PRIMARY KEY,
    dept      text NOT NULL,
    naf       text,           -- activité principale (NAF rév. 2, ex. 47.11F)
    enseigne  text,
    source_id int REFERENCES sources(id),
    geom      geometry(Point, 2154)
);
CREATE INDEX IF NOT EXISTS sirene_geom_idx ON sirene_etablissements USING gist (geom);
CREATE INDEX IF NOT EXISTS sirene_dept_idx ON sirene_etablissements (dept);

-- File des rapports PDF (spec §8) : l'API dépose, le worker consomme.
-- Les PDF eux-mêmes vivent dans un volume temporaire purgé après 24 h, jamais en base.
CREATE TABLE IF NOT EXISTS report_jobs (
    id      uuid PRIMARY KEY,
    statut  text NOT NULL DEFAULT 'pending', -- pending | running | done | error
    demande jsonb NOT NULL,                  -- corps de POST /reports (zone, thèmes, titre…)
    erreur  text,
    fichier text,                            -- nom du PDF dans le volume rapports
    cree    timestamptz NOT NULL DEFAULT now(),
    maj     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS report_jobs_statut_idx ON report_jobs (statut, cree);

CREATE TABLE IF NOT EXISTS env_zonages (
    id              bigserial PRIMARY KEY,
    famille         text NOT NULL, -- natura2000 | znieff1 | znieff2 | espace_protege | patrimoine_geol
    code_national   text,
    libelle         text,
    url_fiche_inpn  text,
    source_id       int REFERENCES sources(id),
    geom            geometry(MultiPolygon, 2154)
);
-- Géométrie généralisée (~50 m), calculée à l'import : sert uniquement à l'affichage
-- carte aux petites échelles, où re-simplifier les grands contours ZNIEFF à chaque
-- tuile coûte plusieurs secondes. L'analyse et le rapport n'utilisent que `geom`.
ALTER TABLE env_zonages ADD COLUMN IF NOT EXISTS geom_gen geometry(MultiPolygon, 2154);
-- Surface précalculée : permet d'écarter les zonages sub-pixel à l'affichage sans
-- exécuter ST_Area sur toute la table à chaque tuile.
ALTER TABLE env_zonages ADD COLUMN IF NOT EXISTS surface_m2 double precision;
CREATE INDEX IF NOT EXISTS env_zonages_geom_idx ON env_zonages USING gist (geom);
CREATE INDEX IF NOT EXISTS env_zonages_famille_idx ON env_zonages (famille);
CREATE INDEX IF NOT EXISTS env_zonages_surface_idx ON env_zonages (surface_m2);
