"""Metriques d'une execution de benchmark OCR, calculees a la lecture.

Fonctions pures : elles prennent les comptes que le worker a figes
(evaluation_report, un par champ) et rendent les indicateurs. Les ratios ne
sont jamais stockes : une formule ou un seuil qui change ne demande pas de
relancer le moteur.

Ce que rend l'API (champs verifies par un humain seulement)
------------------------------------------------------------
Chaque valeur tombe dans une seule case :

    justes     case remplie, bien lue
    fausses    case remplie, lue avec une autre valeur (la plus dangereuse :
               elle passe inapercue)
    manquees   case remplie, rien lu
    inventees  case vide, le moteur a ecrit quelque chose
    vides      case vide, rien lu : hors score

    taux_lectures_justes   justes / tout ce que le moteur a ecrit
                           (precision : quand il ecrit, a-t-il raison ?)
    taux_valeurs_trouvees  justes / toutes les cases remplies
                           (rappel : combien de valeurs sont lues ?)
    score                  la moyenne des deux (F1, comptes sommes)
    taux_erreur            1 - justes / valeurs jugees

En base, evaluation_report garde la matrice classique : vp = justes,
fp = fausses + inventees, fn = fausses + manquees, vn = vides,
substitutions = fausses.

Par champ, en plus du bloc ci-dessus
------------------------------------
Un document donne une seule valeur par champ (une ligne de tableau compte
comme un champ). D'ou, sans autre donnee que les comptes :

    reussite             justes / valeurs jugees : part des documents ou le
                         champ est bien lu (les vides hors calcul)
    documents_en_erreur  fausses + manquees + inventees
    echec_principal      la plus frequente des trois, « fausse » d'abord a
                         egalite : c'est l'erreur qui passe inapercue

Les filtres (FiltresChamps) ne portent que sur ``par_champ`` : le score et les
decompositions restent ceux de tout le test.

Garde-fous
----------
- Les vides n'entrent dans aucun ratio : un CERFA est surtout vide, et un
  moteur muet aurait sinon une « exactitude » excellente.
- Les taux globaux et par groupe portent leur fourchette (Wilson, 95 %), et un
  bloc de moins de EFFECTIF_MINIMAL valeurs est marque « pas assez de
  donnees ».
- Le score global n'est pas pondere : la decomposition par type et par
  criticite est toujours rendue a cote.
- Deux executions ne se comparent que sur la meme recette, avec la meme
  version de comparateur et la meme empreinte de schema.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: En dessous, un taux est publie mais marque « effectif insuffisant ».
EFFECTIF_MINIMAL = 5
#: Une execution sur moins de documents est marquee « echantillon faible ».
DOCUMENTS_MINIMUM = 10

#: Types d'erreur d'un champ, tels que l'API les nomme, et leur compte dans bloc().
TYPES_ERREUR: Dict[str, str] = {
    "fausse": "fausses",
    "manquee": "manquees",
    "inventee": "inventees",
}

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


def _sommer(lignes: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    c = {nom: 0 for nom in _COMPTES}
    for ligne in lignes:
        for nom in _COMPTES:
            c[nom] += int(ligne.get(nom) or 0)
    return c


def bloc(lignes: Iterable[Mapping[str, Any]], fourchettes: bool = True) -> Dict[str, Any]:
    """Indicateurs d'un ensemble de champs (global, une section, un type...).

    ``fourchettes`` faux pour un champ seul : 618 intervalles de confiance sur
    quelques valeurs chacun alourdiraient la reponse sans rien dire.
    """
    c = _sommer(lignes)
    vp, fp, fn = c["vp"], c["fp"], c["fn"]
    fausses = c["substitutions"]
    inventees = fp - fausses
    #: Valeurs en jeu : remplies d'un cote ou de l'autre (les vides exclus).
    valeurs = vp + fn + inventees
    # Forme equivalente a 2PR/(P+R), mais definie des qu'une valeur est en jeu :
    # un champ jamais lu (0 vp, 5 fn) n'a pas de precision, et son score vaut 0,
    # pas « indefini » — sinon le pire champ disparaitrait du classement.
    resultat: Dict[str, Any] = {
        "valeurs_jugees": valeurs,
        "justes": vp,
        "fausses": fausses,
        "manquees": fn - fausses,
        "inventees": inventees,
        "vides": c["vn"],
        "score": _arrondi(_ratio(2 * vp, 2 * vp + fp + fn)),
        "taux_lectures_justes": _arrondi(_ratio(vp, vp + fp)),
        "taux_valeurs_trouvees": _arrondi(_ratio(vp, vp + fn)),
        "taux_erreur": _arrondi(_ratio(valeurs - vp, valeurs)),
        "taux_erreur_caracteres": _arrondi(
            _ratio(c["somme_distance"], c["somme_longueur_attendue"])
        ),
        "assez_de_donnees": valeurs >= EFFECTIF_MINIMAL,
    }
    if fourchettes:
        resultat["fourchette_lectures_justes"] = wilson(vp, vp + fp)
        resultat["fourchette_valeurs_trouvees"] = wilson(vp, vp + fn)
    return resultat


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


def _avec_libelles(
    sections: Dict[str, Dict[str, Any]], lignes: Sequence[Mapping[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """Ajoute a chaque section son libelle du schema (« Co-deposant »), sinon son id."""
    libelles = {
        str(ligne.get("section_id") or "?"): ligne.get("section_label")
        for ligne in lignes
        if ligne.get("section_label")
    }
    for section_id, valeurs in sections.items():
        valeurs["libelle"] = libelles.get(section_id) or section_id
    return sections


def _exclu(field_key: str, exclus: Sequence[str]) -> bool:
    return any(field_key.startswith(prefixe) for prefixe in exclus)


def _seuil_du_champ(field_key: str, seuils: Mapping[str, float]) -> Optional[float]:
    """Seuil le plus specifique : cle exacte, sinon le plus long prefixe."""
    candidats = [p for p in seuils if field_key == p or field_key.startswith(p)]
    return float(seuils[max(candidats, key=len)]) if candidats else None


def _a_des_erreurs(champ: Mapping[str, Any]) -> bool:
    return bool(champ["fausses"] or champ["manquees"] or champ["inventees"])


def detail_champ(champ: Mapping[str, Any]) -> Dict[str, Any]:
    """Reussite, documents en erreur et echec principal d'un champ."""
    erreurs = {nom: int(champ[compte]) for nom, compte in TYPES_ERREUR.items()}
    en_erreur = sum(erreurs.values())
    return {
        "reussite": _arrondi(_ratio(int(champ["justes"]), int(champ["valeurs_jugees"]))),
        "documents_en_erreur": en_erreur,
        # max garde le premier a egalite : l'ordre de TYPES_ERREUR decide.
        "echec_principal": max(erreurs, key=lambda nom: erreurs[nom]) if en_erreur else None,
    }


