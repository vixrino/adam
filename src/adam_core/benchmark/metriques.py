"""Metriques d'une execution de benchmark OCR, calculees a la lecture.

Fonctions pures : elles prennent les comptes que le worker a figes
(evaluation_report, un par champ) et rendent les indicateurs. Les ratios ne
sont jamais stockes : une formule ou un seuil qui change ne demande pas de
relancer le moteur.

Definitions (champs verifies par un humain seulement)
------------------------------------------------------
    vp  verite remplie, lecture egale
    fp  lecture remplie et fausse : valeur inventee, ou substitution
    fn  verite remplie mal lue : valeur manquee, ou substitution
    vn  verite vide, lecture vide

    precision = vp / (vp + fp)   quand le moteur ecrit, a-t-il raison ?
    rappel    = vp / (vp + fn)   des valeurs du document, combien sont lues ?
    F1        = 2PR / (P + R) = 2vp / (2vp + fp + fn)
                                 le score global, en micro (comptes sommes)

Une substitution (verite remplie, lecture differente) compte en fp ET en fn :
c'est l'erreur la plus dangereuse, celle qui passe inapercue.

Garde-fous
----------
- Les vn n'entrent dans aucun ratio : un CERFA est surtout vide, et un moteur
  muet aurait sinon une « exactitude » excellente.
- Chaque taux porte son intervalle de confiance (Wilson, 95 %), et un bloc de
  moins de EFFECTIF_MINIMAL valeurs est marque insuffisant.
- Le score global n'est pas pondere : la decomposition par type et par
  criticite est toujours rendue a cote.
- Deux executions ne se comparent que sur la meme recette, avec la meme
  version de comparateur et la meme empreinte de schema.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: En dessous, un taux est publie mais marque « effectif insuffisant ».
EFFECTIF_MINIMAL = 5
#: Une execution sur moins de documents est marquee « echantillon faible ».
DOCUMENTS_MINIMUM = 10

_COMPTES = (
    "vp",
    "fp",
    "fn",
    "vn",
    "substitutions",
    "somme_distance",
    "somme_longueur_attendue",
)


def _ratio(numerateur: int, denominateur: int) -> Optional[float]:
    return numerateur / denominateur if denominateur else None


def wilson(succes: int, total: int, z: float = 1.96) -> Optional[Tuple[float, float]]:
    """Intervalle de Wilson a 95 % d'une proportion : juste meme sur peu de cas,
    la ou l'approximation normale donne des bornes hors de [0, 1]."""
    if total == 0:
        return None
    p = succes / total
    denominateur = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominateur
    marge = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominateur
    return (round(max(0.0, centre - marge), 4), round(min(1.0, centre + marge), 4))


