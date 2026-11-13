"""Metriques du benchmark : formules, garde-fous, verdict et comparaison."""

from __future__ import annotations

from typing import Any, Dict

from adam_core.benchmark.metriques import (
    FiltresChamps,
    bloc,
    calculer,
    comparer,
    detail_champ,
    wilson,
)


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
            8,
            1,
            1,
            1,
            50,
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
        assert "échantillon trop petit" in texte
        assert "pas assez de données" in texte
        assert "vérification partielle" in texte
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
        # Tous les champs sont listes ; a.c n'a pas bouge, il est aussi compte.
        assert {ch["champ"] for ch in c["par_champ"]} == {"a.b", "a.c"}
        assert c["champs_inchanges"] == 1
        ab = next(ch for ch in c["par_champ"] if ch["champ"] == "a.b")
        assert (ab["reussite_a"], ab["reussite_b"], ab["ecart_pts"]) == (0.6, 0.9, 30.0)

    def test_champ_d_un_seul_cote_et_regressions_d_abord(self) -> None:
        a = calculer(
            [_ligne("a.b", vp=9, fn=1), _ligne("a.c", vp=5)], EXECUTION, tous_les_champs=True
        )
        b = calculer(
            [_ligne("a.b", vp=5, fn=5), _ligne("a.d", vp=3)],
            dict(EXECUTION, id=2),
            tous_les_champs=True,
        )
        c = comparer(a, b)
        par_champ = {ch["champ"]: ch for ch in c["par_champ"]}
        assert c["par_champ"][0]["champ"] == "a.b"  # -40 pts : la regression en tete
        assert par_champ["a.c"]["present_b"] is False and par_champ["a.c"]["ecart_pts"] is None
        assert par_champ["a.d"]["present_a"] is False and par_champ["a.d"]["reussite_b"] == 1.0

    def test_par_section_et_documents(self) -> None:
        lignes = [_ligne("a.b", vp=6, fn=4, section_label="Section A")]
        a = calculer(lignes, EXECUTION, tous_les_champs=True)
        b = calculer(
            [_ligne("a.b", vp=8, fn=2, section_label="Section A")],
            dict(EXECUTION, id=2, documents_compared=11),
            tous_les_champs=True,
        )
        c = comparer(a, b)
        assert c["par_section"]["a"]["libelle"] == "Section A"
        assert c["par_section"]["a"]["ecart_pts"] == 0.0  # pas de fp : 100 % des deux cotes
        assert (c["a"]["documents"], c["b"]["documents"]) == (12, 11)
        assert "nombre de documents different" in c["raisons"]

    def test_non_comparable_signale(self) -> None:
        a = calculer([_ligne("a.b", vp=6)], EXECUTION)
        b = calculer([_ligne("a.b", vp=6)], dict(EXECUTION, id=2, schema_hash="autre"))
        c = comparer(a, b)
        assert c["comparable"] is False
        assert c["raisons"] == ["empreinte du schema differente"]

    def test_verite_differente_signalee(self) -> None:
        a = calculer([_ligne("a.b", vp=6)], dict(EXECUTION, verite_hash="v1"))
        b = calculer([_ligne("a.b", vp=6)], dict(EXECUTION, id=2, verite_hash="v2"))
        assert comparer(a, b)["raisons"] == ["verite humaine differente"]

    def test_verite_absente_d_un_cote_non_signalee(self) -> None:
        """Execution d'avant l'empreinte : rien a comparer, pas une raison."""
        a = calculer([_ligne("a.b", vp=6)], EXECUTION)
        b = calculer([_ligne("a.b", vp=6)], dict(EXECUTION, id=2, verite_hash="v2"))
        assert comparer(a, b)["comparable"] is True


