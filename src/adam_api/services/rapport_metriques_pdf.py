"""PDF du rapport de qualite d'extraction, a l'identique de la maquette retenue.

La maquette (« PDF genere par les filtres », 794 x 1123 px, soit une page A4)
est reproduite element par element : chaque cote ci-dessous est celle que le
navigateur donne a la maquette, en pixels, convertie en points. Le moteur HTML
de PyMuPDF ne sait ni les boites flexibles, ni la grille, ni l'anneau en
degrade : tout est donc dessine a sa place, avec les polices de la maquette
(Inter, et une police a chasse fixe pour les cles), livrees dans ``polices/``
sous licence OFL.

Une page A4, puis autant de pages que le tableau des champs en demande ; les
extraits suivent le tableau. Chaque page porte le pied « Page n / N ».

Ecart assume avec la maquette : les extraits ne montrent pas de decoupe de
la page autour du champ. Le moteur OCR ne rend pas de position ; la decoupe
est abandonnee et les cartes se resserrent.

Un champ sensible ne montre jamais de valeur, meme si on lui en passait une.
"""

from __future__ import annotations

import html
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

import pymupdf

Couleur = Tuple[float, float, float]
Champ = Mapping[str, Any]

# -- Echelle et polices ----------------------------------------------------------------

#: Pixels de la maquette -> points PDF : 794 px de large font une page A4.
_A4 = pymupdf.Rect(0, 0, 595.2756, 841.8898)  # A4 exact ; paper_rect l'arrondit
_K = _A4.width / 794

_POLICES = Path(__file__).with_name("polices")


class _Police:
    """Une police de la maquette.

    Le fichier de ``polices/`` s'il est la ; sinon la police integree a
    PyMuPDF (Helvetica, Helvetica gras, Courier) : le PDF reste juste, a peine
    moins fidele a la maquette, et un depot peut se passer des fichiers.
    """

    def __init__(self, nom: str, fichier: str, interne: str, crenage: bool = True) -> None:
        self.nom = nom
        self.chemin = _POLICES / fichier
        self.interne = interne
        #: Faconner le texte comme le navigateur (crenage) ; inutile a chasse fixe.
        self.crenage = crenage
        self._places: Dict[Tuple[str, float], Tuple[str, List[float], float]] = {}
        self._font: Optional[pymupdf.Font] = None
        self._largeurs: Dict[Tuple[str, float], float] = {}

    @property
    def font(self) -> pymupdf.Font:
        """La police chargee une fois, pour mesurer et pour ecrire."""
        if self._font is None:
            if self.chemin.is_file():
                self._font = pymupdf.Font(fontfile=str(self.chemin))
            else:
                self._font = pymupdf.Font(self.interne)
        return self._font

    @property
    def ascendant(self) -> float:
        """Hauteur au-dessus de la ligne de base, en fraction de la taille."""
        return float(self.font.ascender)

    def glyphes(self, texte: str) -> str:
        """Identifiants des glyphes, en hexadecimal, pour l'operateur TJ."""
        return "".join(f"{self.font.has_glyph(ord(c)):04x}" for c in texte)

    def largeur(self, texte: str, taille: float) -> float:
        """Largeur en pixels de maquette, crenage compris."""
        if self.crenage and len(texte) > 1:
            return self.placer(texte, taille)[2]
        cle = (texte, taille)
        if cle not in self._largeurs:
            self._largeurs[cle] = float(self.font.text_length(texte, fontsize=taille))
        return self._largeurs[cle]

    def morceaux_places(
        self, texte: str, taille: float, abscisses: Sequence[float]
    ) -> List[Tuple[float, str]]:
        """Decoupe le texte en morceaux dont les lettres tombent a leur avance simple."""
        morceaux: List[Tuple[float, str]] = []
        debut, courant, attendue = 0.0, "", 0.0
        for caractere, x in zip(texte, abscisses):
            if courant and abs(x - attendue) > 0.01:
                morceaux.append((debut, courant))
                courant = ""
            if not courant:
                debut, attendue = x, x
            courant += caractere
            attendue += self.largeur(caractere, taille)
        if courant:
            morceaux.append((debut, courant))
        return morceaux

    def placer(self, texte: str, taille: float) -> Tuple[str, List[float], float]:
        """Lettres a dessiner, abscisse de chacune et largeur, faconnees par HarfBuzz.

        Le navigateur applique le crenage d'Inter et ses variantes contextuelles
        (dont il ne garde que les places) ; PyMuPDF ne le fait qu'en mettant
        du HTML en page. Le texte y est donc mis une fois, sur une page de
        brouillon, pour relever chaque lettre et sa place (mis en cache). Sans
        correspondance lettre a lettre (ligature), on revient aux avances
        simples.
        """
        cle = (texte, taille)
        if cle in self._places:
            return self._places[cle]
        simples = [float(self.font.text_length(c, fontsize=taille)) for c in texte]
        abscisses = [sum(simples[:i]) for i in range(len(texte))]
        resultat = (texte, abscisses, sum(simples))
        corps = texte.lstrip(" ")
        if self.crenage and corps.strip():
            # insert_htmlbox retire les espaces de tete : on les remet a la main.
            tete = len(texte) - len(corps)
            decalage = sum(simples[:tete])
            lettres = _faconner(self, corps, taille)
            if len(lettres) == len(corps) and all(
                c == o or 0xE000 <= ord(c) <= 0xF8FF for (c, _), o in zip(lettres, corps)
            ):
                depart = lettres[0][1]
                places = [decalage + x - depart for _, x in lettres]
                # On garde les lettres d'origine, aux places faconnees : une
                # variante en zone privee rendrait le texte du PDF faux
                # (recherche, copier-coller) pour 1 px de hauteur de crochet.
                resultat = (texte, abscisses[:tete] + places, places[-1] + simples[-1])
        self._places[cle] = resultat
        return resultat


