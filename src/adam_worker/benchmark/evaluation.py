"""Evaluation d'un document : la lecture du moteur contre la verite terrain.

Fonction pure : elle recoit la verite (les document_field du document) et la
sortie du connecteur, et rend les ecarts a ecrire, les compteurs et les
agregats par champ. Aucune base, aucun reseau : le worker fait les entrees
et sorties, cette fonction fait le calcul, et se teste seule.

Le rapprochement lecture -> champ reutilise le merger de la pre-alimentation :
c'est la meme question (quelle valeur OCR pour quel FIELD_SPEC et quelle
ligne de tableau), et deux reponses differentes mesureraient un rapprochement
qui n'est pas celui de la production.

Denominateur honnete (T1)
-------------------------
Seuls les champs portant au moins une field_proposal sont compares : un champ
jamais relu par un humain a resolved_value == ocr_value par construction, et le
compter mesurerait le moteur contre lui-meme. Les autres sont comptes dans
fields_compared (le perimetre), pas dans fields_human_verified (le
denominateur), et ne produisent jamais d'ecart.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from adam_core.schemas.interface_contract import SmartdocDocument
from adam_worker.benchmark.comparateur import comparer, empreinte
from adam_worker.prepopulation.merger import index_ocr_pairs, merge, semantic_key


@dataclass(frozen=True)
class ChampVerite:
    """Un document_field du perimetre, avec ce qu'il faut pour le juger."""

    document_field_id: int
    field_spec_id: int
    section_id: str
    field_key: str
    group_id: Optional[str]
    value_type: str
    sensitive: bool
    #: resolved_value : la valeur retenue apres relecture humaine.
    attendu: Optional[str]
    #: Au moins une field_proposal : le champ a ete regarde par un humain.
    verifie: bool

    @property
    def cle(self) -> str:
        return semantic_key(self.section_id, self.field_key)

    @property
    def libelle(self) -> str:
        """Libelle fige du rapport : la cle, et la ligne pour un repetable."""
        return f"{self.cle}[{self.group_id}]" if self.group_id else self.cle


@dataclass
class Agregat:
    field_key: str
    compared: int = 0
    diff_count: int = 0


@dataclass
class ResultatDocument:
    """Ce qu'un document ajoute a l'execution."""

    ecarts: List[Dict[str, Any]] = field(default_factory=list)
    fields_compared: int = 0
    fields_human_verified: int = 0
    unexpected_count: int = 0
    #: field_spec_id -> agregat du champ pour ce document.
    agregats: Dict[int, Agregat] = field(default_factory=dict)
    #: value_type -> tranche de confiance -> [corrects, ecarts].
    histogramme: Dict[str, Dict[str, List[int]]] = field(default_factory=dict)


def _tranche(confiance: float) -> str:
    return f"{round(float(confiance), 2):.2f}"


def _hors_schema(ocr: Optional[SmartdocDocument], verite: List[ChampVerite]) -> int:
    """Valeurs lues sous une cle qu'aucun champ du perimetre n'attend."""
    attendues: Set[Tuple[str, Optional[str]]] = set()
    for champ in verite:
        attendues.add((champ.cle, champ.group_id))
        # Une valeur sans instance peut remplir une ligne repetable (repli du merger).
        attendues.add((champ.cle, None))
    return sum(
        1
        for cle, kv in index_ocr_pairs(ocr).items()
        if kv.value is not None and cle not in attendues
    )


def evaluer_document(
    verite: List[ChampVerite],
    ocr: Optional[SmartdocDocument],
    execution_id: int,
    cle_hmac: str,
) -> ResultatDocument:
    """Compare la lecture du moteur a la verite d'un document."""
    resultat = ResultatDocument(unexpected_count=_hors_schema(ocr, verite))
    specs = [
        {
            "id": champ.field_spec_id,
            "section_id": champ.section_id,
            "field_key": champ.field_key,
            "group_id": champ.group_id,
            "polygon": None,
        }
        for champ in verite
    ]
    lectures = merge(specs, ocr)
    histogramme: Dict[str, Dict[str, List[int]]] = defaultdict(dict)
    # Un moteur sans confiance par champ (Mistral) laisse la valeur par defaut
    # du contrat, 1.0 : la compter ferait croire a un moteur toujours certain,
    # et fausserait le seuil d'auto-validation que l'histogramme doit fixer.
    confiance_fournie = ocr is None or ocr.metadata.get("confidence_fournie", True)

    for champ, lecture in zip(verite, lectures):
        resultat.fields_compared += 1
        if not champ.verifie:
            continue
        resultat.fields_human_verified += 1
        agregat = resultat.agregats.setdefault(champ.field_spec_id, Agregat(champ.libelle))
        agregat.compared += 1

        lu = lecture.get("ocr_value")
        confiance = lecture.get("ocr_confidence") if confiance_fournie else None
        ecart = comparer(champ.attendu, lu, champ.value_type)
        if confiance is not None:
            compte = histogramme[champ.value_type].setdefault(_tranche(confiance), [0, 0])
            compte[1 if ecart else 0] += 1
        if ecart is None:
            continue

        agregat.diff_count += 1
        resultat.ecarts.append(
            {
                "execution_id": execution_id,
                "document_field_id": champ.document_field_id,
                "verdict": ecart.verdict.value,
                "diff_kind": ecart.diff_kind.value if ecart.diff_kind else None,
                "ocr_confidence": confiance,
                # Sensible : rien en clair, l'empreinte et l'ampleur seulement.
                "expected_value": None if champ.sensitive else ecart.attendu,
                "observed_value": None if champ.sensitive else ecart.lu,
                "observed_hmac": empreinte(ecart.lu, cle_hmac) if champ.sensitive else None,
                "edit_distance": ecart.edit_distance,
            }
        )
    resultat.histogramme = dict(histogramme)
    return resultat


def fusionner_histogrammes(
    cumul: Dict[str, Dict[str, List[int]]], ajout: Dict[str, Dict[str, List[int]]]
) -> None:
    """Ajoute l'histogramme d'un document a celui de l'execution, en place."""
    for value_type, tranches in ajout.items():
        cible = cumul.setdefault(value_type, {})
        for tranche, (corrects, ecarts) in tranches.items():
            courant = cible.setdefault(tranche, [0, 0])
            courant[0] += corrects
            courant[1] += ecarts
