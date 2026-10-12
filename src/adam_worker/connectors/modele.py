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

Les champs repetables (FIELD_SPEC de meme cle sur plusieurs group_id) n'y
figurent qu'une fois : la repetition ne change rien a ce qu'on demande au
moteur, seulement au depliage de sa reponse (ticket T7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

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
    #: Numero de page -> cle semantique -> propriete du json_schema.
    champs: Mapping[int, Mapping[str, FieldDef]] = field(default_factory=dict)

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
        for spec in schema.get("field_specs") or []:
            cle = semantic_key(spec.get("section_id"), spec["field_key"])
            page = champs.setdefault(int(spec["page"]), {})
            # Premiere instance d'un champ repetable : les suivantes portent
            # la meme cle et ne changent rien a la demande.
            page.setdefault(cle, propriete(spec))
        return cls(nom=str(schema.get("name") or "formulaire"), pages=pages, champs=champs)


def propriete(spec: Mapping[str, Any]) -> FieldDef:
    """Propriete du json_schema d'annotation pour un FIELD_SPEC.

    La description vient de field_spec.description, faite pour le moteur ; a
    defaut, de display_label, fait pour l'ecran.
    """
    description = spec.get("description") or spec.get("display_label") or spec["field_key"]
    value_type = str(spec.get("value_type") or FieldValueType.TEXT.value).upper()
    if value_type == FieldValueType.BOOLEAN.value:
        return {"description": description, "type": "boolean"}
    if value_type == FieldValueType.NUMBER.value:
        return {"description": description, "type": "number"}
    if value_type in (FieldValueType.DATE.value, FieldValueType.DATETIME.value):
        return {"description": description, "type": "string", "format": "date"}
    return {"description": description, "type": "string"}