@dataclass(frozen=True)
class FiltresChamps:
    """Filtres de la liste des champs, les memes pour la page et le PDF.

    Vide, un filtre ne retient rien. Plusieurs valeurs d'un meme filtre se
    cumulent (OU), plusieurs filtres se combinent (ET).
    """

    #: Morceau de la cle du champ, sans tenir compte de la casse.
    recherche: Optional[str] = None
    #: value_type : TEXT, NUMBER, DATE, BOOLEAN.
    types_champ: Tuple[str, ...] = ()
    #: Reussite strictement inferieure a ce seuil (0 a 1). Un champ sans valeur
    #: jugee (que des vides) n'a pas de reussite : il est alors ecarte.
    reussite_inferieure_a: Optional[float] = None
    #: Au moins une erreur de l'un de ces types (cles de TYPES_ERREUR).
    types_erreur: Tuple[str, ...] = ()
    #: section_id.
    sections: Tuple[str, ...] = ()

    def actifs(self) -> Dict[str, Any]:
        """Les filtres renseignes, pour les rappeler a l'ecran et dans le PDF."""
        tous = {
            "recherche": self.recherche or None,
            "types_champ": list(self.types_champ),
            "reussite_inferieure_a": self.reussite_inferieure_a,
            "types_erreur": list(self.types_erreur),
            "sections": list(self.sections),
        }
        return {nom: valeur for nom, valeur in tous.items() if valeur not in (None, [])}

    def garde(self, champ: Mapping[str, Any]) -> bool:
        """Vrai si le champ (une entree de par_champ) passe tous les filtres."""
        if self.recherche and self.recherche.lower() not in str(champ["champ"]).lower():
            return False
        types = {t.upper() for t in self.types_champ}
        if types and str(champ.get("type") or "").upper() not in types:
            return False
        if self.sections and champ.get("section") not in self.sections:
            return False
        if self.reussite_inferieure_a is not None and (
            champ["reussite"] is None or champ["reussite"] >= self.reussite_inferieure_a
        ):
            return False
        if self.types_erreur and not any(
            champ[TYPES_ERREUR[nom]] for nom in self.types_erreur if nom in TYPES_ERREUR
        ):
            return False
        return True


