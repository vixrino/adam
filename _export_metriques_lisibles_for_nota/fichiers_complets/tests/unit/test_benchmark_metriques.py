"""Metriques du benchmark : formules, garde-fous, verdict et comparaison."""

from __future__ import annotations

from typing import Any, Dict

from nota_core.benchmark.metriques import bloc, calculer, comparer, wilson


def _ligne(field_key: str, **comptes: Any) -> Dict[str, Any]:
    base = {
        "field_key": field_key,
        "page": 1,
        "section_id": field_key.split(".")[0],
        "value_type": "TEXT",
        "sensitive": False,
    }
    return {**base, **comptes}


EXECUTION = {
    "id": 1,
    "recipe_id": 3,
    "status": "COMPLETED",
    "comparateur_version": "1",
    "schema_hash": "abc",
    "documents_compared": 12,
    "fields_compared": 100,
    "fields_human_verified": 100,
    "ocr_calls_made": 360,
    "pages_processed": 144,
}


class TestFormules:
    def test_taux_et_score(self) -> None:
        # 8 justes, 1 inventee, 1 manquee, 1 fausse (fp ET fn en base).
        b = bloc([_ligne("a.b", vp=8, fp=2, fn=2, substitutions=1, vn=50)])
        assert b["taux_lectures_justes"] == 0.8 and b["taux_valeurs_trouvees"] == 0.8
        assert b["score"] == 0.8
        assert (b["justes"], b["fausses"], b["manquees"], b["inventees"], b["vides"]) == (
            8, 1, 1, 1, 50,
        )
        assert b["valeurs_jugees"] == 11  # chaque valeur dans une seule case
        assert b["taux_erreur"] == round(3 / 11, 4)

    def test_pas_de_fourchette_par_champ(self) -> None:
        assert "fourchette_lectures_justes" in bloc([_ligne("a.b", vp=8)])
        assert "fourchette_lectures_justes" not in bloc([_ligne("a.b", vp=8)], fourchettes=False)

    def test_les_vides_n_entrent_pas_dans_le_score(self) -> None:
        """Un moteur muet sur un formulaire surtout vide : rappel nul, pas 90 %."""
        b = bloc([_ligne("a.b", vp=0, fn=10, vn=90)])
        assert b["taux_valeurs_trouvees"] == 0.0
        assert b["taux_lectures_justes"] is None  # il n'a rien ecrit
        assert b["score"] == 0.0  # mais son score est nul, pas indefini
        assert b["vides"] == 90

    def test_taux_par_caractere(self) -> None:
        b = bloc([_ligne("a.b", vp=1, somme_distance=3, somme_longueur_attendue=30)])
        assert b["taux_erreur_caracteres"] == 0.1

    def test_wilson(self) -> None:
        bas, haut = wilson(8, 10)
        assert 0.4 < bas < 0.8 < haut < 1.0
        assert wilson(0, 0) is None
        assert wilson(0, 3)[0] == 0.0

    def test_effectif_insuffisant(self) -> None:
        assert bloc([_ligne("a.b", vp=3)])["assez_de_donnees"] is False
        assert bloc([_ligne("a.b", vp=5)])["assez_de_donnees"] is True