class TestComparerDeuxRecettes:
    """Le but du benchmark : deux moteurs sur les memes documents d'un export."""

    def _cote(self, recette: Dict[str, Any], **execution: Any) -> Dict[str, Any]:
        m = calculer([_ligne("a.b", vp=6)], dict(EXECUTION, **execution), tous_les_champs=True)
        m["recette"] = recette
        return m

    def test_deux_moteurs_sur_le_meme_export_se_comparent(self) -> None:
        a = self._cote(
            {"id": 3, "dataset_export_id": 8, "document_ids": [14, 15]},
            ocr_provider="MISTRAL",
            ocr_model_id="ocr-1",
        )
        b = self._cote(
            {"id": 4, "dataset_export_id": 8, "document_ids": [15, 14]},
            id=2,
            recipe_id=4,
            ocr_provider="MISTRAL",
            ocr_model_id="ocr-2",
        )
        c = comparer(a, b)
        assert c["comparable"] is True, c["raisons"]
        assert c["moteur"]["changements"] == ["modele"] and c["moteur"]["identique"] is False
        assert c["b"]["recette"]["id"] == 4

    def test_autre_export_non_comparable(self) -> None:
        a = self._cote({"id": 3, "dataset_export_id": 8, "document_ids": [14]})
        b = self._cote({"id": 4, "dataset_export_id": 9, "document_ids": [14]}, id=2)
        assert comparer(a, b)["raisons"] == ["export de dataset different"]

    def test_meme_export_autres_documents_non_comparable(self) -> None:
        a = self._cote({"id": 3, "dataset_export_id": 8, "document_ids": [14, 15]})
        b = self._cote({"id": 4, "dataset_export_id": 8, "document_ids": [14]}, id=2)
        assert comparer(a, b)["raisons"] == ["documents differents dans le meme export"]

    def test_champs_exclus_differents_non_comparable(self) -> None:
        """Une exclusion retire des champs des indicateurs : meme export, memes
        documents, mais pas le meme ensemble mesure."""
        a = self._cote({"id": 3, "dataset_export_id": 8, "document_ids": [14]})
        b = self._cote(
            {"id": 4, "dataset_export_id": 8, "document_ids": [14], "champs_exclus": ["c."]},
            id=2,
        )
        assert comparer(a, b)["raisons"] == ["champs exclus differents"]

    def test_recettes_sans_export_differentes_non_comparables(self) -> None:
        a = self._cote({"id": 3})
        b = self._cote({"id": 4}, id=2, recipe_id=4)
        assert comparer(a, b)["raisons"] == ["recette differente, sans export commun"]

    def test_meme_moteur_identique(self) -> None:
        moteur = {"ocr_provider": "MISTRAL", "ocr_model_id": "ocr-1 + annot-1"}
        recette = {"id": 3, "dataset_export_id": 8, "document_ids": [14]}
        a = self._cote(recette, **moteur)
        # La casse du fournisseur (mistral / MISTRAL) n'est pas un changement.
        b = self._cote(recette, id=2, ocr_provider="mistral", ocr_model_id="ocr-1 + annot-1")
        assert comparer(a, b)["moteur"] == {
            "a": {"fournisseur": "MISTRAL", "modele": "ocr-1 + annot-1"},
            "b": {"fournisseur": "mistral", "modele": "ocr-1 + annot-1"},
            "identique": True,
            "changements": [],
        }


class TestGardeFousLecture:
    def test_execution_anterieure_aux_metriques_signalee(self) -> None:
        """Lignes ecrites avant la matrice : compared > 0, vp/fp/fn/vn a 0."""
        m = calculer([_ligne("a.b", compared=7, diff_count=2)], EXECUTION)
        assert any("antérieure aux métriques" in a for a in m["avertissements"])

    def test_sans_version_non_comparable(self) -> None:
        sans = dict(EXECUTION, comparateur_version=None)
        c = comparer(calculer([_ligne("a.b", vp=5)], sans), calculer([_ligne("a.b", vp=5)], sans))
        assert c["comparable"] is False
        assert "version du comparateur differente" in c["raisons"]


