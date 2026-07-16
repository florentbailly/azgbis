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
