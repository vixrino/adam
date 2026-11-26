"""Tests unitaires adam_api/services/annuaire.py : le client ldap3 hors recherche.

test_annuaire.py couvre les filtres et la recherche contre le serveur MOCK de
ldap3. Ici, ce qui l'entoure : TLS et connexion (lecture seule, liaison
simple), liaison refusee, annuaire injoignable, matricule ambigu, et la
construction depuis les reglages. Ignores sans ldap3.
"""

# Les tests visent la construction du serveur et de la connexion, privees.
# pylint: disable=protected-access

from __future__ import annotations

import asyncio
import ssl
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from adam_api.services.annuaire import (
    AnnuaireDesactive,
    AnnuaireErreur,
    AnnuaireLdap,
    annuaire_depuis_settings,
)

ldap3 = pytest.importorskip("ldap3")


def _annuaire(**changes: Any) -> AnnuaireLdap:
    params: Dict[str, Any] = {
        "host": "ad.exemple",
        "port": 636,
        "use_ssl": True,
        "bind_dn": "CN=SVC,DC=EX",
        "password": "secret",
        "base_dn": "OU=T2,DC=EX",
    }
    params.update(changes)
    return AnnuaireLdap(**params)


class _Connexion:
    """Connexion ldap3 factice : bind, search et unbind enregistres."""

    def __init__(
        self,
        lie: bool = True,
        reponse: Optional[List[Dict[str, Any]]] = None,
        erreur: Optional[Exception] = None,
    ) -> None:
        self.lie = lie
        self.response = reponse or []
        self.erreur = erreur
        self.result = {"description": "invalidCredentials"}
        self.unbinds = 0

    def bind(self) -> bool:
        return self.lie

    def search(self, *_: Any, **__: Any) -> None:
        if self.erreur is not None:
            raise self.erreur

    def unbind(self) -> None:
        self.unbinds += 1


def _entree(matricule: str, dn: str = "CN=x,OU=T2,DC=EX") -> Dict[str, Any]:
    return {"dn": dn, "attributes": {"sAMAccountName": matricule, "displayName": matricule}}


# -- Serveur et connexion ------------------------------------------------------------


def test_ldaps_verifie_le_certificat_contre_le_bundle(tmp_path: Path) -> None:
    # ldap3 verifie que le fichier existe : un bundle factice suffit.
    bundle = tmp_path / "bdf.pem"
    bundle.write_text("certificats", encoding="utf-8")
    serveur = _annuaire(ca_bundle=str(bundle), timeout_seconds=7)._serveur()

    assert serveur.ssl is True and serveur.port == 636
    assert serveur.tls.validate == ssl.CERT_REQUIRED
    assert serveur.tls.ca_certs_file == str(bundle)
    assert serveur.connect_timeout == 7


def test_sans_ssl_aucune_configuration_tls() -> None:
    serveur = _annuaire(use_ssl=False, port=389)._serveur()

    assert serveur.ssl is False and serveur.port == 389


def test_connexion_en_lecture_seule_par_liaison_simple() -> None:
    connexion = _annuaire()._connexion()

    assert connexion.user == "CN=SVC,DC=EX"
    assert connexion.authentication == ldap3.SIMPLE
    assert connexion.read_only is True


# -- Erreurs de l'annuaire ---------------------------------------------------------


def test_liaison_refusee(monkeypatch: pytest.MonkeyPatch) -> None:
    annuaire = _annuaire()
    monkeypatch.setattr(annuaire, "_connexion", lambda: _Connexion(lie=False))

    with pytest.raises(AnnuaireErreur, match="liaison au compte de service refusee"):
        asyncio.run(annuaire.rechercher("Ferreira"))


def test_annuaire_injoignable_et_connexion_refermee(monkeypatch: pytest.MonkeyPatch) -> None:
    annuaire = _annuaire()
    connexion = _Connexion(erreur=ldap3.core.exceptions.LDAPSocketOpenError("timeout"))
    monkeypatch.setattr(annuaire, "_connexion", lambda: connexion)

    with pytest.raises(AnnuaireErreur, match="annuaire injoignable"):
        asyncio.run(annuaire.rechercher("Ferreira"))
    assert connexion.unbinds == 1


def test_matricule_ambigu_rend_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deux comptes pour un meme matricule : on n'en affecte aucun."""
    annuaire = _annuaire()
    monkeypatch.setattr(
        annuaire, "_connexion", lambda: _Connexion(reponse=[_entree("V1"), _entree("V1")])
    )

    assert asyncio.run(annuaire.trouver("V1")) is None


def test_entree_sans_matricule_ignoree(monkeypatch: pytest.MonkeyPatch) -> None:
    annuaire = _annuaire()
    sans_matricule = {"dn": "CN=y,OU=T2,DC=EX", "attributes": {"displayName": "Groupe"}}
    monkeypatch.setattr(
        annuaire, "_connexion", lambda: _Connexion(reponse=[sans_matricule, _entree("V2")])
    )

    assert [p.matricule for p in asyncio.run(annuaire.rechercher("V2"))] == ["V2"]


# -- Construction depuis les reglages --------------------------------------------


def _reglages(**changes: Any) -> SimpleNamespace:
    valeurs: Dict[str, Any] = {
        "ad_enabled": True,
        "ad_host": "ad.exemple",
        "ad_port": 636,
        "ad_use_ssl": True,
        "ad_bind_dn": "CN=SVC,DC=EX",
        "ad_password": "secret",
        "ad_base_dn": "OU=T2,DC=EX",
        "ad_ca_bundle": "",
        "ad_timeout_seconds": 5,
        "ad_search_limit": 25,
        "ad_exclude_prefixes": " OT2, ADM ,",
        "ad_exclude_suffixes": "",
        "ad_exclude_ous": "OT2",
    }
    valeurs.update(changes)
    return SimpleNamespace(**valeurs)


def test_annuaire_coupe_par_reglage() -> None:
    with pytest.raises(AnnuaireDesactive, match="AD_ENABLED=false"):
        annuaire_depuis_settings(_reglages(ad_enabled=False))


def test_listes_d_exclusion_lues_depuis_le_env() -> None:
    annuaire = annuaire_depuis_settings(_reglages())

    assert annuaire.prefixes_exclus == ["OT2", "ADM"]
    assert annuaire.suffixes_exclus == []
    assert annuaire.ou_exclues == ["OT2"]
    assert annuaire.limite == 25 and annuaire.base_dn == "OU=T2,DC=EX"


def test_reglage_d_exclusion_absent() -> None:
    annuaire = annuaire_depuis_settings(_reglages(ad_exclude_prefixes=None))

    assert annuaire.prefixes_exclus == []
