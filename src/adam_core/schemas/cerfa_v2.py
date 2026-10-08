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

_COLONNES = (("deposant", "Deposant"), ("co_deposant", "Co-deposant"))


def _colonnes(prefixe: str, champs: Mapping[str, FieldDef]) -> Dict[str, FieldDef]:
    """Double une rubrique a deux colonnes, deposant et co-deposant."""
    doubles: Dict[str, FieldDef] = {}
    for personne, colonne in _COLONNES:
        for cle, spec in champs.items():
            doubles[f"{prefixe}.{personne}_{cle}"] = {
                **spec,
                "description": f"Colonne {colonne}. {spec['description']}",
            }
    return doubles


def _montant(libelle: str) -> FieldDef:
    return {"description": f"{libelle} : montant mensuel", "type": "number"}


def _nature(libelle: str) -> FieldDef:
    return {"description": f"{libelle} : nature precisee a la main", "type": "string"}


def _oui_non(prefixe: str, question: str) -> Dict[str, FieldDef]:
    return {
        f"{prefixe}_oui": {"description": f"{question} : oui", "type": "boolean"},
        f"{prefixe}_non": {"description": f"{question} : non", "type": "boolean"},
    }


def _poursuites(section: str, objet: str) -> Dict[str, FieldDef]:
    return _oui_non(f"{section}.poursuites", f"Faites-vous l'objet de poursuites, {objet}")


def _dettes(section: str, objet: str, montant: str = "Montant impaye") -> Dict[str, FieldDef]:
    """Tableau de dettes des pages 6 et 7 : creancier, reference, montant, poursuites."""
    return {
        f"{section}.nom_creancier": {"description": f"Nom du creancier, {objet}", "type": "string"},
        f"{section}.adresse_creancier": {
            "description": f"Adresse du creancier, {objet}",
            "type": "string",
        },
        f"{section}.reference": {
            "description": f"Reference de la dette, {objet}",
            "type": "string",
        },
        f"{section}.montant_impaye": {"description": f"{montant}, {objet}", "type": "number"},
        **_poursuites(section, objet),
    }


def _credit(section: str, objet: str) -> Dict[str, FieldDef]:
    """Colonnes d'un tableau de credits sans assurance (pages 10 et 11)."""
    return {
        f"{section}.nom_creancier": {"description": f"Nom du creancier, {objet}", "type": "string"},
        f"{section}.adresse_creancier": {
            "description": f"Adresse du creancier, {objet}",
            "type": "string",
        },
        f"{section}.reference": {"description": f"Reference du pret, {objet}", "type": "string"},
        f"{section}.date_octroi": {
            "description": f"Date d'octroi, {objet}",
            "type": "string",
            "format": "date",
        },
        f"{section}.capital_emprunte": {
            "description": f"Capital emprunte, {objet}",
            "type": "number",
        },
        f"{section}.taux": {
            "description": f"Taux nominal ou debiteur annuel, {objet}",
            "type": "string",
        },
        f"{section}.mensualite": {"description": f"Mensualite, {objet}", "type": "number"},
        f"{section}.restant_du": {"description": f"Restant du, {objet}", "type": "number"},
        f"{section}.montant_impaye": {"description": f"Montant impaye, {objet}", "type": "number"},
        f"{section}.montant_exigible": {
            "description": f"Montant exigible, {objet}",
            "type": "number",
        },
        **_poursuites(section, objet),
    }


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
            "Contenu de la colonne lien de parente, recopie tel qu'ecrit : le "
            "tableau n'a pas de colonne pour le nom, et un deposant y ecrit "
            "parfois le nom de la personne plutot que le lien"
        ),
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
    **{
        f"situation_logement_{personne}.{cle}": {
            **spec,
            "description": f"Colonne {colonne}. {spec['description']}",
        }
        for personne, colonne in _COLONNES
        for cle, spec in {
            "locataire": {"description": "Case Locataire", "type": "boolean"},
            **_oui_non("expulsion", "Faites-vous l'objet d'une procedure d'expulsion"),
            "proprietaire": {"description": "Case Proprietaire", "type": "boolean"},
            **_oui_non("saisie_immobiliere", "Faites-vous l'objet d'une saisie immobiliere"),
            "heberge": {"description": "Case Heberge", "type": "boolean"},
            "occupant_gratuit": {
                "description": "Case Occupant a titre gratuit",
                "type": "boolean",
            },
            "sans_domicile_fixe": {"description": "Case Sans domicile fixe", "type": "boolean"},
            "maison_retraite": {"description": "Case En maison de retraite", "type": "boolean"},
            "autres_cas": {
                "description": "Case Autres cas (mobil-home, famille d'accueil...)",
                "type": "boolean",
            },
        }.items()
    },
    **_colonnes(
        "prestations_familiales",
        {
            "caf_numero_allocataire": {
                "description": "Numero d'allocataire de la caisse d'allocations familiales",
                "type": "string",
            },
            "msa_numero_allocataire": {
                "description": "Numero d'allocataire de la mutualite sociale agricole",
                "type": "string",
            },
        },
    ),
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

