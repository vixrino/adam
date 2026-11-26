"""Tests unitaires adam_worker/consensus_worker.py

Le worker relance try_resolve sur chaque document PENDING_CONSENSUS. On
remplace la session par une fausse qui rend les lignes voulues, et try_resolve
par un enregistreur : la base et le service de consensus ne sont pas en jeu.
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, List, Tuple

import pytest

from adam_core.enums.status import DocumentStatus
from adam_worker import consensus_worker
from adam_worker.consensus_worker import ConsensusWorker


class _Resultat:
    def __init__(self, lignes: List[Tuple[int, int]]) -> None:
        self._lignes = lignes

    def all(self) -> List[Tuple[int, int]]:
        return self._lignes


class _Session:
    def __init__(self, lignes: List[Tuple[int, int]]) -> None:
        self.lignes = lignes
        self.requetes: List[Any] = []

    async def execute(self, requete: Any) -> _Resultat:
        self.requetes.append(requete)
        return _Resultat(self.lignes)


def _brancher(
    monkeypatch: pytest.MonkeyPatch, lignes: List[Tuple[int, int]], echecs: Tuple[int, ...] = ()
) -> Tuple[_Session, List[Tuple[int, int]]]:
    session = _Session(lignes)
    appels: List[Tuple[int, int]] = []

    @asynccontextmanager
    async def fausse_session() -> AsyncIterator[_Session]:
        yield session

    async def faux_try_resolve(document_id: int, dataset_id: int) -> None:
        appels.append((document_id, dataset_id))
        if document_id in echecs:
            raise RuntimeError(f"consensus impossible pour {document_id}")

    monkeypatch.setattr(consensus_worker, "get_async_session", fausse_session)
    monkeypatch.setattr(consensus_worker, "try_resolve", faux_try_resolve)
    return session, appels


@pytest.mark.asyncio
async def test_sans_document_en_attente_rien_n_est_resolu(monkeypatch: pytest.MonkeyPatch) -> None:
    _, appels = _brancher(monkeypatch, [])

    await ConsensusWorker().poll()

    assert not appels


@pytest.mark.asyncio
async def test_chaque_document_en_attente_est_resolu_avec_son_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, appels = _brancher(monkeypatch, [(12, 3), (15, 4)])

    await ConsensusWorker().poll()

    assert appels == [(12, 3), (15, 4)]


@pytest.mark.asyncio
async def test_la_requete_ne_cible_que_pending_consensus(monkeypatch: pytest.MonkeyPatch) -> None:
    session, _ = _brancher(monkeypatch, [])

    await ConsensusWorker().poll()

    assert len(session.requetes) == 1
    compilee = session.requetes[0].compile(compile_kwargs={"literal_binds": True})
    assert DocumentStatus.PENDING_CONSENSUS.value in str(compilee)


@pytest.mark.asyncio
async def test_un_echec_n_interrompt_pas_les_documents_suivants(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Un document dont le consensus leve ne doit pas bloquer le reste du lot."""
    _, appels = _brancher(monkeypatch, [(12, 3), (15, 3), (18, 3)], echecs=(15,))

    await ConsensusWorker().poll()

    assert appels == [(12, 3), (15, 3), (18, 3)]
    assert "document_id=15" in caplog.text