# Graisses de la maquette ; sans fichier, le moyen et le demi-gras deviennent
# du regulier et du gras.
_REGULIER = _Police("inter-4", "Inter-Regular.ttf", "helv")
_MOYEN = _Police("inter-5", "Inter-Medium.ttf", "helv")
_DEMI_GRAS = _Police("inter-6", "Inter-SemiBold.ttf", "hebo")
_GRAS = _Police("inter-7", "Inter-Bold.ttf", "hebo")
_FIXE = _Police("mono-4", "JetBrainsMono-Regular.ttf", "cour", crenage=False)

_BROUILLON = pymupdf.Rect(0, 0, 4000, 200)


def _archive(police: _Police) -> pymupdf.Archive:
    """La police, fichier ou integree, sous le nom que la CSS reclame."""
    archive = pymupdf.Archive()
    archive.add(police.font.buffer, f"{police.nom}.ttf")
    return archive


def _faconner(police: _Police, texte: str, taille: float) -> List[Tuple[str, float]]:
    """(lettre, abscisse) de chaque lettre, telle que HarfBuzz la place."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=_BROUILLON.width, height=_BROUILLON.height)
        css = (
            f"@font-face{{font-family:F;src:url({police.nom}.ttf)}}"
            f"*{{font-family:F;font-size:{taille}px;white-space:pre;margin:0}}"
        )
        page.insert_htmlbox(_BROUILLON, html.escape(texte), css=css, archive=_archive(police))
        return [
            (c["c"], float(c["origin"][0]))
            for bloc in page.get_text("rawdict")["blocks"]
            for ligne in bloc.get("lines", [])
            for span in ligne["spans"]
            for c in span["chars"]
        ]
    finally:
        document.close()


# -- Couleurs de la maquette -----------------------------------------------------------


def _rgb(hexa: str) -> Couleur:
    return (int(hexa[1:3], 16) / 255, int(hexa[3:5], 16) / 255, int(hexa[5:7], 16) / 255)


_TEXTE = _rgb("#212b36")
_GRIS = _rgb("#637381")
_BLEU = _rgb("#003da5")
_BORD = _rgb("#c1c7d0")
_FOND = _rgb("#f7f8fa")
_LIGNE = _rgb("#eeeeee")
_BLANC = _rgb("#ffffff")

#: Etiquette de l'echec principal : libelle, fond, texte, bordure, tirets.
_ETIQUETTES: Dict[str, Tuple[str, Couleur, Couleur, Couleur, str]] = {
    "fausse": ("Lu mais faux", _rgb("#f7e4e5"), _rgb("#812424"), _rgb("#dc3838"), ""),
    # Motifs en points : tirets de 3 px et blancs de 2 px, pointilles de 1 px.
    "manquee": (
        "Perdu",
        _rgb("#f8efda"),
        _rgb("#6c3917"),
        _rgb("#a47a10"),
        f"[{3 * _K:.4f} {2 * _K:.4f}] 0",
    ),
    "inventee": (
        "Inventé",
        _rgb("#e8f0f9"),
        _rgb("#002057"),
        _rgb("#0070d1"),
        f"[{_K:.4f} {_K:.4f}] 0",
    ),
}
_TYPES = {
    "TEXT": "TEXTE",
    "NUMBER": "NOMBRE",
    "DATE": "DATE",
    "DATETIME": "DATE ET HEURE",
    "BOOLEAN": "CASE À COCHER",
}

# -- Geometrie de la maquette (px) -----------------------------------------------------

_GAUCHE, _DROITE = 56.0, 738.0
_HAUT = 48.0
_ESPACE = 18.0  # ecart entre les blocs
_PIED_Y = 1051.0  # trait du pied de page
_BAS = _PIED_Y - _ESPACE  # le contenu s'arrete la

#: Bords des colonnes du tableau, de gauche a droite.
_COLONNES = (56.5, 392.3, 496.5, 576.48, 737.5)
_ENTETE_TABLEAU = 26.5
_PADDING = 8.0

_CARTE_LARGEUR = (682 - 2 * 10) / 3  # 220,67 : trois cartes et deux ecarts de 10
_CARTE_ECART = 10.0

#: Documents demandes par champ pour les extraits : une carte par champ.
EXTRAITS_PAR_CHAMP = 1
#: Cartes d'extraits au plus : quatre rangees de trois.
CHAMPS_AVEC_EXTRAITS = 12


# -- Primitives ------------------------------------------------------------------------


class _Page:
    """Une page ou l'on dessine en pixels de maquette.

    Formes et textes s'accumulent et s'ecrivent une fois, a la fin (``fin``) :
    ecrire chaque texte a part refaisait le contenu de la page a chaque appel,
    11 s pour 642 champs.
    """

    def __init__(self, page: pymupdf.Page) -> None:
        self.page = page
        self.forme = page.new_shape()
        self._polices: Set[str] = set()

    def _r(self, x: float, y: float, largeur: float, hauteur: float) -> pymupdf.Rect:
        return pymupdf.Rect(x * _K, y * _K, (x + largeur) * _K, (y + hauteur) * _K)

    def rect(
        self,
        x: float,
        y: float,
        largeur: float,
        hauteur: float,
        *,
        fond: Optional[Couleur] = None,
        bord: Optional[Couleur] = None,
        rayon: float = 0.0,
        tirets: str = "",
    ) -> None:
        """Rectangle comme en CSS : le fond couvre toute la boite, sous la
        bordure de 1 px, tracee a l'interieur avec un rayon reduit d'autant.

        Comme Chrome a l'impression, la boite est calee sur le pixel entier
        (bords arrondis au plus proche) ; le texte, lui, garde sa position.
        """
        x0, y0 = math.floor(x + 0.5), math.floor(y + 0.5)
        x1, y1 = math.floor(x + largeur + 0.5), math.floor(y + hauteur + 0.5)
        x, y, largeur, hauteur = x0, y0, x1 - x0, y1 - y0

        def relatif(rayon_: float, l: float, h: float) -> Optional[float]:
            return min(rayon_ / max(min(l, h), 1e-6), 0.5) if rayon_ > 0 else None

        if fond is not None:
            self.forme.draw_rect(
                self._r(x, y, largeur, hauteur), radius=relatif(rayon, largeur, hauteur)
            )
            self.forme.finish(color=None, fill=fond, width=0)
        if bord is not None:
            l, h = largeur - 1, hauteur - 1
            self.forme.draw_rect(self._r(x + 0.5, y + 0.5, l, h), radius=relatif(rayon - 0.5, l, h))
            self.forme.finish(color=bord, fill=None, width=_K, dashes=tirets or None)

    def trait(self, x0: float, x1: float, y: float, couleur: Couleur) -> None:
        """Trait horizontal de 1 px, centre sur y."""
        self.forme.draw_line(pymupdf.Point(x0 * _K, y * _K), pymupdf.Point(x1 * _K, y * _K))
        self.forme.finish(color=couleur, width=_K)

    def texte(
        self, x: float, y: float, texte: str, police: _Police, taille: float, couleur: Couleur
    ) -> float:
        """Texte dont la boite de ligne commence en y ; rend sa largeur (px).

        Comme Chrome, la ligne de base tombe sur le pixel entier :
        y + arrondi(ascendant x taille). Chaque morceau est pose a sa position
        absolue : un TextWriter les fondait dans un seul tableau TJ, dont les
        ajustements tronques derivaient jusqu'a 0,5 px en fin de ligne.
        """
        if police.nom not in self._polices:
            self.page.insert_font(fontname=police.nom, fontbuffer=police.font.buffer)
            self._polices.add(police.nom)
        base = (y + round(police.ascendant * taille)) * _K
        if not police.crenage or len(texte) < 2:
            morceaux: List[Tuple[float, str]] = [(0.0, texte)]
            largeur = police.largeur(texte, taille)
        else:
            dessin, abscisses, largeur = police.placer(texte, taille)
            morceaux = police.morceaux_places(dessin, taille, abscisses)
        # Operateurs ecrits a la main, comme Shape.insert_text les ecrit : lui
        # relit toutes les polices de la page a chaque appel (14 s sur 642
        # champs). Police inseree en Identity-H : un glyphe = 4 chiffres hexa.
        teinte = " ".join(f"{c:g}" for c in couleur)
        hauteur = self.page.rect.height
        for debut, morceau in morceaux:
            if morceau.strip():
                self.forme.text_cont += (
                    f"\nq\nBT\n1 0 0 1 {(x + debut) * _K:g} {hauteur - base:g} Tm\n"
                    f"/{police.nom} {taille * _K:g} Tf {teinte} rg "
                    f"[<{police.glyphes(morceau)}>]TJ\nET\nQ\n"
                )
        return largeur

    def morceaux(
        self, x: float, y: float, morceaux: Sequence[Tuple[str, _Police, Couleur]], taille: float
    ) -> None:
        """Une ligne faite de morceaux de styles differents."""
        for texte, police, couleur in morceaux:
            x += self.texte(x, y, texte, police, taille, couleur)

    def fin(self) -> None:
        """Ecrit formes et textes, dans l'ordre ou ils ont ete poses."""
        self.forme.commit()