# -- Pages 3 a 11 ------------------------------------------------------------
#
# Releves sur le CERFA vierge publie par la Banque de France (300 BdF 1947 -
# DIRCOM - 30/04/2020), recoupe avec la transcription d'un CERFA reel rempli.

_STATUTS = {
    "cdi": "Salarie en CDI",
    "cdd": "Salarie en CDD",
    "interimaire": "Salarie interimaire",
    "retraite": "Retraite",
    "conge_parental": "En conge parental",
    "demandeur_emploi": "Demandeur d'emploi",
    "etudiant": "Etudiant",
    "sans_activite": "Sans activite",
    "autre": "Autre",
}

#: Lignes de ressources ; True quand la ligne porte une nature ecrite a la main
#: (« Autres pensions : Reversion »).
_RESSOURCES = {
    "salaire": ("Salaire", False),
    "retraite": ("Retraite", False),
    "pension_alimentaire_recue": ("Pension alimentaire recue", False),
    "autres_pensions": ("Autres pensions", True),
    "allocations_chomage": ("Allocations chomage", False),
    "allocation_logement": ("Allocation logement / APL", False),
    "allocations_familiales": ("Allocations familiales", False),
    "allocation_solidarite_specifique": ("Allocation specifique de solidarite", False),
    "rsa": ("Revenu de solidarite active", False),
    "autres_allocations": ("Autres allocations", True),
    "rente_viagere": ("Rente viagere", False),
    "autres_rentes": ("Autres rentes", True),
    "indemnites_journalieres": ("Indemnites journalieres", True),
    "revenus_fonciers": ("Revenus fonciers", False),
    "revenus_capitaux_mobiliers": ("Revenus de valeurs et capitaux mobiliers", False),
    "autres_ressources": ("Autres ressources", True),
}

_CHARGES = {
    "loyer": "Loyer",
    "charges_copropriete": "Charges de copropriete",
    "frais_maison_retraite": "Frais de maison de retraite ou autres",
    "impot_revenu": "Impots sur le revenu",
    "taxe_habitation": "Taxe d'habitation",
    "taxe_fonciere": "Taxe fonciere",
    "pension_alimentaire_versee": "Pension alimentaire versee",
    "mutuelle": "Mutuelle",
    "chauffage": "Chauffage",
    "frais_garde": "Frais de garde",
    "frais_scolarite": "Frais de scolarite",
    "frais_transport_professionnels": "Frais de transport professionnels",
    "autres_charges": "Autres charges et frais divers",
}

_BIENS_IMMOBILIERS = {
    "residence_principale": "Residence principale",
    "autre_bien_1": "Autre bien immobilier (premiere ligne)",
    "autre_bien_2": "Autre bien immobilier (seconde ligne)",
    "terrain": "Terrain",
    "mobil_home": "Mobil-home - caravane",
    "garage": "Garage - parking",
    "autre": "Autres a preciser",
}

_EPARGNE = {
    "pel": "Plan d'epargne logement (PEL)",
    "livret_a": "Livret A",
    "ldd": "Livret de developpement durable (LDD)",
    "lep": "Livret d'epargne populaire (LEP)",
    "cel": "Compte epargne logement (CEL)",
    "pea": "Plan d'epargne en action (PEA)",
    "pee": "Plan d'epargne entreprise (PEE)",
    "per": "Plan d'epargne retraite (PERP ou PERCO)",
    "assurance_vie": "Assurance-vie",
    "parts_sci": "Parts de SCI",
}