def calculer(
    lignes: Sequence[Mapping[str, Any]],
    execution: Mapping[str, Any],
    config: Optional[Mapping[str, Any]] = None,
    categories: Optional[Mapping[str, int]] = None,
    tous_les_champs: bool = False,
    filtres: Optional[FiltresChamps] = None,
) -> Dict[str, Any]:
    """Toutes les metriques d'une execution.

    Args:
        lignes: les evaluation_report de l'execution, en mappings.
        execution: compteurs et identite de l'execution (test_execution).
        config: la config de la recette (score_minimal, seuils_par_champ,
            champs_exclus).
        categories: nombre d'ecarts par diff_kind (comparison_result).
        tous_les_champs: faux, ``par_champ`` ne garde que les champs en
            erreur. Sur un CERFA de 618 champs, la liste complete faisait
            94 % de la reponse, et un champ sans erreur n'y apprend rien.
        filtres: restreignent ``par_champ``, apres le choix ci-dessus ; le
            reste de la reponse porte toujours sur tout le test.
    """
    config = config or {}
    exclus = list(config.get("champs_exclus") or [])
    retenues = [ligne for ligne in lignes if not _exclu(str(ligne.get("field_key", "")), exclus)]

    global_ = bloc(retenues)
    par_champ = [
        {
            "champ": ligne.get("field_key"),
            "page": ligne.get("page"),
            "section": ligne.get("section_id"),
            # Libelle du schema quand il est connu, sinon l'id de section.
            "section_libelle": ligne.get("section_label") or ligne.get("section_id"),
            "type": ligne.get("value_type"),
            "sensible": bool(ligne.get("sensitive")),
            **bloc([ligne], fourchettes=False),
        }
        for ligne in retenues
    ]
    for champ in par_champ:
        champ.update(detail_champ(champ))
    # Les pires champs d'abord : c'est ce qu'on regarde. A reussite egale, celui
    # qui echoue sur le plus de documents.
    par_champ.sort(
        key=lambda c: (
            c["reussite"] is None,
            c["reussite"] if c["reussite"] is not None else 0,
            -c["documents_en_erreur"],
            str(c["champ"]),
        )
    )
    # Le verdict porte sur tous les champs, avant le filtre d'affichage.
    par_categorie = _par(retenues, _criticite)
    sensibles = [ligne for ligne in retenues if ligne.get("sensitive")]
    if sensibles:
        par_categorie["sensible"] = bloc(sensibles)
    verdict = _verdict(global_, par_champ, config, par_categorie)
    en_erreur = [champ for champ in par_champ if _a_des_erreurs(champ)]
    filtres = filtres or FiltresChamps()
    affiches = [c for c in (par_champ if tous_les_champs else en_erreur) if filtres.garde(c)]

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
        "par_section": _avec_libelles(
            _par(retenues, lambda ligne: ligne.get("section_id") or "?"), retenues
        ),
        "par_page": _par(retenues, lambda ligne: ligne.get("page") or "?"),
        "par_champ": affiches,
        "champs_sans_erreur": len(par_champ) - len(en_erreur),
        # « 6 champs sur 40 verifies » : ce que par_champ montre, sur quoi.
        "selection": {
            "filtres": filtres.actifs(),
            "champs": len(affiches),
            "champs_verifies": len(par_champ),
        },
        "categories_erreurs": dict(categories or {}),
        "echantillon": {
            "documents": documents,
            "champs_au_total": perimetre,
            # Les totaux ci-dessus somment tous les documents ; par document :
            "champs_par_document": round(perimetre / documents) if documents else None,
            "champs_verifies": verifies,
            # Champs regardes par un humain, sur le total : sous 1, une partie
            # de la verite manque, et les taux ne valent que pour elle.
            "part_verifiee": _arrondi(_ratio(verifies, perimetre)),
            "champs_exclus_par_config": len(lignes) - len(retenues),
            "trop_petit": documents < DOCUMENTS_MINIMUM,
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
        "verdict": verdict,
        "avertissements": _avertissements(
            global_, documents, verifies, perimetre, execution, retenues
        ),
    }