def _couper(texte: str, police: _Police, taille: float, largeur: float) -> List[str]:
    """Coupe au caractere (word-break: break-all) pour tenir dans la largeur."""
    lignes: List[str] = []
    courante, occupee = "", 0.0
    for caractere in texte:
        ajout = police.largeur(caractere, taille)
        if courante and occupee + ajout > largeur:
            lignes.append(courante)
            courante, occupee = caractere, ajout
        else:
            courante, occupee = courante + caractere, occupee + ajout
    return lignes + [courante] if courante or not lignes else lignes


def _nombre(n: Any) -> str:
    return f"{int(n or 0):,}".replace(",", " ")


def _pourcent(taux: Optional[float]) -> str:
    return "—" if taux is None else f"{round(taux * 100)} %"


# -- Blocs de la premiere page ---------------------------------------------------------


def _entete(
    p: _Page,
    metriques: Mapping[str, Any],
    dataset: Optional[str],
    recette: Mapping[str, Any],
    edite_le: datetime,
) -> float:
    execution = metriques["execution"]
    documents = int(metriques["echantillon"]["documents"] or 0)
    p.texte(_GAUCHE, 48, "NOTA · Rapport de qualité d'extraction", _REGULIER, 11, _GRIS)
    p.texte(
        _GAUCHE, 66, f"Dataset {dataset or '—'} · recette #{recette.get('id')}", _GRAS, 20, _TEXTE
    )
    moteur = execution.get("ocr_provider") or execution.get("ocr_model_id") or "inconnu"
    lignes = (
        f"Moteur : {moteur} · {_nombre(documents)} document{'s' if documents > 1 else ''}",
        f"Édité le {edite_le.strftime('%d/%m/%Y')}",
    )
    for i, ligne in enumerate(lignes):
        p.texte(_DROITE - _REGULIER.largeur(ligne, 11), 62 + 14 * i, ligne, _REGULIER, 11, _GRIS)
    p.rect(_GAUCHE, 102, _DROITE - _GAUCHE, 3, fond=_BLEU)
    return 105


