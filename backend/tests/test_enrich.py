"""Fonctions de décision de l'enrichissement typologique (pipeline/ingest/enrich.py).

Les fonctions sont pures (sans base ni réseau) : on les importe directement depuis
le pipeline — c'est la logique la plus sensible de la chaîne (spec §5).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline"))

from ingest.enrich import decider, typologie_naf  # noqa: E402


# --- typologie_naf : nomenclature depuis la division NAF ---------------------------

def test_naf_divisions_typiques():
    assert typologie_naf("01.13Z") == "agricole"
    assert typologie_naf("25.62B") == "industriel"
    assert typologie_naf("43.32A") == "industriel"   # BTP : ateliers/dépôts
    assert typologie_naf("47.11F") == "commerce"
    assert typologie_naf("56.10A") == "commerce"     # restauration
    assert typologie_naf("62.01Z") == "bureaux"
    assert typologie_naf("84.11Z") == "bureaux"      # administration publique
    assert typologie_naf("85.20Z") == "autre"        # enseignement
    assert typologie_naf("86.21Z") == "autre"        # santé


def test_naf_invalide():
    assert typologie_naf(None) is None
    assert typologie_naf("XX") is None


def test_naf_sci_ecartees():
    # Les 68.20 (SCI, loueurs de biens) sont domiciliées dans le bien possédé :
    # aucun signal sur l'usage du local, elles ne votent pas.
    assert typologie_naf("68.20B") is None
    assert typologie_naf("68.31Z") == "bureaux"  # les agences immobilières, si


# --- decider : arbitrage bâti BD TOPO puis NAF SIRENE ------------------------------

def test_usage_industriel_unique_confiance_haute():
    assert decider({"Industriel": 1200.0}, {}) == ("industriel", "bdtopo", "haute")


def test_usage_industriel_dominant_mixte_confiance_moyenne():
    assert decider({"Industriel": 900.0, "Résidentiel": 300.0}, {}) == \
        ("industriel", "bdtopo", "moyenne")


def test_usage_agricole():
    assert decider({"Agricole": 400.0, "Annexe": 900.0}, {}) == ("agricole", "bdtopo", "haute")


def test_commercial_et_services_arbitre_par_naf():
    # L'usage BD TOPO « Commercial et services » ne distingue pas bureaux/commerce :
    # c'est le NAF dominant qui conclut.
    assert decider({"Commercial et services": 800.0}, {"62.01Z": 3}) == \
        ("bureaux", "sirene", "moyenne")
    assert decider({"Commercial et services": 800.0}, {"47.11F": 2, "62.01Z": 1}) == \
        ("commerce", "sirene", "moyenne")


def test_naf_melange_confiance_basse():
    assert decider({}, {"47.11F": 1, "62.01Z": 1}) == ("commerce", "sirene", "basse") or \
        decider({}, {"47.11F": 1, "62.01Z": 1}) == ("bureaux", "sirene", "basse")


def test_sans_signal_reste_non_qualifie():
    assert decider({}, {}) is None
    assert decider({"Annexe": 50.0, "Indifférencié": 30.0}, {}) is None


def test_residentiel_seul_ne_conclut_pas():
    # Local d'activité en immeuble résidentiel sans établissement connu : on ne
    # reclasse pas arbitrairement.
    assert decider({"Résidentiel": 600.0}, {}) is None
