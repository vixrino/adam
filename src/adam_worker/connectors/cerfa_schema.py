"""Champs attendus par page du CERFA surendettement v2, pour l'annotation Mistral.

Source : le script de qualification test_mistral_configuration.py, qui a valide
sur des CERFA fictifs l'appel OCR en une passe avec un json_schema par page.
Le schema y etait transcrit en dictionnaires Python approximatifs ; il est
normalise ici en une forme plate — une propriete par cle pointee — car c'est
la seule que le json_schema strict de Mistral accepte, et c'est elle qui fait
que l'annotation rend directement les field_key du contrat (CA-2 du ticket T5).

Les groupes repetables du script (`<variable_numero_...>`) sont aplatis en une
seule instance : la repetition des champs est portee par le ticket T7 et ne
change rien a l'appel OCR, seulement au depliage de la reponse.

Les types sont ceux du script d'origine, y compris les choix discutables
(code_postal en number), pour rester sur la configuration qualifiee ; c'est
field_parser qui tranche en aval.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

#: Une entree par champ : description, type JSON Schema, format optionnel.
FieldDef = Mapping[str, Any]

_PAGE_1: Dict[str, FieldDef] = {
    "deposant.civilite_monsieur": {
        "description": "Case a cocher Monsieur pour le deposant",
        "type": "boolean",
    },
    "deposant.civilite_madame": {
        "description": "Case a cocher Madame pour le deposant",
        "type": "boolean",
    },
    "deposant.nom_naissance": {"description": "Nom de naissance du deposant", "type": "string"},
    "deposant.nom_usage": {"description": "Nom d'usage du deposant", "type": "string"},
    "deposant.prenoms": {"description": "Prenoms du deposant", "type": "string"},
    "deposant.date_naissance": {
        "description": "Date de naissance du deposant",
        "type": "string",
        "format": "date",
    },
    "deposant.lieu_naissance": {"description": "Lieu de naissance du deposant", "type": "string"},
    "deposant.dept_naissance": {
        "description": "Numero du departement de naissance du deposant",
        "type": "string",
    },
    "deposant.pays_naissance": {"description": "Pays de naissance du deposant", "type": "string"},
    "co_deposant.civilite_monsieur": {
        "description": "Case a cocher Monsieur pour le co-deposant",
        "type": "boolean",
    },
    "co_deposant.civilite_madame": {
        "description": "Case a cocher Madame pour le co-deposant",
        "type": "boolean",
    },
    "co_deposant.nom_naissance": {
        "description": "Nom de naissance du co-deposant",
        "type": "string",
    },
    "co_deposant.nom_usage": {"description": "Nom d'usage du co-deposant", "type": "string"},
    "co_deposant.prenoms": {"description": "Prenoms du co-deposant", "type": "string"},
    "co_deposant.date_naissance": {
        "description": "Date de naissance du co-deposant",
        "type": "string",
        "format": "date",
    },
    "co_deposant.lieu_naissance": {
        "description": "Lieu de naissance du co-deposant",
        "type": "string",
    },
    "co_deposant.dept_naissance": {
        "description": "Numero du departement de naissance du co-deposant",
        "type": "string",
    },
    "co_deposant.pays_naissance": {
        "description": "Pays de naissance du co-deposant",
        "type": "string",
    },
    "coordonnees_personnelles.batiment": {
        "description": "Champ Batiment section coordonnees personnelles",
        "type": "string",
    },
    "coordonnees_personnelles.escalier": {
        "description": "Champ Escalier section coordonnees personnelles",
        "type": "number",
    },
    "coordonnees_personnelles.etage": {
        "description": "Champ Etage section coordonnees personnelles",
        "type": "number",
    },
    "coordonnees_personnelles.appartement": {
        "description": "Champ Appartement section coordonnees personnelles",
        "type": "string",
    },
    "coordonnees_personnelles.numero": {
        "description": "Champ Numero de voie section coordonnees personnelles",
        "type": "string",
    },
    "coordonnees_personnelles.voie": {
        "description": "Champ Voie section coordonnees personnelles",
        "type": "string",
    },
    "coordonnees_personnelles.lieu_dit": {
        "description": "Champ Lieu-dit section coordonnees personnelles",
        "type": "string",
    },
    "coordonnees_personnelles.code_postal": {
        "description": "Champ Code postal section coordonnees personnelles",
        "type": "number",
    },
    "coordonnees_personnelles.localite": {
        "description": "Champ Localite section coordonnees personnelles",
        "type": "string",
    },
    "coordonnees_personnelles.pays": {
        "description": "Champ Pays section coordonnees personnelles",
        "type": "string",
    },
    "coordonnees_personnelles.telephone_deposant": {
        "description": "Champ Telephone du deposant section coordonnees personnelles",
        "type": "string",
    },
    "coordonnees_personnelles.telephone_co_deposant": {
        "description": "Champ Telephone du co-deposant section coordonnees personnelles",
        "type": "string",
    },
    "coordonnees_personnelles.courriel": {
        "description": "Champ Adresse courriel du deposant section coordonnees personnelles",
        "type": "string",
    },
    "coordonnees_personnelles.courriel_co_deposant": {
        "description": "Champ Adresse courriel du co-deposant section coordonnees personnelles",
        "type": "string",
    },
    "assist_travailleur_social.nom": {
        "description": "Nom du travailleur social",
        "type": "string",
    },
    "assist_travailleur_social.prenom": {
        "description": "Prenom du travailleur social",
        "type": "string",
    },
    "assist_travailleur_social.adresse": {
        "description": "Adresse du travailleur social",
        "type": "string",
    },
    "assist_travailleur_social.telephone": {
        "description": "Telephone du travailleur social",
        "type": "string",
    },
    "assist_travailleur_social.courriel": {
        "description": "Adresse courriel du travailleur social",
        "type": "string",
    },
    "certification.fait_a": {"description": "Lieu de certification", "type": "string"},
    "certification.date": {
        "description": "Date de certification",
        "type": "string",
        "format": "date",
    },
    "certification.signature_deposant": {
        "description": "Signature du deposant",
        "type": "boolean",
    },
    "certification.signature_codeposant": {
        "description": "Signature du co-deposant",
        "type": "boolean",
    },
}

_PAGE_2: Dict[str, FieldDef] = {
    "dossier_precedent.non": {"description": "Aucun dossier precedent", "type": "boolean"},
    "dossier_precedent.oui": {
        "description": "Existence d'un dossier precedent",
        "type": "boolean",
    },
    "dossier_precedent.numero": {"description": "Numero du dossier precedent", "type": "string"},
    "situation_familiale.marie": {"description": "Marie(e)", "type": "boolean"},
    "situation_familiale.marie_date": {
        "description": "Date du mariage",
        "type": "string",
        "format": "date",
    },
    "situation_familiale.pacse": {"description": "Pacse(e)", "type": "boolean"},
    "situation_familiale.pacse_date": {
        "description": "Date du PACS",
        "type": "string",
        "format": "date",
    },
    "situation_familiale.concubin": {"description": "Concubin(e)", "type": "boolean"},
    "situation_familiale.concubin_date": {
        "description": "Date de debut du concubinage",
        "type": "string",
        "format": "date",
    },
    "situation_familiale.autre": {"description": "Autre situation familiale", "type": "string"},
    "situation_familiale.celibataire": {"description": "Celibataire", "type": "boolean"},
    "situation_familiale.separe": {"description": "Separe(e)", "type": "boolean"},
    "situation_familiale.separe_date": {
        "description": "Date de separation",
        "type": "string",
        "format": "date",
    },
    "situation_familiale.divorce": {"description": "Divorce(e)", "type": "boolean"},
    "situation_familiale.divorce_date": {
        "description": "Date du divorce",
        "type": "string",
        "format": "date",
    },
    "situation_familiale.veuf": {"description": "Veuf(ve)", "type": "boolean"},
    "situation_familiale.veuf_date": {
        "description": "Date du veuvage",
        "type": "string",
        "format": "date",
    },
    "personnes_a_charge.lien_parente": {"description": "Lien de parente", "type": "string"},
    "personnes_a_charge.date_naissance": {
        "description": "Date de naissance de la personne a charge",
        "type": "string",
        "format": "date",
    },
    "personnes_a_charge.situation_garde": {
        "description": "Situation ou mode de garde",
        "type": "string",
    },
    "personnes_a_charge.ressources_oui": {
        "description": "La personne a charge dispose de ressources",
        "type": "boolean",
    },
    "personnes_a_charge.ressources_non": {
        "description": "La personne a charge ne dispose pas de ressources",
        "type": "boolean",
    },
    "situation_logement_deposant.locataire": {
        "description": "Case a cocher : deposant locataire",
        "type": "boolean",
    },
    "situation_logement_deposant.expulsion_oui": {
        "description": "Case a cocher procedure d'expulsion en cours : oui",
        "type": "boolean",
    },
    "situation_logement_deposant.expulsion_non": {
        "description": "Case a cocher procedure d'expulsion en cours : non",
        "type": "boolean",
    },
    "situation_logement_deposant.proprietaire": {
        "description": "Case a cocher : deposant proprietaire",
        "type": "boolean",
    },
    "situation_logement_deposant.saisie_immobiliere_oui": {
        "description": "Case a cocher saisie immobiliere en cours : oui",
        "type": "boolean",
    },
    "situation_logement_deposant.saisie_immobiliere_non": {
        "description": "Case a cocher saisie immobiliere en cours : non",
        "type": "boolean",
    },
}

_PAGE_6: Dict[str, FieldDef] = {
    "dettes_logement.nom_creancier": {
        "description": "Nom du creancier de la dette de logement",
        "type": "string",
    },
    "dettes_logement.adresse_creancier": {
        "description": "Adresse du creancier de la dette de logement",
        "type": "string",
    },
    "dettes_logement.reference": {
        "description": "Reference de la dette de logement",
        "type": "string",
    },
    "dettes_logement.montant_impaye": {
        "description": "Montant impaye de la dette de logement",
        "type": "number",
    },
    "dettes_logement.poursuites_oui": {
        "description": "Poursuites en cours pour la dette de logement",
        "type": "boolean",
    },
    "dettes_logement.poursuites_non": {
        "description": "Aucune poursuite pour la dette de logement",
        "type": "boolean",
    },
    "dettes_courantes.nom_creancier": {
        "description": "Nom du creancier de la dette courante",
        "type": "string",
    },
    "dettes_courantes.adresse_creancier": {
        "description": "Adresse du creancier de la dette courante",
        "type": "string",
    },
    "dettes_courantes.reference": {
        "description": "Reference de la dette courante",
        "type": "string",
    },
    "dettes_courantes.montant_impaye": {
        "description": "Montant impaye de la dette courante",
        "type": "number",
    },
    "dettes_courantes.poursuites_oui": {
        "description": "Poursuites en cours pour la dette courante",
        "type": "boolean",
    },
    "dettes_courantes.poursuites_non": {
        "description": "Aucune poursuite pour la dette courante",
        "type": "boolean",
    },
}

_PAGE_10: Dict[str, FieldDef] = {
    "credits_consommation.nom_creancier": {
        "description": "Nom du creancier du credit",
        "type": "string",
    },
    "credits_consommation.adresse_creancier": {
        "description": "Adresse du creancier du credit",
        "type": "string",
    },
    "credits_consommation.reference": {"description": "Reference du pret", "type": "string"},
    "credits_consommation.date_octroi": {
        "description": "Date d'octroi du credit",
        "type": "string",
        "format": "date",
    },
    "credits_consommation.capital_emprunte": {"description": "Capital emprunte", "type": "number"},
    "credits_consommation.taux": {
        "description": "Taux nominal ou debiteur annuel",
        "type": "string",
    },
    "credits_consommation.mensualite": {
        "description": "Montant de la mensualite",
        "type": "number",
    },
    "credits_consommation.restant_du": {"description": "Montant restant du", "type": "number"},
    "credits_consommation.montant_impaye": {
        "description": "Montant impaye du credit",
        "type": "number",
    },
    "credits_consommation.montant_exigible": {"description": "Montant exigible", "type": "number"},
    "credits_consommation.poursuites_oui": {
        "description": "Poursuites en cours relatives au credit",
        "type": "boolean",
    },
    "credits_consommation.poursuites_non": {
        "description": "Aucune poursuite relative au credit",
        "type": "boolean",
    },
}

#: Champs attendus par numero de page (1-indexe). Une page absente de cette
#: table ne porte aucun champ a extraire et n'est pas soumise a l'OCR.
CERFA_V2_PAGE_FIELDS: Dict[int, Dict[str, FieldDef]] = {
    1: _PAGE_1,
    2: _PAGE_2,
    6: _PAGE_6,
    10: _PAGE_10,
}
