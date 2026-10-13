"""Modele d'un type de document, tel que l'extraction OCR le consomme.

Le connecteur Mistral lisait les champs et les pages d'un module Python fige
pour le CERFA (cerfa_v2). Il recoit desormais ce modele, construit a partir du
schema du dataset en base (DOC_SCHEMA, ses SCHEMA_PAGE et ses FIELD_SPEC) :
ajouter un type de document, c'est creer un schema, pas ecrire du code.

Le modele porte trois choses :
- le nom du schema, qui dit au moteur quel formulaire il lit ;
- la description de chaque page, qui sert a reconnaitre une page a son
  contenu et a remettre en ordre un document scanne dans le desordre ;
- les champs de chaque page, sous la forme des proprietes du json_schema
  d'annotation, indexes par leur cle semantique "section.champ" — celle que
  le merger rapproche ensuite des FIELD_SPEC.

Champs repetables (ticket T7)
-----------------------------
Un tableau a plusieurs lignes identiques (prets n° 1 a 6) a une FIELD_SPEC par
ligne, distinguee par group_id. Le moteur recoit une propriete par ligne, dont
le nom porte l'instance : "credits_consommation.pret_2.reference". Le schema
reste plat — le mode strict de Mistral exige `required` complet a chaque
niveau, et un tableau d'objets ne fixerait ni le nombre ni le rang des lignes.

Ce nom n'est qu'une cle d'appel : la reponse est redecoupee en
id="credits_consommation.reference" et group_id="pret_2", la forme du contrat
(KVPair.group_id), que le merger rapproche de la bonne ligne.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from adam_core.enums.status import FieldValueType
from adam_worker.prepopulation.merger import semantic_key

#: Une entree par champ : description, type JSON Schema, format optionnel.
FieldDef = Mapping[str, Any]


@dataclass(frozen=True)
class ModeleDocument:
    """Ce que le moteur doit savoir d'un type de document pour l'extraire."""

    nom: str
    #: Numero de page -> description (titres de rubrique imprimes).
    pages: Mapping[int, str] = field(default_factory=dict)
    #: Numero de page -> cle d'appel -> propriete du json_schema. La cle
    #: d'appel est la cle semantique, avec l'instance pour un repetable.
    champs: Mapping[int, Mapping[str, FieldDef]] = field(default_factory=dict)
    #: Cle d'appel d'un champ repetable -> (cle semantique, group_id). Une cle
    #: absente d'ici est un champ simple : elle est sa propre cle semantique.
    instances: Mapping[str, Tuple[str, str]] = field(default_factory=dict)

    def cible(self, cle_appel: str) -> Tuple[str, Optional[str]]:
        """(cle semantique, group_id) que remplit une propriete de la reponse."""
        if cle_appel in self.instances:
            return self.instances[cle_appel]
        return cle_appel, None

    @property
    def nombre_pages(self) -> int:
        """Nombre de pages du formulaire, d'apres les pages decrites et les champs."""
        return max([*self.pages, *self.champs], default=0)

    @classmethod
    def depuis_schema(cls, schema: Mapping[str, Any]) -> "ModeleDocument":
        """Construit le modele depuis un schema tel que GET /schemas/{id} le rend."""
        pages = {
            int(p["page_number"]): str(p["description"])
            for p in schema.get("pages") or []
            if p.get("description")
        }
        champs: Dict[int, Dict[str, FieldDef]] = {}
        instances: Dict[str, Tuple[str, str]] = {}
        for spec in schema.get("field_specs") or []:
            cle = semantic_key(spec.get("section_id"), spec["field_key"])
            group_id = spec.get("group_id")
            page = champs.setdefault(int(spec["page"]), {})
            if not group_id:
                page.setdefault(cle, propriete(spec))
                continue
            cle_appel = cle_d_appel(cle, group_id)
            page.setdefault(cle_appel, propriete(spec, group_id))
            instances[cle_appel] = (cle, group_id)
        return cls(
            nom=str(schema.get("name") or "formulaire"),
            pages=pages,
            champs=champs,
            instances=instances,
        )


def cle_d_appel(cle: str, group_id: str) -> str:
    """Nom de propriete d'une instance : l'instance s'insere apres la section.

    "credits_consommation.reference" + "pret_2" donne
    "credits_consommation.pret_2.reference".
    """
    section, _, reste = cle.partition(".")
    return f"{section}.{group_id}.{reste}" if reste else f"{group_id}.{section}"


def propriete(spec: Mapping[str, Any], group_id: Optional[str] = None) -> FieldDef:
    """Propriete du json_schema d'annotation pour un FIELD_SPEC.

    La description vient de field_spec.description, faite pour le moteur ; a
    defaut, de display_label, fait pour l'ecran. Pour une ligne de tableau,
    elle dit laquelle : c'est le numero imprime de la ligne qui la designe.
    """
    description = spec.get("description") or spec.get("display_label") or spec["field_key"]
    if group_id:
        numero = re.search(r"(\d+)$", group_id)
        ligne = f"ligne n° {numero.group(1)} du tableau" if numero else f"instance {group_id}"
        description = f"{description} ({ligne})"
    value_type = str(spec.get("value_type") or FieldValueType.TEXT.value).upper()
    if value_type == FieldValueType.BOOLEAN.value:
        return {"description": description, "type": "boolean"}
    if value_type == FieldValueType.NUMBER.value:
        return {"description": description, "type": "number"}
    if value_type in (FieldValueType.DATE.value, FieldValueType.DATETIME.value):
        return {"description": description, "type": "string", "format": "date"}
    return {"description": description, "type": "string"}
