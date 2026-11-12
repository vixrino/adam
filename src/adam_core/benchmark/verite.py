"""Empreinte de la verite humaine d'un document, pour le benchmark.

Un export fige la liste des documents, pas leurs valeurs (droit a
l'effacement : la verite reste dans document_field). Si un relecteur corrige
une valeur entre deux executions, l'ecart de score ne mesure plus seulement le
moteur. L'export garde donc une empreinte de la verite de chaque document, et
chaque execution celle de ce qu'elle a jugee : le worker signale un document
dont la verite a change depuis l'export, et la comparaison deux executions qui
n'ont pas juge la meme verite.

Seuls les champs verifies (au moins une field_proposal) entrent dans
l'empreinte : ce sont les seuls que le benchmark juge. Une re-pre-alimentation
OCR des champs jamais relus ne la change donc pas.

Calculee par l'API (a l'export) et par le worker (a l'execution) : les deux
doivent lire les memes lignes, d'ou une seule fonction de calcul.
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_core.models import DocumentField, FieldProposal

#: (field_spec_id, group_id, valeur retenue) d'un champ verifie.
ChampJuge = Tuple[int, Optional[str], Optional[str]]


def empreinte_document(champs: Iterable[ChampJuge]) -> str:
    """Empreinte des champs verifies d'un document, dans n'importe quel ordre.

    Un hash, pas les valeurs : un IBAN n'y est pas lisible, et l'empreinte ne
    sert qu'a dire « a change » ou « n'a pas change ».
    """
    # (vide ?, valeur) : None et "" restent distincts, et le tri ne compare
    # jamais None a une chaine.
    contenu = sorted((int(f), g or "", v is None, v or "") for f, g, v in champs)
    return hashlib.sha256(json.dumps(contenu, ensure_ascii=False).encode()).hexdigest()[:16]


def empreinte_verite(par_document: Mapping[int, str]) -> str:
    """Empreinte de la verite d'un lot de documents, a partir de celles de
    chaque document."""
    contenu = sorted((int(d), e) for d, e in par_document.items())
    return hashlib.sha256(json.dumps(contenu).encode()).hexdigest()[:16]


async def empreintes_documents(db: AsyncSession, document_ids: List[int]) -> Dict[int, str]:
    """Empreinte de la verite de chaque document, comme le worker la calcule."""
    if not document_ids:
        return {}
    verifie = exists().where(FieldProposal.document_field_id == DocumentField.id)
    lignes = (
        await db.execute(
            select(
                DocumentField.document_id,
                DocumentField.field_spec_id,
                DocumentField.group_id,
                DocumentField.resolved_value,
            )
            .where(DocumentField.document_id.in_(document_ids))
            .where(verifie)
        )
    ).all()
    par_document: Dict[int, List[ChampJuge]] = {int(d): [] for d in document_ids}
    for document_id, field_spec_id, group_id, valeur in lignes:
        par_document[int(document_id)].append((field_spec_id, group_id, valeur))
    return {d: empreinte_document(champs) for d, champs in par_document.items()}
