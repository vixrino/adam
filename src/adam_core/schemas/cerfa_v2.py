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

Les types sont ceux du script d'origine, sauf la ou un CERFA reel les a mis
en defaut : code postal, escalier et etage passent en string, un number
perdant le zero initial d'un code postal (01500) et ne pouvant rendre un
escalier « B ». Les champs ajoutes depuis — nom des personnes a charge,
numero d'allocataire — l'ont ete d'apres le meme CERFA.
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
        "type": "string",
    },
    "coordonnees_personnelles.etage": {
        "description": "Champ Etage section coordonnees personnelles",
        "type": "string",
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
        "type": "string",
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
    "personnes_a_charge.lien_parente": {
        "description": (
            "Lien de parente avec le deposant (enfant, parent...), lu dans la "
            "colonne lien de parente ; jamais un nom de personne"
        ),
        "type": "string",
    },
    "personnes_a_charge.nom_prenom": {
        "description": "Nom et prenom de la personne vivant au domicile",
        "type": "string",
    },
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
    "prestations_familiales.numero_allocataire_deposant": {
        "description": (
            "Numero d'allocataire du deposant aupres de la caisse d'allocations "
            "familiales, rubrique prestations familiales"
        ),
        "type": "string",
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

#: Page 9, credits immobiliers. Meme tableau que la page 10, a deux colonnes
#: pres : le CERFA y demande l'assureur du pret et le montant mensuel de son
#: assurance, qui n'existent pas pour un credit a la consommation.
_PAGE_9: Dict[str, FieldDef] = {
    "credits_immobiliers.nom_creancier": {
        "description": "Nom du creancier du credit immobilier",
        "type": "string",
    },
    "credits_immobiliers.adresse_creancier": {
        "description": "Adresse du creancier du credit immobilier",
        "type": "string",
    },
    "credits_immobiliers.nom_assureur": {
        "description": "Nom et adresse de l'assureur du pret, si different du creancier",
        "type": "string",
    },
    "credits_immobiliers.reference": {
        "description": "Reference du pret immobilier",
        "type": "string",
    },
    "credits_immobiliers.date_octroi": {
        "description": "Date d'octroi du credit immobilier",
        "type": "string",
        "format": "date",
    },
    "credits_immobiliers.capital_emprunte": {
        "description": "Capital emprunte",
        "type": "number",
    },
    "credits_immobiliers.taux": {
        "description": "Taux nominal ou debiteur annuel",
        "type": "string",
    },
    "credits_immobiliers.mensualite": {
        "description": "Montant de la mensualite hors assurance",
        "type": "number",
    },
    "credits_immobiliers.assurance_mensuelle": {
        "description": "Montant mensuel de l'assurance du pret",
        "type": "number",
    },
    "credits_immobiliers.restant_du": {"description": "Montant restant du", "type": "number"},
    "credits_immobiliers.montant_impaye": {
        "description": "Montant impaye du credit immobilier",
        "type": "number",
    },
    "credits_immobiliers.montant_exigible": {
        "description": "Montant exigible",
        "type": "number",
    },
    "credits_immobiliers.poursuites_oui": {
        "description": "Poursuites en cours relatives au credit immobilier",
        "type": "boolean",
    },
    "credits_immobiliers.poursuites_non": {
        "description": "Aucune poursuite relative au credit immobilier",
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

# -- Pages 3, 4, 5, 7, 8 et 11 ----------------------------------------------
#
# Ajoutees d'apres un CERFA reel rempli, transcrit page par page. Une
# transcription ne rend que les lignes remplies : chaque champ ci-dessous est
# atteste sur ce CERFA, ou reprend une structure deja qualifiee (les colonnes
# des tableaux de dettes de la page 6). Les lignes laissees vides par le
# deposant — un poste de ressources non percu, par exemple — n'y figurent donc
# pas encore, et sont a relever sur un formulaire vierge.


def _personnes(prefixe: str, champs: Dict[str, FieldDef]) -> Dict[str, FieldDef]:
    """Double une rubrique a deux colonnes, deposant et co-deposant."""
    doubles: Dict[str, FieldDef] = {}
    for personne, colonne in (("deposant", "Deposant"), ("co_deposant", "Co-deposant")):
        for cle, spec in champs.items():
            doubles[f"{prefixe}.{personne}_{cle}"] = {
                **spec,
                "description": f"Colonne {colonne}. {spec['description']}",
            }
    return doubles


def _ressource(libelle: str) -> Dict[str, FieldDef]:
    """Une ligne de ressource : sa nature precisee a la main, puis son montant."""
    return {
        "nature": {
            "description": f"{libelle} : nature precisee a la main",
            "type": "string",
        },
        "montant": {"description": f"{libelle} : montant mensuel", "type": "number"},
    }


def _dettes(section: str, libelle: str) -> Dict[str, FieldDef]:
    """Colonnes d'un tableau de dettes, celles de la page 6."""
    return {
        f"{section}.nom_creancier": {
            "description": f"Nom du creancier, {libelle}",
            "type": "string",
        },
        f"{section}.adresse_creancier": {
            "description": f"Adresse du creancier, {libelle}",
            "type": "string",
        },
        f"{section}.reference": {"description": f"Reference, {libelle}", "type": "string"},
        f"{section}.montant_impaye": {
            "description": f"Montant impaye, {libelle}",
            "type": "number",
        },
        f"{section}.poursuites_oui": {
            "description": f"Poursuites en cours, {libelle}",
            "type": "boolean",
        },
        f"{section}.poursuites_non": {
            "description": f"Aucune poursuite, {libelle}",
            "type": "boolean",
        },
    }


#: Page 3, situation professionnelle et ressources. Sur le CERFA de test :
#: statut « Autre », precise « Invalidite », depuis 2019 ; reversion 493,21,
#: prevoyance 458,37, indemnites journalieres d'invalidite 838,88.
_PAGE_3: Dict[str, FieldDef] = {
    **_personnes(
        "situation_professionnelle",
        {
            "statut": {
                "description": "Libelle de la case cochee pour le statut professionnel",
                "type": "string",
            },
            "statut_precision": {
                "description": "Precision ecrite a cote de la case Autre du statut professionnel",
                "type": "string",
            },
            "depuis": {
                "description": "Date depuis laquelle dure la situation professionnelle",
                "type": "string",
                "format": "date",
            },
        },
    ),
    **_personnes(
        "ressources_mensuelles",
        {
            **{f"autres_pensions_{k}": v for k, v in _ressource("Autres pensions").items()},
            **{f"autres_allocations_{k}": v for k, v in _ressource("Autres allocations").items()},
            **{
                f"indemnites_journalieres_{k}": v
                for k, v in _ressource("Indemnites journalieres").items()
            },
        },
    ),
}

#: Page 4, charges, gestion du budget et vehicules. La rubrique gestion du
#: budget etait masquee sur le CERFA de test : aucun champ n'en est releve.
_PAGE_4: Dict[str, FieldDef] = {
    **_personnes(
        "charges_mensuelles",
        {"loyer": {"description": "Loyer mensuel", "type": "number"}},
    ),
    "vehicules.type": {"description": "Type ou modele du vehicule", "type": "string"},
    "vehicules.loa_lld_oui": {
        "description": "Vehicule en location avec option d'achat (LOA) ou LLD : oui",
        "type": "boolean",
    },
    "vehicules.loa_lld_non": {
        "description": "Vehicule en location avec option d'achat (LOA) ou LLD : non",
        "type": "boolean",
    },
}

#: Page 5, patrimoine. Seule la case d'absence de patrimoine est attestee.
_PAGE_5: Dict[str, FieldDef] = {
    "patrimoine.aucun": {
        "description": "Case « si vous n'avez pas de patrimoine cochez cette case »",
        "type": "boolean",
    },
}

#: Page 7, dettes diverses et dettes de pension alimentaire ou d'amendes.
_PAGE_7: Dict[str, FieldDef] = {
    **_dettes("dettes_diverses", "dette diverse"),
    **_dettes("dettes_pension_amendes", "dette de pension alimentaire ou amende"),
}

#: Page 8, decouverts bancaires et locations diverses.
_PAGE_8: Dict[str, FieldDef] = {
    **_dettes("decouverts_bancaires", "decouvert bancaire"),
    **_dettes("locations_diverses", "location diverse"),
}

#: Page 11. La suite du tableau des credits a la consommation (prets 7 et 8)
#: n'y est pas declaree : ses cles sont celles de la page 10, et deux pages ne
#: peuvent porter la meme cle tant que les repetables (T7) ne sont pas la.
_PAGE_11: Dict[str, FieldDef] = {
    **_dettes("autres_prets_cautionnements", "autre pret ou cautionnement"),
    "cause_surendettement.texte": {
        "description": "Cause de la situation de surendettement, telle qu'ecrite",
        "type": "string",
    },
}

#: Champs attendus par numero de page (1-indexe). La page 12, avertissement
#: portant l'adresse de renvoi du dossier, n'en a aucun.
CERFA_V2_PAGE_FIELDS: Dict[int, Dict[str, FieldDef]] = {
    1: _PAGE_1,
    2: _PAGE_2,
    3: _PAGE_3,
    4: _PAGE_4,
    5: _PAGE_5,
    6: _PAGE_6,
    7: _PAGE_7,
    8: _PAGE_8,
    9: _PAGE_9,
    10: _PAGE_10,
    11: _PAGE_11,
}

#: Rubriques imprimees de chaque page, pour reconnaitre une page a son contenu
#: et non a son rang : un CERFA reel est arrive pages 9 et 10 inversees.
#: Releves sur ce CERFA, pages 1 a 12.
#: Les pages 10 et 11 ouvrent sur le meme titre ; la page 11 seule porte
#: ensuite les rubriques autres prets et cause du surendettement. Les pages sans
#: champs y figurent aussi : les reconnaitre permet de distinguer une page
#: deplacee d'une page etrangere au formulaire.
CERFA_V2_PAGE_TITLES: Dict[int, str] = {
    1: (
        "Deposant ; Co-deposant ; Coordonnees personnelles ; Vous etes assiste(e) "
        "par un travailleur social ; Declaration sur l'honneur"
    ),
    2: (
        "Vous avez deja depose un dossier de surendettement ; Situation familiale "
        "actuelle ; Enfant(s) et/ou autre(s) personne(s) vivant a votre domicile ; "
        "Situation logement ; Prestations familiales"
    ),
    3: "Situation professionnelle ; Montant des ressources mensuelles",
    4: "Montant des charges mensuelles ; Gestion du budget ; Vehicule(s)",
    5: "Patrimoine",
    6: (
        "Dettes de logement ; Dettes de charges courantes (impots, EDF, dettes "
        "sociales, assurances...)"
    ),
    7: "Dettes diverses ; Dettes de pension alimentaire, amendes",
    8: "Decouverts bancaires ; Locations diverses",
    9: (
        "Credits immobiliers. Tableau de prets avec les colonnes assureur du pret "
        "et montant mensuel de l'assurance"
    ),
    10: (
        "Credits a la consommation (credits renouvelables, prets personnels...), "
        "et aucune autre rubrique"
    ),
    11: (
        "Credits a la consommation (suite du tableau de la page 10) ; Autres "
        "prets et cautionnements ; Cause de votre situation de surendettement"
    ),
    12: "Avertissement : adresse a laquelle renvoyer le dossier",
}