def _anneau(p: _Page, cx: float, cy: float, taux: Optional[float]) -> None:
    """Anneau de 72 px : la part bleue part de midi, dans le sens horaire."""
    rayon, epaisseur = 31.5, 9.0
    centre = pymupdf.Point(cx * _K, cy * _K)
    forme = p.forme
    forme.draw_circle(centre, rayon * _K)
    forme.finish(color=_BORD, width=epaisseur * _K)
    part = max(0.0, min(1.0, taux or 0.0))
    if part >= 1.0:
        forme.draw_circle(centre, rayon * _K)
        forme.finish(color=_BLEU, width=epaisseur * _K)
    elif part > 0:
        midi = pymupdf.Point(cx * _K, (cy - rayon) * _K)
        # Angle negatif : sens horaire a l'ecran (l'axe y du PDF descend).
        forme.draw_sector(centre, midi, -part * 360, fullSector=False)
        forme.finish(color=_BLEU, width=epaisseur * _K, closePath=False, lineCap=0)


def _taux(p: _Page, y: float, metriques: Mapping[str, Any]) -> float:
    g = metriques["global"]
    p.rect(_GAUCHE, y, _DROITE - _GAUCHE, 98, fond=_FOND, bord=_BORD, rayon=5)
    # Le champ qui porte le nom du libelle : la page lit le meme.
    taux = g.get("taux_lectures_justes")
    _anneau(p, 109, y + 49, taux)
    texte = _pourcent(taux)
    p.texte(109 - _GRAS.largeur(texte, 16) / 2, y + 39, texte, _GRAS, 16, _TEXTE)
    # Sur tout ce que le moteur a ecrit : justes, fausses et inventees.
    ecrites = int(g["justes"]) + int(g["fausses"]) + int(g["inventees"])
    p.morceaux(
        161,
        y + 32,
        (
            ("Taux de lectures justes", _GRAS, _TEXTE),
            (
                f" · {_nombre(g['justes'])} lus correctement sur {_nombre(ecrites)}",
                _REGULIER,
                _TEXTE,
            ),
        ),
        12,
    )
    marge = g.get("fourchette_lectures_justes")
    if marge:
        ligne = f"Marge d'incertitude : {_pourcent(marge[0])} à {_pourcent(marge[1])}"
        p.texte(161, y + 50, ligne, _REGULIER, 12, _GRIS)
    return y + 98