def bloc(lignes: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Indicateurs d'un ensemble de champs (global, une section, un type...)."""
    c = {nom: 0 for nom in _COMPTES}
    for ligne in lignes:
        for nom in _COMPTES:
            c[nom] += int(ligne.get(nom) or 0)
    vp, fp, fn = c["vp"], c["fp"], c["fn"]
    inventees = fp - c["substitutions"]
    #: Valeurs en jeu : remplies d'un cote ou de l'autre (les vn exclus).
    valeurs = vp + fn + inventees
    precision = _ratio(vp, vp + fp)
    rappel = _ratio(vp, vp + fn)
    # Forme equivalente a 2PR/(P+R), mais definie des qu'une valeur est en jeu :
    # un champ jamais lu (0 vp, 5 fn) n'a pas de precision, et son F1 vaut 0,
    # pas « indefini » — sinon le pire champ disparaitrait du classement.
    f1 = _ratio(2 * vp, 2 * vp + fp + fn)
    return {
        **c,
        "inventees": inventees,
        "valeurs": valeurs,
        "vides_confirmes": c["vn"],
        "precision": _arrondi(precision),
        "rappel": _arrondi(rappel),
        "f1": _arrondi(f1),
        "taux_erreur": _arrondi(_ratio(valeurs - vp, valeurs)),
        "taux_erreur_caracteres": _arrondi(
            _ratio(c["somme_distance"], c["somme_longueur_attendue"])
        ),
        "ic95_precision": wilson(vp, vp + fp),
        "ic95_rappel": wilson(vp, vp + fn),
        "effectif_suffisant": valeurs >= EFFECTIF_MINIMAL,
    }


def _arrondi(valeur: Optional[float]) -> Optional[float]:
    return round(valeur, 4) if valeur is not None else None


def _criticite(ligne: Mapping[str, Any]) -> str:
    """Critique : donnee personnelle ou montant, dont l'erreur coute le plus."""
    if ligne.get("sensitive") or str(ligne.get("value_type") or "").upper() == "NUMBER":
        return "critique"
    return "standard"


def _par(
    lignes: Sequence[Mapping[str, Any]], cle: Callable[[Mapping[str, Any]], Any]
) -> Dict[str, Dict[str, Any]]:
    groupes: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for ligne in lignes:
        groupes[str(cle(ligne))].append(ligne)
    return {nom: bloc(groupe) for nom, groupe in sorted(groupes.items())}


def _exclu(field_key: str, exclus: Sequence[str]) -> bool:
    return any(field_key.startswith(prefixe) for prefixe in exclus)


def _seuil_du_champ(field_key: str, seuils: Mapping[str, float]) -> Optional[float]:
    """Seuil le plus specifique : cle exacte, sinon le plus long prefixe."""
    candidats = [p for p in seuils if field_key == p or field_key.startswith(p)]
    return float(seuils[max(candidats, key=len)]) if candidats else None


def calculer(
    lignes: Sequence[Mapping[str, Any]],
    execution: Mapping[str, Any],
    config: Optional[Mapping[str, Any]] = None,
    categories: Optional[Mapping[str, int]] = None,
) -> Dict[str, Any]:
    """Toutes les metriques d'une execution.

    Args:
        lignes: les evaluation_report de l'execution, en mappings.
        execution: compteurs et identite de l'execution (test_execution).
        config: la config de la recette (seuil_f1, seuils_par_champ,
            champs_exclus).
        categories: nombre d'ecarts par diff_kind (comparison_result).
    """
    config = config or {}
    exclus = list(config.get("champs_exclus") or [])
    retenues = [ligne for ligne in lignes if not _exclu(str(ligne.get("field_key", "")), exclus)]

    global_ = bloc(retenues)
    par_champ = [
        {
            "field_key": ligne.get("field_key"),
            "page": ligne.get("page"),
            "section_id": ligne.get("section_id"),
            "value_type": ligne.get("value_type"),
            "sensitive": bool(ligne.get("sensitive")),
            **bloc([ligne]),
        }
        for ligne in retenues
    ]
    # Les pires champs d'abord : c'est ce qu'on regarde.
    par_champ.sort(key=lambda c: (c["f1"] is None, c["f1"] if c["f1"] is not None else 0))

    documents = int(execution.get("documents_compared") or 0)
    perimetre = int(execution.get("fields_compared") or 0)
    verifies = int(execution.get("fields_human_verified") or 0)

    return {
        "execution": {
            "id": execution.get("id"),
            "recipe_id": execution.get("recipe_id"),
            "status": execution.get("status"),
            "ocr_provider": execution.get("ocr_provider"),
            "ocr_model_id": execution.get("ocr_model_id"),
            "comparateur_version": execution.get("comparateur_version"),
            "schema_hash": execution.get("schema_hash"),
            "started_at": execution.get("started_at"),
            "finished_at": execution.get("finished_at"),
        },
        "global": global_,
        "par_type": _par(retenues, lambda ligne: ligne.get("value_type") or "?"),
        "par_criticite": _par(retenues, _criticite),
        "par_section": _par(retenues, lambda ligne: ligne.get("section_id") or "?"),
        "par_page": _par(retenues, lambda ligne: ligne.get("page") or "?"),
        "par_champ": par_champ,
        "categories_erreurs": dict(categories or {}),
        "echantillon": {
            "documents": documents,
            "champs_perimetre": perimetre,
            "champs_juges": verifies,
            # Champs regardes par un humain, sur le perimetre : sous 1, une
            # partie de la verite manque, et les taux ne valent que pour elle.
            "couverture": _arrondi(_ratio(verifies, perimetre)),
            "champs_exclus_par_config": len(lignes) - len(retenues),
            "faible": documents < DOCUMENTS_MINIMUM,
        },
        "cout": {
            "appels_ocr": execution.get("ocr_calls_made"),
            "appels_par_document": _arrondi(
                _ratio(int(execution.get("ocr_calls_made") or 0), documents)
            ),
            "pages_par_document": _arrondi(
                _ratio(int(execution.get("pages_processed") or 0), documents)
            ),
        },
        "verdict": _verdict(global_, par_champ, config),
        "avertissements": _avertissements(
            global_, documents, verifies, perimetre, execution, retenues
        ),
    }


def _verdict(
    global_: Mapping[str, Any], par_champ: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> Dict[str, Any]:
    """Reussi / echoue selon la config de la recette ; None sans seuil."""
    seuil_f1 = config.get("seuil_f1")
    seuils = config.get("seuils_par_champ") or {}
    champs_en_echec = []
    for champ in par_champ:
        seuil = _seuil_du_champ(str(champ["field_key"]), seuils)
        taux = champ["taux_erreur"]
        if seuil is not None and taux is not None and taux > seuil:
            champs_en_echec.append(
                {"field_key": champ["field_key"], "taux_erreur": taux, "seuil": seuil}
            )
    if seuil_f1 is None and not seuils:
        return {"seuil_f1": None, "reussi": None, "champs_en_echec": []}
    f1 = global_["f1"]
    global_ok = seuil_f1 is None or (f1 is not None and f1 >= float(seuil_f1))
    return {
        "seuil_f1": seuil_f1,
        "reussi": bool(global_ok and not champs_en_echec),
        "champs_en_echec": champs_en_echec,
    }


def _avertissements(
    global_: Mapping[str, Any],
    documents: int,
    verifies: int,
    perimetre: int,
    execution: Mapping[str, Any],
    lignes: Sequence[Mapping[str, Any]] = (),
) -> List[str]:
    """Ce qu'il faut savoir avant de croire le score."""
    messages = []
    juges = sum(int(ligne.get("compared") or 0) for ligne in lignes)
    matrice = sum(int(ligne.get(nom) or 0) for ligne in lignes for nom in ("vp", "fp", "fn", "vn"))
    if juges and not matrice:
        # Execution faite avant que le worker ne compte la matrice : ses champs
        # ont ete juges, mais vp/fp/fn/vn valent leur defaut, 0.
        messages.append(
            "execution anterieure aux metriques : matrice non enregistree, "
            "relancer la recette pour obtenir precision et rappel"
        )
    if documents < DOCUMENTS_MINIMUM:
        messages.append(
            f"echantillon faible : {documents} document(s), moins de {DOCUMENTS_MINIMUM}"
        )
    if not global_["effectif_suffisant"]:
        messages.append(
            f"effectif insuffisant : {global_['valeurs']} valeur(s) jugee(s), "
            f"moins de {EFFECTIF_MINIMAL}"
        )
    if perimetre and verifies < perimetre:
        messages.append(
            f"couverture partielle : {verifies} champ(s) verifie(s) sur {perimetre} ; "
            "les taux ne valent que pour les champs regardes par un humain"
        )
    if execution.get("error_message"):
        messages.append(str(execution["error_message"]))
    return messages


def comparer(a: Mapping[str, Any], b: Mapping[str, Any]) -> Dict[str, Any]:
    """Compare deux resultats de calculer() : b par rapport a a.

    La comparaison est toujours rendue, mais signalee non comparable si la
    recette, la version du comparateur ou l'empreinte du schema different :
    un ecart de score n'y mesurerait pas le moteur.
    """
    ea, eb = a["execution"], b["execution"]
    raisons = [
        f"{libelle} differente"
        for cle, libelle in (
            ("recipe_id", "recette"),
            ("comparateur_version", "version du comparateur"),
            ("schema_hash", "empreinte du schema"),
        )
        if ea.get(cle) != eb.get(cle) or ea.get(cle) is None
    ]
    indicateurs = ("precision", "rappel", "f1", "taux_erreur", "taux_erreur_caracteres")

    def delta(x: Optional[float], y: Optional[float]) -> Optional[float]:
        return round(y - x, 4) if x is not None and y is not None else None

    champs_a = {c["field_key"]: c for c in a["par_champ"]}
    champs_b = {c["field_key"]: c for c in b["par_champ"]}
    par_champ = [
        {
            "field_key": cle,
            "f1_a": champs_a[cle]["f1"],
            "f1_b": champs_b[cle]["f1"],
            "delta_f1": delta(champs_a[cle]["f1"], champs_b[cle]["f1"]),
        }
        for cle in sorted(champs_a.keys() & champs_b.keys())
    ]
    par_champ.sort(key=lambda c: c["delta_f1"] if c["delta_f1"] is not None else 0)
    return {
        "a": ea,
        "b": eb,
        "comparable": not raisons,
        "raisons": raisons,
        "global": {
            nom: {
                "a": a["global"][nom],
                "b": b["global"][nom],
                "delta": delta(a["global"][nom], b["global"][nom]),
            }
            for nom in indicateurs
        },
        "par_champ": par_champ,
    }
