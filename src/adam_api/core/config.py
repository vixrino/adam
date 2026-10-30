"""
Settings specifiques a l'API nota.
"""

from functools import lru_cache
from typing import List

from pydantic import ValidationError, model_validator
from pydantic_settings import SettingsConfigDict

from adam_core.core.config import CoreSettings

#: Prefixe commun a toutes les routes metier, monte par main.py.
#: Declare ici et non dans main.py : le worker en a besoin pour construire ses
#: URL, et importer main.py depuis un worker chargerait toute l'application.
API_PREFIX = "/api/v1"

#: Environnements ou les durcissements ci-dessous sont suspendus. "test" est celui
#: de la suite de tests, jamais un deploiement.
_LOCAL_ENVIRONMENTS = {"dev", "test"}

#: Longueur minimale de INTERNAL_API_KEY hors DEV (secret partage par tous les services).
_MIN_INTERNAL_API_KEY_LENGTH = 32


class Settings(CoreSettings):
    # La config porte des secrets (INTERNAL_API_KEY...) : jamais dans un message d'erreur,
    # ni dans le traceback de demarrage (get_settings chaine l'exception d'origine).
    model_config = SettingsConfigDict(hide_input_in_errors=True)

    api_host: str
    api_port: int
    api_version: str
    api_title: str
    api_cors_origins: str
    api_disable_jwt_validation: bool

    # Dev
    api_dev_matricule: str = "MAT00003"

    # Auth service machine
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
    mistral_annotation_model: str = "mistral-medium-latest"
    #: Chemin d'un truststore PEM pour un endpoint prive ; vide = CA systeme.
    mistral_ca_bundle: str = ""

    @model_validator(mode="after")
    def _harden_outside_dev(self) -> "Settings":
        """Refuse de demarrer hors DEV avec une authentification affaiblie.

        api_disable_jwt_validation=true endosse un matricule fixe (api_dev_matricule)
        et internal_auth_enabled=false laisse n'importe quel X-Internal-Token devenir
        un appelant service : dans les deux cas, plus rien ne prouve qui appelle.
        Une INTERNAL_API_KEY courte se devine, et c'est le seul secret des services.
        """
        if self.app_env.lower() in _LOCAL_ENVIRONMENTS:
            return self
        if self.api_disable_jwt_validation or not self.internal_auth_enabled:
            raise ValueError(
                "bypass d'authentification interdit hors DEV (APP_ENV="
                f"{self.app_env}) : API_DISABLE_JWT_VALIDATION doit etre false "
                "et INTERNAL_AUTH_ENABLED true"
            )
        if len(self.internal_api_key) < _MIN_INTERNAL_API_KEY_LENGTH:
            raise ValueError(
                f"INTERNAL_API_KEY trop courte hors DEV (APP_ENV={self.app_env}) : "
                f"{_MIN_INTERNAL_API_KEY_LENGTH} caracteres minimum"
            )
        return self

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.api_cors_origins.split(",")]

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

    #: Comptes a ne jamais proposer, bien que ranges sous AD_BASE_DN : debuts
    #: de matricule (« OT2 ») et unites d'organisation (« OT2 »), separes par
    #: des virgules.
    ad_exclude_prefixes: str = ""
    #: Fins de matricule a exclure (« OT2 » : I21080MOT2).
    ad_exclude_suffixes: str = ""
    ad_exclude_ous: str = ""
    #: Slug de l'organisation des agents crees a leur premiere connexion, quand
    #: aucun mot de leur departement AD n'est le slug d'une organisation. Vide :
    #: pas de repli, l'agent est refuse.
    ad_organisation_defaut: str = ""

    #: Cle du HMAC des valeurs lues sur les champs sensibles, dans les ecarts du
    #: benchmark : une erreur recurrente sur un IBAN se reconnait a son
    #: empreinte, sans que l'IBAN soit stocke. Vide : le benchmark refuse de
    #: tourner. Ne vit que dans l'environnement, jamais en base ni en commit.
    comparison_hmac_key: str = ""


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as e:
        missing = [str(err["loc"][0]) for err in e.errors() if err["type"] == "missing"]
        if not missing:  # configuration presente mais refusee
            reasons = "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
            raise RuntimeError(f"\n\n  NOTA configuration refusee : {reasons}\n") from e
        raise RuntimeError(
            "\n\n"
            "  NOTA configuration manquante\n"
            f"  Variables d'environnement absentes : {', '.join(missing)}\n"
            "  Référence : resources/config/.env.template\n"
        ) from e


# def get_settings() -> Settings:
#     return Settings()  # type: ignore[call-arg]


settings = get_settings()