def _libelle_filtres(selection: Mapping[str, Any], sections: Mapping[str, Any]) -> List[str]:
    f = selection.get("filtres") or {}
    seuil = f.get("reussite_inferieure_a")
    types = ", ".join(_TYPES.get(t.upper(), t) for t in f.get("types_champ", []))
    erreurs = ", ".join(
        _ETIQUETTES[t][0] if t in _ETIQUETTES else t for t in f.get("types_erreur", [])
    )
    morceaux = [
        f"Réussite : < {_pourcent(seuil)}" if seuil is not None else "Réussite : toutes",
        f"Type de champ : {types or 'tous'}",
        f"Type d'erreur : {erreurs or 'tous'}",
    ]
    if f.get("sections"):
        libelles = (sections.get(s_, {}).get("libelle") or s_ for s_ in f["sections"])
        morceaux.append("Section : " + ", ".join(libelles))
    if f.get("recherche"):
        morceaux.append(f"Recherche : « {f['recherche']} »")
    return morceaux


def _filtres(p: _Page, y: float, metriques: Mapping[str, Any]) -> float:
    """Encadre des filtres ; la ligne passe a la ligne entre deux filtres quand
    elle deborde (plusieurs sections choisies, par exemple)."""
    selection = metriques.get("selection") or {}
    champs = int(selection.get("champs", len(metriques.get("par_champ") or [])))
    verifies = _nombre(selection.get("champs_verifies", 0))
    # Chaque groupe reste sur une ligne ; « N champs sur M verifies » est le dernier.
    largeur_max = _DROITE - 15 - 71
    groupes: List[List[Tuple[str, _Police]]] = []
    for filtre in _libelle_filtres(selection, metriques.get("par_section") or {}):
        texte = f"{filtre} · "
        if _REGULIER.largeur(texte, 11.5) <= largeur_max:
            groupes.append([(texte, _REGULIER)])
            continue
        # Un filtre plus large qu'une ligne (beaucoup de sections) se coupe
        # entre ses valeurs.
        valeurs = filtre.split(", ")
        for i, valeur in enumerate(valeurs):
            fin = ", " if i < len(valeurs) - 1 else " · "
            groupes.append([(valeur + fin, _REGULIER)])
    groupes.append(
        [
            (f"{_nombre(champs)} champ{'s' if champs > 1 else ''}", _GRAS),
            (f" sur {verifies} vérifiés", _REGULIER),
        ]
    )
    lignes: List[List[Tuple[str, _Police]]] = [[]]
    occupee = 0.0
    for groupe in groupes:
        largeur = sum(police.largeur(texte, 11.5) for texte, police in groupe)
        if lignes[-1] and occupee + largeur > largeur_max:
            lignes.append([])
            occupee = 0.0
        lignes[-1].extend(groupe)
        occupee += largeur
    hauteur = 54 + 14 * (len(lignes) - 1)
    p.rect(_GAUCHE, y, _DROITE - _GAUCHE, hauteur, bord=_BLEU, rayon=5)
    p.texte(71, y + 11, "Filtres appliqués à ce rapport", _GRAS, 11.5, _BLEU)
    for i, ligne in enumerate(lignes):
        p.morceaux(71, y + 29 + 14 * i, [(t, pol, _TEXTE) for t, pol in ligne], 11.5)
    return y + hauteur


