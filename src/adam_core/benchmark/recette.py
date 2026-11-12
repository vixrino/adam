"""Contrat d'une recette de benchmark : moteur OCR et seuils.

Partage par l'API (qui le valide a la creation) et par le worker (qui en tire
le moteur a utiliser). Fige avec la recette, dans test_recipe.config. A la
creation, l'API y ecrit le fournisseur et les modeles du .env pour les champs
laisses vides : deux executions d'une meme recette lisent avec le meme
fournisseur et les memes modeles, meme si le .env change entre elles. Limite :
un modele nomme par un alias (« mistral-ocr-latest ») peut changer chez le
fournisseur ; nommer une version precise pour une comparaison durable.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Longueur maximale de la consigne : de quoi decrire un formulaire, pas de
#: quoi y glisser un document.
CONSIGNE_MAX = 8000

#: Fournisseurs que le worker sait construire (adam_worker.connectors).
#: MOCK ne lit rien : il sert aux demonstrations et aux tests de la chaine.
FournisseurOcr = Literal["MISTRAL", "MOCK"]

#: Categories de champs que les seuils peuvent viser, comme par_criticite des
#: metriques, plus « sensible » (donnees personnelles : noms, IBAN...).
CategorieChamp = Literal["sensible", "critique", "standard"]


class ConfigOcr(BaseModel):
    """Le moteur de lecture de la recette. Un champ vide : celui du worker (.env)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: Optional[FournisseurOcr] = None
    #: Modele OCR (Mistral : /v1/ocr), par exemple « mistral-ocr-latest ».
    model: Optional[str] = Field(default=None, min_length=1)
    #: Modele qui range le texte lu dans les champs (Mistral : /v1/chat/completions).
    annotation_model: Optional[str] = Field(default=None, min_length=1)
    #: Consigne donnee au modele d'annotation, a la place de celle du code.
    prompt: Optional[str] = Field(default=None, min_length=1, max_length=CONSIGNE_MAX)

    @field_validator("provider", mode="before")
    @classmethod
    def _majuscules(cls, valeur: object) -> object:
        return valeur.upper() if isinstance(valeur, str) else valeur

    @field_validator("model", "annotation_model", "prompt", mode="before")
    @classmethod
    def _vide_vaut_defaut(cls, valeur: object) -> object:
        """« » ou des espaces : pas de valeur, donc celle par defaut."""
        if isinstance(valeur, str) and not valeur.strip():
            return None
        return valeur


class ConfigRecette(BaseModel):
    """Configuration du test, figee avec la recette."""

    model_config = ConfigDict(extra="forbid")

    #: Score global minimal (0 a 1) pour que le passage soit « reussi ».
    score_minimal: Optional[float] = Field(default=None, ge=0, le=1)
    #: Taux d'erreur maximal par champ (cle exacte ou prefixe) :
    #: {"gestion_budget.iban": 0.0}.
    seuils_par_champ: Dict[str, float] = Field(default_factory=dict)
    #: Taux d'erreur maximal par categorie de champs : {"sensible": 0.0}.
    seuils_par_categorie: Dict[CategorieChamp, float] = Field(default_factory=dict)
    #: Prefixes de cle ignores par les metriques : ["certification."].
    champs_exclus: List[str] = Field(default_factory=list)
    #: Le moteur ; absent, celui du worker.
    ocr: ConfigOcr = Field(default_factory=ConfigOcr)

    @field_validator("seuils_par_champ", "seuils_par_categorie")
    @classmethod
    def _taux(cls, seuils: Dict[str, float]) -> Dict[str, float]:
        for cle, valeur in seuils.items():
            if not 0 <= valeur <= 1:
                raise ValueError(f"seuil de {cle} hors de 0 a 1 : {valeur}")
        return seuils


def config_ocr(config: Optional[Dict[str, object]]) -> ConfigOcr:
    """Le moteur d'une config de recette en base, tolerant les anciennes
    recettes qui n'en ont pas."""
    return ConfigOcr.model_validate((config or {}).get("ocr") or {})