#: Page 3, situation professionnelle et ressources mensuelles. Une seule case
#: de statut est cochee par colonne : sa date « depuis le » est relevee seule.
_PAGE_3: Dict[str, FieldDef] = {
    **_colonnes(
        "situation_professionnelle",
        {
            "profession": {
                "description": "Profession ou dernier emploi occupe",
                "type": "string",
            },
            "qualification": {"description": "Qualification", "type": "string"},
            **{
                f"statut_{cle}": {"description": f"Case {libelle}", "type": "boolean"}
                for cle, libelle in _STATUTS.items()
            },
            "statut_autre_precision": {
                "description": "Precision ecrite a cote de la case Autre",
                "type": "string",
            },
            "depuis": {
                "description": "Date « depuis le » en face de la case de statut cochee",
                "type": "string",
                "format": "date",
            },
        },
    ),
    **_colonnes(
        "ressources_mensuelles",
        {
            champ: spec
            for cle, (libelle, a_nature) in _RESSOURCES.items()
            for champ, spec in ([(f"{cle}_nature", _nature(libelle))] if a_nature else [])
            + [(cle, _montant(libelle))]
        },
    ),
}

#: Page 4, charges, vehicules et gestion du budget.
_PAGE_4: Dict[str, FieldDef] = {
    **_colonnes(
        "charges_mensuelles", {cle: _montant(libelle) for cle, libelle in _CHARGES.items()}
    ),
    "vehicules.type": {"description": "Type de vehicule", "type": "string"},
    **_oui_non(
        "vehicules.loa_lld",
        "Location avec option d'achat (LOA) ou location longue duree (LLD)",
    ),
    "vehicules.valeur_estimee": {
        "description": "Valeur estimee en euros, si la case LOA/LLD non est cochee",
        "type": "number",
    },
    **_oui_non("gestion_budget.compte_bancaire", "Avez-vous au moins un compte bancaire"),
    "gestion_budget.iban": {
        "description": "IBAN des comptes declares, tels qu'ecrits",
        "type": "string",
    },
}

#: Page 5, patrimoine : immobilier, epargne, autre patrimoine.
_PAGE_5: Dict[str, FieldDef] = {
    **{
        champ: spec
        for cle, libelle in _BIENS_IMMOBILIERS.items()
        for champ, spec in {
            f"patrimoine_immobilier.{cle}_valeur": {
                "description": f"{libelle} : valeur estimee en euros",
                "type": "number",
            },
            **_oui_non(
                f"patrimoine_immobilier.{cle}_indivision", f"{libelle} : bien en indivision"
            ),
        }.items()
    },
    "patrimoine_immobilier.autre_precision": {
        "description": "Nature du bien ecrite a cote de « Autres a preciser »",
        "type": "string",
    },
    **_colonnes(
        "epargne",
        {
            cle: {"description": f"{libelle} : montant", "type": "number"}
            for cle, libelle in _EPARGNE.items()
        },
    ),
    "patrimoine.autre_precision": {
        "description": "Autre patrimoine (bijoux, tableaux, bateau...) : precision",
        "type": "string",
    },
    "patrimoine.aucun": {
        "description": "Case « si vous n'avez pas de patrimoine cochez cette case »",
        "type": "boolean",
    },
}

#: Page 7, dettes diverses ; dettes de pension alimentaire, amendes,
#: condamnations penales et dettes frauduleuses.
_PAGE_7: Dict[str, FieldDef] = {
    **_dettes("dettes_diverses", "dette diverse (avocat, factures, cheques impayes)"),
    **_dettes(
        "dettes_pension_amendes",
        "dette de pension alimentaire, amende, condamnation penale ou dette frauduleuse",
    ),
}