class TestCalculer:
    def _lignes(self) -> list:
        return [
            _ligne("deposant.nom", vp=9, fn=1),
            _ligne("gestion_budget.iban", vp=4, fp=1, fn=1, substitutions=1, sensitive=True),
            _ligne("credits.montant", vp=2, fp=2, value_type="NUMBER"),
            _ligne("certification.signature", vp=0, fn=5, value_type="BOOLEAN"),
        ]

    def test_decompositions(self) -> None:
        m = calculer(self._lignes(), EXECUTION, categories={"DIGIT": 3})
        assert set(m["par_type"]) == {"TEXT", "NUMBER", "BOOLEAN"}
        assert set(m["par_criticite"]) == {"critique", "standard"}
        # IBAN (sensible) et montant (NUMBER) sont critiques.
        assert m["par_criticite"]["critique"]["justes"] == 6
        assert m["par_champ"][0]["champ"] == "certification.signature"  # le pire d'abord
        assert m["categories_erreurs"] == {"DIGIT": 3}
        assert m["cout"]["appels_par_document"] == 30.0
        assert m["echantillon"]["part_verifiee"] == 1.0

    def test_par_champ_ne_garde_que_les_erreurs(self) -> None:
        lignes = self._lignes() + [_ligne("deposant.ville", vp=10, vn=2)]
        m = calculer(lignes, EXECUTION)
        assert "deposant.ville" not in {c["champ"] for c in m["par_champ"]}
        assert m["champs_sans_erreur"] == 1
        tous = calculer(lignes, EXECUTION, tous_les_champs=True)
        assert len(tous["par_champ"]) == 5

    def test_champs_exclus_par_config(self) -> None:
        m = calculer(self._lignes(), EXECUTION, {"champs_exclus": ["certification."]})
        assert all(c["champ"] != "certification.signature" for c in m["par_champ"])
        assert m["echantillon"]["champs_exclus_par_config"] == 1
        assert m["global"]["manquees"] == 1 and m["global"]["fausses"] == 1

    def test_verdict(self) -> None:
        sans_seuil = calculer(self._lignes(), EXECUTION)
        assert sans_seuil["verdict"]["reussi"] is None
        exigeant = calculer(
            self._lignes(),
            EXECUTION,
            {"score_minimal": 0.5, "seuils_par_champ": {"gestion_budget.iban": 0.0}},
        )
        assert exigeant["verdict"]["reussi"] is False
        assert exigeant["verdict"]["champs_en_echec"][0]["champ"] == "gestion_budget.iban"
        indulgent = calculer(self._lignes(), EXECUTION, {"score_minimal": 0.1})
        assert indulgent["verdict"]["reussi"] is True

    def test_avertissements(self) -> None:
        petite = dict(EXECUTION, documents_compared=1, fields_human_verified=40)
        m = calculer([_ligne("a.b", vp=2)], petite)
        texte = " ".join(m["avertissements"])
        assert "echantillon trop petit" in texte
        assert "pas assez de donnees" in texte
        assert "verification partielle" in texte
        assert m["echantillon"]["trop_petit"] is True


class TestComparer:
    def test_meme_recette_meme_regle(self) -> None:
        lignes_a = [_ligne("a.b", vp=6, fn=4), _ligne("a.c", vp=5, fn=1)]
        lignes_b = [_ligne("a.b", vp=9, fn=1), _ligne("a.c", vp=5, fn=1)]
        a = calculer(lignes_a, EXECUTION, tous_les_champs=True)
        b = calculer(lignes_b, dict(EXECUTION, id=2), tous_les_champs=True)
        c = comparer(a, b)
        assert c["comparable"] is True
        assert c["global"]["taux_valeurs_trouvees"]["evolution"] == 0.1875  # 11/16 -> 14/16
        # a.c n'a pas bouge : compte, pas liste.
        assert [ch["champ"] for ch in c["par_champ"]] == ["a.b"]
        assert c["champs_inchanges"] == 1

    def test_non_comparable_signale(self) -> None:
        a = calculer([_ligne("a.b", vp=6)], EXECUTION)
        b = calculer([_ligne("a.b", vp=6)], dict(EXECUTION, id=2, schema_hash="autre"))
        c = comparer(a, b)
        assert c["comparable"] is False
        assert c["raisons"] == ["empreinte du schema differente"]


class TestGardeFousLecture:
    def test_execution_anterieure_aux_metriques_signalee(self) -> None:
        """Lignes ecrites avant la matrice : compared > 0, vp/fp/fn/vn a 0."""
        m = calculer([_ligne("a.b", compared=7, diff_count=2)], EXECUTION)
        assert any("anterieure aux metriques" in a for a in m["avertissements"])

    def test_sans_version_non_comparable(self) -> None:
        sans = dict(EXECUTION, comparateur_version=None)
        c = comparer(calculer([_ligne("a.b", vp=5)], sans), calculer([_ligne("a.b", vp=5)], sans))
        assert c["comparable"] is False
        assert "version du comparateur differente" in c["raisons"]
