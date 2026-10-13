"""
Settings specifiques a l'API ADAM.
"""

from functools import lru_cache
from typing import List

from adam_core.core.config import CoreSettings

#: Prefixe commun a toutes les routes metier, monte par main.py.
#: Declare ici et non dans main.py : le worker en a besoin pour construire ses
#: URL, et importer main.py depuis un worker chargerait toute l'application.
API_PREFIX = "/api/v1"


class Settings(CoreSettings):
    api_host: str
    api_port: int
    api_version: str
    api_title: str
    api_cors_origins: str
    api_disable_jwt_validation: bool
    #: Matricule endosse quand la validation JWT est desactivee. Resolu en base
    #: comme n'importe quel appelant : c'est ce qui evite de reinventer un
    #: UserCaller de toutes pieces, dont l'organisation finissait par ne
    #: correspondre a aucune ligne reelle. Sans effet hors bypass.
    api_dev_matricule: str = "MAT00003"
    internal_auth_enabled: bool
    internal_api_key: str
    pvc_mount_path: str
    ocr_mock_enabled: bool
    ocr_mock_confidence: float
    ocr_timeout_seconds: int
    # Connecteur Mistral. Optionnels tant que ocr_mock_enabled est vrai ; le
    # constructeur du connecteur refuse une cle ou un endpoint vides.
    mistral_api_key: str = ""
    mistral_ocr_endpoint: str = ""
    mistral_ocr_model: str = "mistral-ocr-latest"
    #: Modele qui extrait les champs du markdown rendu par l'OCR. L'endpoint
    #: choisit seul le sien quand on lui delegue l'annotation, et son defaut
    #: n'est pas deploye partout : on le nomme ici plutot que de le subir.
    mistral_annotation_model: str = "mistral-medium-latest"
    #: Chemin d'un truststore PEM pour un endpoint prive ; vide = CA systeme.
    mistral_ca_bundle: str = ""

    #: Annuaire Active Directory, interroge par le compte de service pour
    #: affecter quelqu'un a un projet avant sa premiere connexion. Le mot de
    #: passe ne vit que dans l'environnement, jamais dans le code.
    ad_enabled: bool = False
    ad_host: str = ""
    ad_port: int = 636
    ad_use_ssl: bool = True
    ad_bind_dn: str = ""
    ad_password: str = ""
    ad_base_dn: str = ""
    #: Truststore PEM pour verifier le certificat de l'AD ; vide = CA systeme.
    ad_ca_bundle: str = ""
    ad_timeout_seconds: int = 5
    ad_search_limit: int = 25
    #: Une saisie plus courte ramenerait des milliers de comptes.
    ad_min_chars: int = 3
    #: Une recherche au plus toutes les N secondes par utilisateur.
    ad_rate_seconds: float = 2.0

    #: Cle du HMAC des valeurs lues sur les champs sensibles, dans les ecarts du
    #: benchmark : une erreur recurrente sur un IBAN se reconnait a son
    #: empreinte, sans que l'IBAN soit stocke. Vide : le benchmark refuse de
    #: tourner. Ne vit que dans l'environnement, jamais en base ni en commit.
    comparison_hmac_key: str = ""

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.api_cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