class TestParChamp:
    """Reussite, documents en erreur, echec principal, et les filtres."""

    def _lignes(self) -> list:
        return [
            # 10 documents : 7 justes, 2 fausses, 1 manquee -> reussite 0.7
            _ligne("deposant.nom", vp=7, fp=2, fn=3, substitutions=2),
            # 4 documents : 1 juste, 3 inventees -> reussite 0.25
            _ligne("credits.montant", vp=1, fp=3, value_type="NUMBER"),
            # 5 documents, tous justes
            _ligne("deposant.ville", vp=5, vn=5),
            # que des vides : pas de reussite
            _ligne("certification.lieu", vn=10),
        ]

    def test_detail_champ(self) -> None:
        champ = bloc([_ligne("a.b", vp=7, fp=2, fn=3, substitutions=2)], fourchettes=False)
        assert detail_champ(champ) == {
            "reussite": 0.7,
            "documents_en_erreur": 3,
            "echec_principal": "fausse",
        }
        juste = bloc([_ligne("a.b", vp=4)], fourchettes=False)
        assert detail_champ(juste)["echec_principal"] is None
        vide = bloc([_ligne("a.b", vn=4)], fourchettes=False)
        assert detail_champ(vide)["reussite"] is None

    def test_a_egalite_fausse_avant_les_autres(self) -> None:
        champ = bloc([_ligne("a.b", fp=2, fn=2, substitutions=1)], fourchettes=False)
        # 1 fausse, 1 manquee, 1 inventee
        assert detail_champ(champ)["echec_principal"] == "fausse"

    def test_par_champ_porte_le_detail_et_trie_par_reussite(self) -> None:
        m = calculer(self._lignes(), EXECUTION, tous_les_champs=True)
        assert [c["champ"] for c in m["par_champ"]] == [
            "credits.montant",
            "deposant.nom",
            "deposant.ville",
            "certification.lieu",
        ]
        montant = m["par_champ"][0]
        assert montant["reussite"] == 0.25 and montant["documents_en_erreur"] == 3
        assert montant["echec_principal"] == "inventee" and montant["section"] == "credits"

    def test_sans_filtre_selection_compte_tout(self) -> None:
        m = calculer(self._lignes(), EXECUTION)
        assert m["selection"] == {"filtres": {}, "champs": 2, "champs_verifies": 4}

    def test_chaque_filtre(self) -> None:
        def champs(**filtres: Any) -> list:
            m = calculer(
                self._lignes(), EXECUTION, tous_les_champs=True, filtres=FiltresChamps(**filtres)
            )
            return [c["champ"] for c in m["par_champ"]]

        assert champs(recherche="NOM") == ["deposant.nom"]
        assert champs(types_champ=("number",)) == ["credits.montant"]
        assert champs(sections=("deposant",)) == ["deposant.nom", "deposant.ville"]
        # strictement inferieure ; le champ sans reussite est ecarte
        assert champs(reussite_inferieure_a=0.7) == ["credits.montant"]
        assert champs(types_erreur=("manquee",)) == ["deposant.nom"]
        assert champs(types_erreur=("inventee", "manquee")) == ["credits.montant", "deposant.nom"]
        # plusieurs filtres : ET
        assert champs(sections=("deposant",), reussite_inferieure_a=1.0) == ["deposant.nom"]

    def test_les_filtres_ne_touchent_que_par_champ(self) -> None:
        sans = calculer(self._lignes(), EXECUTION)
        avec = calculer(self._lignes(), EXECUTION, filtres=FiltresChamps(recherche="ville"))
        assert avec["global"] == sans["global"] and avec["par_section"] == sans["par_section"]
        assert avec["par_champ"] == []
        assert avec["selection"] == {
            "filtres": {"recherche": "ville"},
            "champs": 0,
            "champs_verifies": 4,
        }


class TestLibellesEtEchantillon:
    def test_par_section_porte_son_libelle(self) -> None:
        m = calculer(
            [_ligne("co_deposant.nom", vp=1, section_label="Co-déposant"), _ligne("x.y", vp=1)],
            EXECUTION,
        )
        assert m["par_section"]["co_deposant"]["libelle"] == "Co-déposant"
        assert m["par_section"]["x"]["libelle"] == "x"  # sans libelle : l'id

    def test_champs_par_document(self) -> None:
        m = calculer([_ligne("a.b", vp=1)], dict(EXECUTION, fields_compared=642 * 12))
        assert m["echantillon"]["champs_par_document"] == 642
        vide = calculer([_ligne("a.b", vp=1)], dict(EXECUTION, documents_compared=0))
        assert vide["echantillon"]["champs_par_document"] is None
