"""Fusion d'une reponse OCR avec le schema de champs attendu.

Fonction pure, sans base ni HTTP : elle prend les FieldSpec du schema et le
SmartdocDocument rendu par le connecteur, et produit la liste des champs a
creer. C'est la seule regle metier du sous-module, et elle se teste seule.

Le schema commande, pas l'OCR
------------------------------
On itere sur les FieldSpec, jamais sur les KVPair de la reponse. Un document
pre-alimente doit porter exactement les champs que son schema declare : ni un
de moins parce que l'OCR ne l'a pas vu, ni un de plus parce que l'OCR a detecte
autre chose. Un champ non detecte existe donc, vide, et l'operateur le saisira.

Trois cas, un seul chemin
--------------------------
    champ detecte       ocr_value renseignee, confiance et polygone de l'OCR
    champ non detecte   valeurs nulles, polygone du schema en repli
    OCR indisponible    identique au precedent pour tous les champs

Le troisieme n'est pas un cas particulier : un OCR absent est un OCR qui n'a
rien detecte, et le code n'a donc pas de branche dediee.

resolved_by
-----------
Pose a "ocr_system" uniquement quand une valeur vient de l'OCR. Un champ vide
n'a pas de resolveur : marquer "ocr_system" dessus laisserait croire que l'OCR
l'a traite alors qu'il ne l'a pas trouve. Ce champ sera ecrase par un
FIELD_PROPOSAL des qu'un operateur soumettra une correction.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from adam_core.enums.status import DocumentFieldStatus
from adam_core.schemas.interface_contract import KVPair, SmartdocDocument

#: Valeur de DocumentField.resolved_by pour une valeur issue de l'OCR.
OCR_RESOLVER = "ocr_system"


def semantic_key(section_id: Optional[str], field_key: str) -> str:
    """Cle "section.champ" utilisee pour rapprocher un FieldSpec d'un KVPair.

    Le contrat OCR identifie un champ par un `id` pointe, "deposant.nom". Cote
    schema, la convention n'est pas uniforme : le seed stocke deja la cle
    complete dans field_key, tandis que d'autres sources n'y mettent que le
    dernier segment. On prefixe donc par section_id seulement si ce n'est pas
    deja fait, sinon on produirait "deposant.deposant.nom" et aucun champ ne
    serait jamais rapproche.
    """
    if not section_id or field_key.startswith(f"{section_id}."):
        return field_key
    return f"{section_id}.{field_key}"


#: Cle d'un KVPair : son identifiant pointe et l'instance qu'il remplit.
CleOcr = Tuple[str, Optional[str]]


def index_ocr_pairs(ocr: Optional[SmartdocDocument]) -> Dict[CleOcr, KVPair]:
    """Indexe les KVPair par (identifiant pointe, group_id).

    Le group_id est celui du contrat : une ligne d'un tableau repetable (pret
    n° 2) arrive avec id="credits_consommation.reference" et group_id="pret_2".
    Sans lui, les six prets d'un tableau partageraient une seule cle, et la
    valeur du premier finirait dans les six.

    En cas de cle repetee entre deux pages, le premier rencontre gagne : un
    champ vu deux fois est plus probablement une entete repetee qu'une seconde
    occurrence significative, et le contrat ne permet pas de trancher.
    """
    if ocr is None:
        return {}
    index: Dict[CleOcr, KVPair] = {}
    for _page_number, _section, kv in ocr.iter_kv_pairs():
        index.setdefault((kv.id, kv.group_id), kv)
    return index


def _payload_from_spec(spec: Mapping[str, Any], kv: Optional[KVPair]) -> Dict[str, Any]:
    """Construit le champ a creer pour un FieldSpec donne."""
    if kv is None or kv.value is None:
        # Champ non detecte : le polygone du schema sert de position par defaut,
        # pour que l'IHM sache ou afficher la zone a saisir.
        return {
            "field_spec_id": spec["id"],
            "group_id": spec.get("group_id"),
            "ocr_value": None,
            "resolved_value": None,
            "status": DocumentFieldStatus.PENDING.value,
            "ocr_confidence": None,
            "ocr_polygon": spec.get("polygon"),
            "resolved_by": None,
        }

    value = kv.extracted_value
    return {
        "field_spec_id": spec["id"],
        # group_id du schema d'abord : c'est lui qui definit la repetabilite,
        # celui de l'OCR n'est qu'une indication de regroupement visuel.
        "group_id": spec.get("group_id") or kv.group_id,
        "ocr_value": value,
        # Valeur initiale avant toute proposition humaine, comme le fait le seed.
        "resolved_value": value,
        "status": DocumentFieldStatus.PENDING.value,
        "ocr_confidence": kv.confidence,
        "ocr_polygon": kv.polygon or spec.get("polygon"),
        "resolved_by": OCR_RESOLVER if value is not None else None,
    }


def merge(
    field_specs: Sequence[Mapping[str, Any]],
    ocr: Optional[SmartdocDocument],
) -> List[Dict[str, Any]]:
    """Produit un champ a creer par FieldSpec du schema.

    Args:
        field_specs: les FieldSpecItemOut du schema, sous forme de mappings
            (tels que rendus par l'API), portant au moins `id`, `field_key`,
            `section_id`, et optionnellement `group_id` et `polygon`.
        ocr: la reponse du connecteur, ou None s'il n'a rien produit.

    Returns:
        La liste des champs, dans l'ordre du schema.
    """
    index = index_ocr_pairs(ocr)
    #: Cles dont la valeur sans instance a deja servi a une ligne repetable.
    replis_servis: Set[str] = set()
    payloads: List[Dict[str, Any]] = []
    for spec in field_specs:
        key = semantic_key(spec.get("section_id"), spec["field_key"])
        group_id = spec.get("group_id")
        kv = index.get((key, group_id))
        if kv is None and group_id is not None and key not in replis_servis:
            # Valeur rendue sans instance (connecteur qui ne connait pas les
            # repetables) : elle ne remplit que la premiere ligne du tableau.
            # La recopier dans toutes ferait croire a l'operateur que six prets
            # ont ete lus, alors qu'un seul l'a ete.
            kv = index.get((key, None))
            if kv is not None:
                replis_servis.add(key)
        payloads.append(_payload_from_spec(spec, kv))
    return payloads


def count_detected(payloads: Sequence[Mapping[str, Any]]) -> int:
    """Nombre de champs pour lesquels l'OCR a fourni une valeur.

    Sert aux logs : c'est la seule statistique publiable, les valeurs elles-memes
    ne devant jamais sortir (IBAN, NIR).
    """
    return sum(1 for payload in payloads if payload.get("ocr_value") is not None)
