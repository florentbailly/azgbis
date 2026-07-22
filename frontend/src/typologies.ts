/* Nomenclature typologique des locaux DVF (spec §5) — partagée entre le panneau
   Couches (filtre de la carte des prix) et le panneau Analyse. Miroir obligatoire :
   backend/app/reports/libelles.py (TYPOLOGIES) et tiles.py (TYPOLOGIES_PRIX). */

export const TYPOLOGIE_LABELS: Record<string, string> = {
  residentiel: "Résidentiel",
  bureaux: "Bureaux",
  commerce: "Commerce",
  industriel: "Industriel",
  agricole: "Agricole",
  autre: "Autre (dépendances…)",
  tertiaire_non_qualifie: "Tertiaire non qualifié",
};

export const TYPOLOGIE_ORDRE = [
  "residentiel", "bureaux", "commerce", "industriel", "agricole",
  "autre", "tertiaire_non_qualifie",
] as const;