# -- Tableau des champs ----------------------------------------------------------------


def _entete_tableau(p: _Page, y: float) -> float:
    haut = y + 0.5
    p.rect(_COLONNES[0], haut, _COLONNES[-1] - _COLONNES[0], _ENTETE_TABLEAU, fond=_BLEU)
    for i, titre in enumerate(("Champ", "Type", "Réussite", "Échec principal")):
        # « Champ » suit les cles : +0,5 comme elles.
        decalage = 0.5 if i == 0 else 0.0
        p.texte(_COLONNES[i] + _PADDING + decalage, haut + 6.5, titre, _MOYEN, 11, _BLANC)
    return haut + _ENTETE_TABLEAU


def _lignes_cle(champ: Champ) -> List[str]:
    largeur = _COLONNES[1] - _COLONNES[0] - 2 * _PADDING
    return _couper(str(champ["champ"]), _FIXE, 10.5, largeur)


def _hauteur_ligne(champ: Champ) -> float:
    """41 px pour une cle sur une ligne : 7 + 14 (cle) + 12 (section) + 8."""
    return 7 + 14 * len(_lignes_cle(champ)) + 12 + 8


def _ligne_tableau(p: _Page, y: float, champ: Champ) -> float:
    lignes = _lignes_cle(champ)
    hauteur = _hauteur_ligne(champ)
    x = _COLONNES[0] + _PADDING + 0.5
    for i, morceau in enumerate(lignes):
        p.texte(x, y + 7 + 14 * i, morceau, _FIXE, 10.5, _TEXTE)
    section = str(champ.get("section_libelle") or champ.get("section") or "")
    p.texte(x, y + 7 + 14 * len(lignes), section, _REGULIER, 10, _GRIS)
    # Les autres cellules sont centrees verticalement (vertical-align: middle).
    # Ligne de base mesuree sur la maquette : y + 24 pour une ligne de 41 px.
    base = y + (hauteur - 41) / 2 + 24
    haut_texte = base - round(11.5 * _REGULIER.ascendant)
    type_ = str(champ.get("type") or "").upper()
    libelle_type = _TYPES.get(type_, type_ or "—")
    p.texte(_COLONNES[1] + _PADDING, haut_texte, libelle_type, _REGULIER, 11.5, _TEXTE)
    p.texte(
        _COLONNES[2] + _PADDING, haut_texte, _pourcent(champ.get("reussite")), _GRAS, 11.5, _TEXTE
    )
    echec = champ.get("echec_principal")
    if echec in _ETIQUETTES:
        libelle, fond, couleur, bord, tirets = _ETIQUETTES[echec]
        haut = y + (hauteur - 18) / 2 - 0.5
        largeur = _DEMI_GRAS.largeur(libelle, 11) + 18
        x_etiquette = _COLONNES[3] + _PADDING
        p.rect(x_etiquette, haut, largeur, 18, fond=fond, bord=bord, rayon=4, tirets=tirets)
        # Meme ligne de base que le texte de la cellule.
        p.texte(
            x_etiquette + 9,
            base - round(11 * _DEMI_GRAS.ascendant),
            libelle,
            _DEMI_GRAS,
            11,
            couleur,
        )
    p.trait(_COLONNES[0], _COLONNES[-1], y + hauteur - 0.5, _LIGNE)
    return y + hauteur


