"""Contrat de sortie du benchmark OCR : metriques d'une execution, comparaison
de deux executions, executions d'un export.

Les calculs (adam_core/benchmark/metriques.py) rendent des dicts ; ces modeles
les figent pour l'IHM. ``extra="forbid"`` partout : une cle ajoutee au calcul
sans etre declaree ici fait echouer les tests au lieu de sortir en douce, et
une cle declaree mais disparue fait echouer la validation. Le contrat ne bouge
donc qu'expres.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


Fourchette = Optional[Tuple[float, float]]


# -- Metriques d'une execution --------------------------------------------------


class Bloc(_Strict):
    """Indicateurs d'un ensemble de champs : tout le test, un type, une section..."""

    valeurs_jugees: int = Field(description="Valeurs remplies d'un cote ou de l'autre")
    justes: int
    fausses: int = Field(description="Lues, mais differentes de la verite")
    manquees: int = Field(description="Presentes dans la verite, non lues")
    inventees: int = Field(description="Lues alors que la verite est vide")
    vides: int = Field(description="Vides des deux cotes, hors des taux")
    score: Optional[float] = Field(description="F1 : 2 justes / (2 justes + fausses + ...)")
    taux_lectures_justes: Optional[float] = Field(description="Precision")
    taux_valeurs_trouvees: Optional[float] = Field(description="Rappel")
    taux_erreur: Optional[float]
    taux_erreur_caracteres: Optional[float]
    assez_de_donnees: bool
    fourchette_lectures_justes: Fourchette = Field(
        default=None, description="Intervalle de Wilson a 95 % ; absent pour un champ seul"
    )
    fourchette_valeurs_trouvees: Fourchette = None


class BlocSection(Bloc):
    libelle: str = Field(description="Libelle du schema (« Co-deposant »), sinon l'id")


class ChampMetrique(Bloc):
    champ: str = Field(description="Cle, et la ligne pour un tableau : « s.cle[pret_7] »")
    page: Optional[int] = None
    section: Optional[str] = None
    section_libelle: Optional[str] = None
    type: Optional[str] = None
    sensible: bool
    reussite: Optional[float] = Field(description="justes / valeurs_jugees")
    documents_en_erreur: int
    echec_principal: Optional[str] = Field(description="fausse, manquee ou inventee")


class Selection(_Strict):
    filtres: Dict[str, Any]
    champs: int = Field(description="Champs listes dans par_champ")
    champs_verifies: int


class Echantillon(_Strict):
    documents: int
    champs_au_total: int
    champs_par_document: Optional[int]
    champs_verifies: int
    part_verifiee: Optional[float]
    champs_exclus_par_config: int
    trop_petit: bool


class Cout(_Strict):
    appels_ocr: Optional[int]
    appels_par_document: Optional[float]
    pages_par_document: Optional[float]


class ChampEnEchec(_Strict):
    champ: str
    taux_erreur: float
    seuil: float


class CategorieEnEchec(_Strict):
    categorie: str
    taux_erreur: float
    seuil: float


class Verdict(_Strict):
    score_minimal: Optional[float]
    reussi: Optional[bool] = Field(description="None : la recette ne fixe aucun seuil")
    champs_en_echec: List[ChampEnEchec]
    categories_en_echec: List[CategorieEnEchec]


class ExecutionResume(_Strict):
    id: int
    recipe_id: int
    status: str
    ocr_provider: Optional[str]
    ocr_model_id: Optional[str]
    comparateur_version: Optional[str]
    schema_hash: Optional[str]
    verite_hash: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class RecetteResume(_Strict):
    id: Optional[int] = None
    name: Optional[str] = None
    version: Optional[int] = None
    dataset_export_id: Optional[int] = Field(
        default=None, description="Nul pour une recette d'avant les exports"
    )
    document_ids: List[int] = Field(default_factory=list)


class DatasetResume(_Strict):
    id: Optional[int]
    name: Optional[str]