def _verdict(
    global_: Mapping[str, Any],
    par_champ: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    categories: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Reussi / echoue selon la config de la recette ; None sans seuil.

    Trois sortes de seuils : le score global minimal, un taux d'erreur maximal
    par champ, un taux d'erreur maximal par categorie (sensible, critique,
    standard). Une categorie sans champ juge ne fait pas echouer.
    """
    # seuil_f1 : nom d'avant, encore dans la config des recettes deja figees.
    score_minimal = config.get("score_minimal", config.get("seuil_f1"))
    seuils = config.get("seuils_par_champ") or {}
    seuils_categorie = config.get("seuils_par_categorie") or {}
    categories_en_echec = []
    for categorie, seuil_categorie in sorted(seuils_categorie.items()):
        taux_categorie = (categories or {}).get(categorie, {}).get("taux_erreur")
        if taux_categorie is not None and taux_categorie > float(seuil_categorie):
            categories_en_echec.append(
                {"categorie": categorie, "taux_erreur": taux_categorie, "seuil": seuil_categorie}
            )
    champs_en_echec = []
    for champ in par_champ:
        seuil = _seuil_du_champ(str(champ["champ"]), seuils)
        taux = champ["taux_erreur"]
        if seuil is not None and taux is not None and taux > seuil:
            champs_en_echec.append({"champ": champ["champ"], "taux_erreur": taux, "seuil": seuil})
    if score_minimal is None and not seuils and not seuils_categorie:
        return {
            "score_minimal": None,
            "reussi": None,
            "champs_en_echec": [],
            "categories_en_echec": [],
        }
    score = global_["score"]
    global_ok = score_minimal is None or (score is not None and score >= float(score_minimal))
    return {
        "score_minimal": score_minimal,
        "reussi": bool(global_ok and not champs_en_echec and not categories_en_echec),
        "champs_en_echec": champs_en_echec,
        "categories_en_echec": categories_en_echec,
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
            "exécution antérieure aux métriques : comptes non enregistrés, "
            "relancer la recette pour obtenir le score"
        )
    if documents < DOCUMENTS_MINIMUM:
        messages.append(
            f"échantillon trop petit : {documents} document(s), moins de {DOCUMENTS_MINIMUM}"
        )
    if not global_["assez_de_donnees"]:
        messages.append(
            f"pas assez de données : {global_['valeurs_jugees']} valeur(s) jugée(s), "
            f"moins de {EFFECTIF_MINIMAL}"
        )
    if perimetre and verifies < perimetre:
        messages.append(
            f"vérification partielle : {verifies} champ(s) vérifié(s) sur {perimetre} ; "
            "les taux ne valent que pour les champs regardés par un humain"
        )
    if execution.get("error_message"):
        messages.append(str(execution["error_message"]))
    return messages


def _points(x: Optional[float], y: Optional[float]) -> Optional[float]:
    """Ecart de y sur x en points de pourcentage, a 0,1 pres."""
    return round((y - x) * 100, 1) if x is not None and y is not None else None


def comparer(a: Mapping[str, Any], b: Mapping[str, Any]) -> Dict[str, Any]:
    """Compare deux resultats de calculer(tous_les_champs=True) : b par rapport a a.

    a est la reference (colonne « Ref. » de la page), b le passage analyse.
    La comparaison est toujours rendue, mais signalee non comparable si la
    recette, la version du comparateur, l'empreinte du schema ou le nombre de
    documents different : un ecart n'y mesurerait pas le moteur.

    ``par_champ`` liste tous les champs, presents d'un cote ou des deux, avec
    leur reussite de chaque cote et l'ecart en points : le front joint sur
    ``champ`` sans deviner si un champ absent est inchange. Les regressions
    d'abord.
    """
    ea = {**a["execution"], "documents": a["echantillon"]["documents"]}
    eb = {**b["execution"], "documents": b["echantillon"]["documents"]}
    raisons = [
        f"{libelle} differente"
        for cle, libelle in (
            ("recipe_id", "recette"),
            ("comparateur_version", "version du comparateur"),
            ("schema_hash", "empreinte du schema"),
        )
        if ea.get(cle) != eb.get(cle) or ea.get(cle) is None
    ]
    if ea["documents"] != eb["documents"]:
        raisons.append("nombre de documents different")
    indicateurs = (
        "score",
        "taux_lectures_justes",
        "taux_valeurs_trouvees",
        "taux_erreur",
        "taux_erreur_caracteres",
    )

    def delta(x: Optional[float], y: Optional[float]) -> Optional[float]:
        return round(y - x, 4) if x is not None and y is not None else None

    champs_a = {c["champ"]: c for c in a["par_champ"]}
    champs_b = {c["champ"]: c for c in b["par_champ"]}
    par_champ = []
    for cle in sorted(champs_a.keys() | champs_b.keys()):
        ca, cb = champs_a.get(cle), champs_b.get(cle)
        connu = cb or ca or {}
        par_champ.append(
            {
                "champ": cle,
                "section": connu.get("section"),
                "section_libelle": connu.get("section_libelle"),
                "present_a": ca is not None,
                "present_b": cb is not None,
                "reussite_a": ca["reussite"] if ca else None,
                "reussite_b": cb["reussite"] if cb else None,
                "ecart_pts": _points(
                    ca["reussite"] if ca else None, cb["reussite"] if cb else None
                ),
                "score_a": ca["score"] if ca else None,
                "score_b": cb["score"] if cb else None,
                "evolution": delta(ca["score"] if ca else None, cb["score"] if cb else None),
            }
        )
    par_champ.sort(key=lambda c: (c["ecart_pts"] is None, c["ecart_pts"] or 0, c["champ"]))
    inchanges = sum(
        1
        for c in par_champ
        if c["present_a"]
        and c["present_b"]
        and c["reussite_a"] == c["reussite_b"]
        and c["score_a"] == c["score_b"]
    )

    sections_a, sections_b = a["par_section"], b["par_section"]
    par_section = {}
    for section in sorted(sections_a.keys() | sections_b.keys()):
        sa, sb = sections_a.get(section), sections_b.get(section)
        taux_a = sa["taux_lectures_justes"] if sa else None
        taux_b = sb["taux_lectures_justes"] if sb else None
        par_section[section] = {
            "libelle": (sb or sa or {}).get("libelle", section),
            "taux_lectures_justes_a": taux_a,
            "taux_lectures_justes_b": taux_b,
            "ecart_pts": _points(taux_a, taux_b),
        }

    return {
        "a": ea,
        "b": eb,
        "comparable": not raisons,
        "raisons": raisons,
        "global": {
            nom: {
                "a": a["global"][nom],
                "b": b["global"][nom],
                "evolution": delta(a["global"][nom], b["global"][nom]),
            }
            for nom in indicateurs
        },
        "par_section": par_section,
        "par_champ": par_champ,
        "champs_inchanges": inchanges,
    }