# -- Extraits --------------------------------------------------------------------------


def _valeur(ecart: Mapping[str, Any], cle: str) -> str:
    if ecart.get("sensitive"):
        return "(masquée)"
    valeur = ecart.get(cle)
    if valeur is None or not str(valeur).strip():
        return "(vide)"
    return str(valeur)


def _lignes_carte(champ: Champ) -> List[str]:
    return _couper(str(champ["champ"]), _FIXE, 10, _CARTE_LARGEUR - 18)


def _hauteur_carte(champ: Champ) -> float:
    """70 px pour une cle sur une ligne : 9 + 13 (cle) + 5 + 12 (document) + 5 + 12 + 9.

    La maquette placait entre la cle et le document une decoupe de la page
    autour du champ ; elle est abandonnee (le moteur OCR ne rend pas de
    position), la carte se resserre d'autant.
    """
    return 9 + 13 * len(_lignes_carte(champ)) + 5 + 12 + 5 + 12 + 9


def _carte(p: _Page, x: float, y: float, hauteur: float, champ: Champ, ecart: Champ) -> None:
    p.rect(x, y, _CARTE_LARGEUR, hauteur, bord=_BORD, rayon=5)
    interieur = x + 9
    lignes = _lignes_carte(champ)
    for i, morceau in enumerate(lignes):
        p.texte(interieur, y + 9 + 13 * i, morceau, _FIXE, 10, _TEXTE)
    bas = y + 9 + 13 * len(lignes) + 5
    ligne = f"Doc #{ecart.get('document_id')} · page {ecart.get('page')}"
    p.texte(interieur, bas, ligne, _REGULIER, 10, _GRIS)
    p.morceaux(
        interieur,
        bas + 17,
        (
            ("Attendu :", _REGULIER, _GRIS),
            (" ", _REGULIER, _TEXTE),
            (_valeur(ecart, "expected_value"), _GRAS, _TEXTE),
            (" · ", _REGULIER, _TEXTE),
            ("Lu :", _REGULIER, _GRIS),
            (" ", _REGULIER, _TEXTE),
            (_valeur(ecart, "observed_value"), _GRAS, _TEXTE),
        ),
        10,
    )


# -- Mise en pages ---------------------------------------------------------------------


class _Mise:
    """La page courante et la hauteur deja occupee."""

    def __init__(self, document: pymupdf.Document) -> None:
        self.document = document
        self.page = _Page(document.new_page(width=_A4.width, height=_A4.height))
        self.y = _HAUT

    def nouvelle_page(self) -> None:
        # Une page est ecrite avant d'ouvrir la suivante : PyMuPDF ne garde pas
        # vivants les objets Page d'un document qui grandit.
        self.page.fin()
        self.page = _Page(self.document.new_page(width=_A4.width, height=_A4.height))
        self.y = _HAUT

    def tient(self, hauteur: float) -> bool:
        return self.y + hauteur <= _BAS

    def titre(self, texte: str, apres: float) -> None:
        self.page.texte(_GAUCHE, self.y, texte, _GRAS, 14, _TEXTE)
        self.y += 17 + apres


def _tableau(m: _Mise, champs: Sequence[Champ]) -> None:
    if not champs:
        m.titre("Champs en erreur", 6)
        m.page.texte(_GAUCHE, m.y, "Aucun champ ne correspond aux filtres.", _REGULIER, 11.5, _GRIS)
        m.y += 14
        return
    titre = "Champs en erreur"
    restants = list(champs)
    while restants:
        if not m.tient(17 + 6 + 0.5 + _ENTETE_TABLEAU + _hauteur_ligne(restants[0])):
            m.nouvelle_page()
        m.titre(titre, 6)
        debut = m.y
        m.y = _entete_tableau(m.page, m.y)
        filets = []
        while restants and m.tient(_hauteur_ligne(restants[0])):
            m.y = _ligne_tableau(m.page, m.y, restants.pop(0))
            filets.append(m.y - 0.5)
        # Bordure du tableau, puis les filets des lignes par-dessus : en CSS,
        # ils coupent les bordures laterales et remplacent celle du bas.
        m.page.rect(_GAUCHE, debut, _DROITE - _GAUCHE, m.y - debut, bord=_BORD)
        for filet in filets:
            m.page.trait(_GAUCHE, _DROITE, filet, _LIGNE)
        if restants:
            m.nouvelle_page()
            titre = "Champs en erreur (suite)"


