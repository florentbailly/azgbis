"""Invariants du catalogue de couches : le front et le rapport le consomment tel quel,
une entrée incohérente casse silencieusement l'affichage ou les cartes du PDF."""
from app import catalog


def test_ids_uniques():
    ids = [l["id"] for l in catalog.LAYERS]
    assert len(ids) == len(set(ids))


def test_theme_de_chaque_couche_existe():
    themes = {t["id"] for t in catalog.THEMES}
    for l in catalog.LAYERS:
        assert l["theme"] in themes, l["id"]


def test_wms_ont_un_nom_de_couche():
    for l in catalog.LAYERS:
        if l["type"] == "wms":
            assert l.get("wms_layer"), l["id"]


def test_vector_ont_source_layer_et_url_gabarit():
    for l in catalog.LAYERS:
        if l["type"] == "vector":
            assert l.get("source_layer"), l["id"]
            assert "{z}" in l["url"] and "{x}" in l["url"] and "{y}" in l["url"], l["id"]


def test_couches_rapport_referencent_des_couches_reelles():
    ids = {l["id"] for l in catalog.LAYERS}
    for t in catalog.THEMES:
        for c in t["couches_rapport"]:
            assert c in ids, f"{t['id']} → {c}"


def test_rendu_classes_porte_sa_legende():
    for l in catalog.LAYERS:
        if l.get("rendu") == "classes":
            assert l["classes"], l["id"]
            for c in l["classes"]:
                assert set(c) == {"classe", "couleur", "libelle"}, l["id"]
            valeurs = [c["classe"] for c in l["classes"]]
            assert valeurs == sorted(set(valeurs)), l["id"]


def test_couleurs_des_themes_sont_la_charte():
    for t in catalog.THEMES:
        assert t["couleur"].startswith("#") and len(t["couleur"]) == 7, t["id"]