#: Page 8, decouverts bancaires et locations diverses (LOA, LLD...).
_PAGE_8: Dict[str, FieldDef] = {
    "decouverts_bancaires.nom_banque": {"description": "Nom de la banque", "type": "string"},
    "decouverts_bancaires.adresse_banque": {
        "description": "Adresse de la banque",
        "type": "string",
    },
    "decouverts_bancaires.reference_compte": {
        "description": "Reference du compte",
        "type": "string",
    },
    "decouverts_bancaires.montant_decouvert": {
        "description": "Montant du decouvert utilise",
        "type": "number",
    },
    **_poursuites("decouverts_bancaires", "decouvert bancaire"),
    "locations_diverses.nom_creancier": {
        "description": "Nom du creancier de la location",
        "type": "string",
    },
    "locations_diverses.adresse_creancier": {
        "description": "Adresse du creancier de la location",
        "type": "string",
    },
    "locations_diverses.reference_contrat": {
        "description": "Reference du contrat de location",
        "type": "string",
    },
    "locations_diverses.date_debut": {
        "description": "Date de debut du contrat de location",
        "type": "string",
        "format": "date",
    },
    "locations_diverses.nombre_loyers": {
        "description": "Nombre de loyers prevus au contrat",
        "type": "number",
    },
    "locations_diverses.loyer_mensuel": {
        "description": "Montant du loyer mensuel",
        "type": "number",
    },
    "locations_diverses.montant_impayes": {
        "description": "Montant des impayes de la location",
        "type": "number",
    },
    "locations_diverses.solde_apres_vente": {
        "description": "Montant du solde apres-vente",
        "type": "number",
    },
    **_poursuites("locations_diverses", "location"),
}

#: Page 11. La suite du tableau des credits a la consommation (prets 7 et 8)
#: n'y est pas declaree : ses cles sont celles de la page 10, et deux pages ne
#: peuvent porter la meme cle tant que les repetables (T7) ne sont pas la.
_PAGE_11: Dict[str, FieldDef] = {
    "cause_surendettement.texte": {
        "description": "Cause principale du depot du dossier, telle qu'ecrite",
        "type": "string",
    },
    **_credit("autres_prets", "autre pret (pret familial, employeur, CAF...)"),
    "cautionnement.nom_creancier": {
        "description": "Nom du creancier de la dette cautionnee",
        "type": "string",
    },
    "cautionnement.adresse_creancier": {
        "description": "Adresse du creancier de la dette cautionnee",
        "type": "string",
    },
    "cautionnement.reference": {
        "description": "Reference de la dette cautionnee",
        "type": "string",
    },
    "cautionnement.montant_reclame": {
        "description": "Montant reclame au titre de la caution",
        "type": "number",
    },
    "cautionnement.personne_cautionnee": {
        "description": "Nom de la personne ou de la societe cautionnee",
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
#: Releves sur le CERFA vierge de la Banque de France, qui imprime aussi
#: « page N/12 » en tete de chaque page. Les pages 10 et 11 portent toutes deux
#: les credits a la consommation ; la page 11 s'ouvre sur la cause du
#: surendettement et porte ensuite autres prets et cautionnement. Les pages sans
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
    4: "Montant des charges mensuelles ; Vehicule(s) ; Gestion du budget",
    5: "Patrimoine",
    6: (
        "Dettes de logement ; Dettes de charges courantes (impots, EDF, dettes "
        "sociales, assurances...)"
    ),
    7: (
        "Dettes diverses (avocat, factures diverses, cheques impayes...) ; Dettes "
        "de pension alimentaire/Amendes/Condamnations penales/Dettes frauduleuses"
    ),
    8: (
        "Decouverts bancaires ; Locations diverses (locations avec option "
        "d'achat, locations longue duree...)"
    ),
    9: (
        "Credits immobiliers. Tableau de prets avec les colonnes assureur du pret "
        "et montant mensuel de l'assurance"
    ),
    10: (
        "Credits a la consommation (credits renouvelables, prets personnels...), "
        "et aucune autre rubrique"
    ),
    11: (
        "Cause de votre situation de surendettement ; Credits a la consommation, "
        "prets n° 7 et 8 ; Autres prets (prets familiaux, pret employeur, pret "
        "CAF...) ; Cautionnement"
    ),
    12: "Avertissement : adresse a laquelle renvoyer le dossier",
}