def _extraits(m: _Mise, cartes: Sequence[Tuple[Champ, Champ]]) -> None:
    rangees = [cartes[i : i + 3] for i in range(0, len(cartes), 3)]
    for index, rangee in enumerate(rangees):
        hauteur = max(_hauteur_carte(champ) for champ, _ in rangee)
        avec_titre = index == 0
        if not m.tient((17 + 8 if avec_titre else 0) + hauteur):
            m.nouvelle_page()
            avec_titre = True
        if avec_titre:
            suite = " (suite)" if index else ""
            m.titre(f"Extraits de documents en erreur{suite}", 8)
        for colonne, (champ, ecart) in enumerate(rangee):
            x = _GAUCHE + colonne * (_CARTE_LARGEUR + _CARTE_ECART)
            _carte(m.page, x, m.y, hauteur, champ, ecart)
        m.y += hauteur + _CARTE_ECART


def _pieds(document: pymupdf.Document, metriques: Mapping[str, Any]) -> None:
    execution = metriques["execution"]
    gauche = (
        f"Généré par NOTA · comparateur v{execution.get('comparateur_version') or '—'} · "
        f"schéma {str(execution.get('schema_hash') or '—')[:8]}"
    )
    total = document.page_count
    for numero in range(total):
        p = _Page(document[numero])
        p.trait(_GAUCHE, _DROITE, _PIED_Y + 0.5, _BORD)
        p.texte(_GAUCHE, 1062, gauche, _REGULIER, 10.5, _GRIS)
        droite = f"Page {numero + 1} / {total}"
        p.texte(_DROITE - _REGULIER.largeur(droite, 10.5), 1062, droite, _REGULIER, 10.5, _GRIS)
        p.fin()


def rendre_pdf(
    metriques: Mapping[str, Any],
    *,
    recette: Mapping[str, Any],
    dataset: Optional[str],
    extraits: Mapping[str, Sequence[Mapping[str, Any]]],
    edite_le: datetime,
) -> bytes:
    """Le PDF du rapport, a l'identique de la maquette.

    Args:
        metriques: la reponse de /metriques, filtres compris.
        recette: au moins ``id``.
        dataset: le nom du dataset.
        extraits: par champ (par_champ[].champ), des ecarts tels que /ecarts
            les rend ; le premier fait la carte du champ.
        edite_le: la date imprimee.
    """
    document = pymupdf.open()
    m = _Mise(document)
    m.y = _entete(m.page, metriques, dataset, recette, edite_le) + _ESPACE
    m.y = _taux(m.page, m.y, metriques) + _ESPACE
    m.y = _filtres(m.page, m.y, metriques) + _ESPACE
    champs: Sequence[Champ] = metriques.get("par_champ") or []
    _tableau(m, champs)
    m.y += _ESPACE
    cartes = [
        (champ, extraits[champ["champ"]][0]) for champ in champs if extraits.get(champ["champ"])
    ][:CHAMPS_AVEC_EXTRAITS]
    _extraits(m, cartes)
    m.page.fin()
    _pieds(document, metriques)
    document.subset_fonts()
    sortie: bytes = document.tobytes(garbage=4, deflate=True)
    document.close()
    return sortie


def extraits_a_montrer(par_champ: Sequence[Champ]) -> List[str]:
    """Les champs dont le PDF montre un extrait : les pires, en erreur."""
    return [c["champ"] for c in par_champ if c.get("documents_en_erreur")][:CHAMPS_AVEC_EXTRAITS]


def dict_ecarts(ecarts: Sequence[Any]) -> List[Dict[str, Any]]:
    """EcartOut -> dict, pour rendre_pdf."""
    return [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in ecarts]