class MetriquesOut(_Strict):
    execution: ExecutionResume
    recette: RecetteResume
    dataset: DatasetResume
    global_: Bloc = Field(alias="global")
    par_type: Dict[str, Bloc]
    par_criticite: Dict[str, Bloc]
    par_section: Dict[str, BlocSection]
    par_page: Dict[str, Bloc]
    par_champ: List[ChampMetrique]
    champs_sans_erreur: int
    selection: Selection
    categories_erreurs: Dict[str, int]
    echantillon: Echantillon
    cout: Cout
    verdict: Verdict
    avertissements: List[str]


# -- Comparaison de deux executions -----------------------------------------------


class CoteCompare(ExecutionResume):
    documents: int = Field(description="Documents juges par l'execution")
    recette: RecetteResume


class Moteur(_Strict):
    fournisseur: Optional[str]
    modele: Optional[str]


class MoteursCompares(_Strict):
    a: Moteur
    b: Moteur
    identique: bool
    changements: List[str] = Field(description="« fournisseur », « modele » (consigne comprise)")


class IndicateurCompare(_Strict):
    a: Optional[float]
    b: Optional[float]
    evolution: Optional[float] = Field(description="b - a")


class SectionComparee(_Strict):
    libelle: str
    taux_lectures_justes_a: Optional[float]
    taux_lectures_justes_b: Optional[float]
    ecart_pts: Optional[float]


class ChampCompare(_Strict):
    champ: str
    section: Optional[str]
    section_libelle: Optional[str]
    present_a: bool
    present_b: bool
    reussite_a: Optional[float]
    reussite_b: Optional[float]
    ecart_pts: Optional[float] = Field(description="Points de pourcentage, b - a")
    score_a: Optional[float]
    score_b: Optional[float]
    evolution: Optional[float]


class ComparaisonOut(_Strict):
    a: CoteCompare = Field(description="La reference")
    b: CoteCompare
    comparable: bool
    raisons: List[str] = Field(description="Pourquoi l'ecart ne mesurerait pas que le moteur")
    moteur: MoteursCompares
    global_: Dict[str, IndicateurCompare] = Field(alias="global")
    par_section: Dict[str, SectionComparee]
    par_champ: List[ChampCompare] = Field(description="Tous les champs, regressions d'abord")
    champs_inchanges: int


# -- Progression d'une execution ---------------------------------------------------


class ProgressionOut(_Strict):
    """Ce que l'IHM affiche pendant un passage : de quoi une barre et une
    estimation de fin, rafraichies par polling."""

    execution_id: int
    status: str = Field(description="PENDING, RUNNING, COMPLETED, FAILED, CANCELLED")
    termine: bool = Field(description="Plus rien ne bougera : arreter le polling")
    annulable: bool
    documents_total: int = Field(description="Documents de la recette")
    documents_traites: int = Field(description="Compares ou ecartes (images absentes)")
    documents_compares: int
    pourcentage: float = Field(description="0 a 100 ; 100 une fois COMPLETED")
    champs_compares: int
    ecarts: int
    appels_ocr: int
    pages_traitees: int
    secondes_ecoulees: Optional[float] = Field(description="Depuis le debut du passage")
    secondes_restantes_estimees: Optional[float] = Field(
        description="Au rythme moyen des documents deja traites ; None sans recul"
    )
    dernier_signe_de_vie: Optional[datetime] = Field(
        description="Ecrit a chaque document : un passage fige se voit ici"
    )
    message: Optional[str]


# -- Executions d'un export ---------------------------------------------------------


class ExecutionDeLExport(_Strict):
    """Une ligne de l'ecran de comparaison : un passage termine sur l'export."""

    execution_id: int
    recette: RecetteResume
    ocr_provider: Optional[str]
    ocr_model_id: Optional[str]
    finished_at: Optional[datetime]
    documents: int
    score: Optional[float]
    taux_lectures_justes: Optional[float]
    taux_valeurs_trouvees: Optional[float]
    taux_erreur: Optional[float]
    reussi: Optional[bool]
