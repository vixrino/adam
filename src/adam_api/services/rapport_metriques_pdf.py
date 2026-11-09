"""PDF du rapport de qualite d'extraction : les metriques d'un test, filtrees.

Il reprend la maquette retenue (« PDF genere par les filtres ») : le taux de
valeurs bien lues et sa marge d'incertitude, la repartition des champs
verifies, les filtres appliques, le tableau des champs en erreur, puis des
extraits des documents en erreur (valeur attendue, valeur lue).

Fonction pure : elle recoit ce que rendent deja /metriques et /ecarts, et rend
les octets du PDF. La mise en page est faite par PyMuPDF (Story, du HTML mis
en pages), deja utilise pour les images de page : aucune dependance en plus.

Un champ sensible ne montre jamais de valeur, meme si on lui en passait une :
« valeur masquee » a la place.
"""

from __future__ import annotations

import html
import io
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pymupdf

#: A4 en points, et la zone ou le texte s'ecrit (le bas garde le pied de page).
_PAGE = pymupdf.paper_rect("a4")
_ZONE = _PAGE + (40, 40, -40, -60)
_PIED = pymupdf.Rect(40, _PAGE.height - 45, _PAGE.width - 40, _PAGE.height - 25)

#: Nombre de documents montres par champ, dans les extraits.
EXTRAITS_PAR_CHAMP = 3
#: Champs dont on montre des extraits, les pires d'abord.
CHAMPS_AVEC_EXTRAITS = 20

_ECHECS = {
    "fausse": "Lu, mais faux",
    "manquee": "Présent, non lu",
    "inventee": "Lu alors que vide",
}
_TYPES = {
    "TEXT": "Texte",
    "NUMBER": "Nombre",
    "DATE": "Date",
    "DATETIME": "Date et heure",
    "BOOLEAN": "Case à cocher",
}

_CSS = """
* { font-family: sans-serif; }
body { font-size: 9pt; color: #1f2328; }
h1 { font-size: 15pt; margin: 0 0 2pt 0; }
h2 { font-size: 11pt; margin: 14pt 0 4pt 0; }
.sous-titre { color: #57606a; margin: 0 0 10pt 0; }
.taux { font-size: 26pt; font-weight: bold; margin: 0; }
.legende { color: #57606a; }
.alerte { border-left: 3px solid #d4a72c; padding: 2pt 0 2pt 6pt; margin: 6pt 0; }
.verdict-ok { color: #1a7f37; font-weight: bold; }
.verdict-ko { color: #cf222e; font-weight: bold; }
table { border-collapse: collapse; width: 100%; }
th { text-align: left; border-bottom: 1px solid #8c959f; padding: 3pt 4pt; font-size: 8pt; }
td { border-bottom: 1px solid #d0d7de; padding: 3pt 4pt; vertical-align: top; }
.num { text-align: right; }
.section { color: #57606a; font-size: 8pt; }
.extrait { border-left: 2px solid #d0d7de; padding: 2pt 0 2pt 6pt; margin: 4pt 0; }
.valeur { font-family: monospace; }
"""


def _e(valeur: Any) -> str:
    return html.escape(str(valeur), quote=True)


def _nombre(n: Any) -> str:
    """2400 -> « 2 400 », espace insecable."""
    return f"{int(n or 0):,}".replace(",", " ")


def _pourcent(taux: Optional[float], decimales: int = 0) -> str:
    if taux is None:
        return "—"
    return f"{taux * 100:.{decimales}f} %".replace(".", ",")


def _date(valeur: Any) -> str:
    if isinstance(valeur, datetime):
        return valeur.strftime("%d/%m/%Y")
    if isinstance(valeur, str) and valeur:
        try:
            return datetime.fromisoformat(valeur).strftime("%d/%m/%Y")
        except ValueError:
            return valeur
    return "—"


def _filtres(selection: Mapping[str, Any]) -> str:
    """« Reussite : < 70 % · Type de champ : Nombre · ... », tous les filtres."""
    f = selection.get("filtres") or {}
    seuil = f.get("reussite_inferieure_a")
    morceaux = [
        f"Réussite : < {_pourcent(seuil)}" if seuil is not None else "Réussite : toutes",
        "Type de champ : "
        + (", ".join(_TYPES.get(t.upper(), t) for t in f.get("types_champ", [])) or "tous"),
        "Type d'erreur : "
        + (", ".join(_ECHECS.get(t, t) for t in f.get("types_erreur", [])) or "tous"),
        "Section : " + (", ".join(f.get("sections", [])) or "toutes"),
    ]
    if f.get("recherche"):
        morceaux.append(f"Recherche : « {f['recherche']} »")
    return " · ".join(_e(m) for m in morceaux)


def _entete(
    metriques: Mapping[str, Any],
    dataset: Optional[str],
    recette: Mapping[str, Any],
    edite_le: datetime,
) -> str:
    execution = metriques["execution"]
    g = metriques["global"]
    documents = metriques["echantillon"]["documents"]
    moteur = execution.get("ocr_model_id") or execution.get("ocr_provider") or "inconnu"
    remplies = int(g["justes"]) + int(g["fausses"]) + int(g["manquees"])
    marge = g.get("fourchette_valeurs_trouvees")
    marge_texte = (
        f"Marge d'incertitude : {_pourcent(marge[0])} à {_pourcent(marge[1])}" if marge else ""
    )
    recette_nom = f" « {_e(recette['name'])} »" if recette.get("name") else ""
    morceaux = [
        "<h1>NOTA · Rapport de qualité d'extraction</h1>",
        f"<p class='sous-titre'>Dataset {_e(dataset or '—')} · recette #{_e(recette.get('id'))}"
        f"{recette_nom} · test #{_e(execution.get('id'))} du {_date(execution.get('finished_at'))}"
        f"<br/>Moteur : {_e(moteur)} · {_nombre(documents)} document(s) · "
        f"édité le {edite_le.strftime('%d/%m/%Y')}</p>",
        f"<p class='taux'>{_pourcent(g.get('taux_valeurs_trouvees'))}</p>",
        f"<p><b>Valeurs bien lues</b> · {_nombre(g['justes'])} lues correctement sur "
        f"{_nombre(remplies)}<br/><span class='legende'>{marge_texte}</span></p>",
        "<p>Parmi les valeurs des champs vérifiés : "
        f"<b>{_nombre(g['justes'])}</b> correctes · <b>{_nombre(g['fausses'])}</b> lues, mais "
        f"fausses · <b>{_nombre(g['manquees'])}</b> présentes, non lues · "
        f"<b>{_nombre(g['inventees'])}</b> lues alors que vides · "
        f"<b>{_nombre(g['vides'])}</b> vides (hors taux)</p>",
    ]
    verdict = metriques.get("verdict") or {}
    if verdict.get("reussi") is not None:
        classe, texte = ("verdict-ok", "réussi") if verdict["reussi"] else ("verdict-ko", "échoué")
        seuil = verdict.get("score_minimal")
        exigence = f" (score minimal {_pourcent(seuil)})" if seuil is not None else ""
        morceaux.append(
            f"<p>Résultat du test : <span class='{classe}'>{texte}</span>{exigence}</p>"
        )
    for message in metriques.get("avertissements") or []:
        morceaux.append(f"<p class='alerte'>{_e(message[:1].upper() + message[1:])}</p>")
    return "\n".join(morceaux)


def _tableau(metriques: Mapping[str, Any]) -> str:
    selection = metriques.get("selection") or {}
    champs: Sequence[Mapping[str, Any]] = metriques.get("par_champ") or []
    morceaux = [
        "<h2>Filtres appliqués à ce rapport</h2>",
        f"<p>{_filtres(selection)}</p>",
        f"<p><b>{_nombre(selection.get('champs', len(champs)))} champ(s)</b> sur "
        f"{_nombre(selection.get('champs_verifies', 0))} vérifiés</p>",
        "<h2>Champs en erreur</h2>",
    ]
    if not champs:
        morceaux.append("<p class='legende'>Aucun champ ne correspond aux filtres.</p>")
        return "\n".join(morceaux)
    morceaux.append(
        "<p class='legende'>Réussite = part des documents dans lesquels le champ est lu "
        "correctement.</p>"
        "<table><tr><th>Champ</th><th>Type</th><th class='num'>Réussite</th>"
        "<th>Échec principal</th></tr>"
    )
    for c in champs:
        echec = c.get("echec_principal")
        echec_texte = (
            f"{_ECHECS.get(echec, echec)} · {_nombre(c['documents_en_erreur'])} doc(s) en erreur"
            if echec
            else "—"
        )
        morceaux.append(
            f"<tr><td>{_e(c['champ'])}<br/><span class='section'>{_e(c.get('section') or '')}"
            f" · page {_e(c.get('page') or '—')}</span></td>"
            f"<td>{_e(_TYPES.get(str(c.get('type') or '').upper(), c.get('type') or '—'))}</td>"
            f"<td class='num'>{_pourcent(c.get('reussite'))}</td>"
            f"<td>{_e(echec_texte)}</td></tr>"
        )
    morceaux.append("</table>")
    return "\n".join(morceaux)


def _valeur(ecart: Mapping[str, Any], cle: str) -> str:
    if ecart.get("sensitive"):
        return "<i>valeur masquée</i>"
    valeur = ecart.get(cle)
    if valeur is None or not str(valeur).strip():
        return "<i>vide</i>"
    return f"<span class='valeur'>{_e(valeur)}</span>"


def _extraits(
    metriques: Mapping[str, Any], extraits: Mapping[str, Sequence[Mapping[str, Any]]]
) -> str:
    champs = [c for c in metriques.get("par_champ") or [] if extraits.get(c["champ"])]
    if not champs:
        return ""
    morceaux = [
        "<h2>Extraits de documents en erreur</h2>",
        f"<p class='legende'>Au plus {EXTRAITS_PAR_CHAMP} documents par champ, pour les "
        f"{CHAMPS_AVEC_EXTRAITS} champs les moins bien lus. Champs sensibles : seul le "
        "résultat est indiqué, jamais la valeur.</p>",
    ]
    for champ in champs:
        ecarts = extraits[champ["champ"]]
        en_erreur = int(champ.get("documents_en_erreur") or 0)
        reste = en_erreur - len(ecarts)
        suite = f" (et {_nombre(reste)} autre(s))" if reste > 0 else ""
        morceaux.append(f"<p><b>{_e(champ['champ'])}</b>{suite}</p>")
        for ecart in ecarts:
            morceaux.append(
                f"<div class='extrait'>Document {_e(ecart.get('document_id'))} · page "
                f"{_e(ecart.get('page'))} · {_e(_ECHECS.get(str(ecart.get('type_erreur')), ''))}"
                f"<br/>Attendu : {_valeur(ecart, 'expected_value')} · "
                f"Lu : {_valeur(ecart, 'observed_value')}</div>"
            )
    return "\n".join(morceaux)


def _pied(metriques: Mapping[str, Any]) -> str:
    execution = metriques["execution"]
    empreinte = str(execution.get("schema_hash") or "—")[:8]
    return (
        f"Généré par NOTA · comparateur v{_e(execution.get('comparateur_version') or '—')} · "
        f"schéma {_e(empreinte)}"
    )


def rendre_pdf(
    metriques: Mapping[str, Any],
    *,
    recette: Mapping[str, Any],
    dataset: Optional[str],
    extraits: Mapping[str, Sequence[Mapping[str, Any]]],
    edite_le: datetime,
) -> bytes:
    """Le PDF du rapport.

    Args:
        metriques: la reponse de /metriques, filtres compris.
        recette: au moins ``id``, et ``name`` si connu.
        dataset: le nom du dataset.
        extraits: par champ (par_champ[].champ), des ecarts tels que /ecarts
            les rend.
        edite_le: la date imprimee.
    """
    corps = "\n".join(
        (
            _entete(metriques, dataset, recette, edite_le),
            _tableau(metriques),
            _extraits(metriques, extraits),
        )
    )
    story = pymupdf.Story(html=f"<body>{corps}</body>", user_css=_CSS)
    tampon = io.BytesIO()
    writer = pymupdf.DocumentWriter(tampon)
    encore = True
    while encore:
        device = writer.begin_page(_PAGE)
        encore, _ = story.place(_ZONE)
        story.draw(device)
        writer.end_page()
    writer.close()
    return _numeroter(tampon.getvalue(), _pied(metriques))


def _numeroter(pdf: bytes, pied: str) -> bytes:
    """Pied de chaque page : la provenance a gauche, « Page n / N » a droite."""
    document = pymupdf.open("pdf", pdf)
    total = document.page_count
    style = "font-family:sans-serif;font-size:7.5pt;color:#57606a"
    for numero in range(1, total + 1):
        page = document[numero - 1]
        page.insert_htmlbox(_PIED, f"<div style='{style}'>{pied}</div>")
        page.insert_htmlbox(
            _PIED, f"<div style='{style};text-align:right'>Page {numero} / {total}</div>"
        )
    # Chaque pied de page embarque sa police : sans sous-ensemble, 28 pages
    # pesaient 1,8 Mo.
    document.subset_fonts()
    sortie: bytes = document.tobytes(garbage=4, deflate=True)
    document.close()
    return sortie


def extraits_a_montrer(par_champ: Sequence[Mapping[str, Any]]) -> List[str]:
    """Les champs dont le PDF montre des extraits : les pires, en erreur."""
    return [c["champ"] for c in par_champ if c.get("documents_en_erreur")][:CHAMPS_AVEC_EXTRAITS]


def dict_ecarts(ecarts: Sequence[Any]) -> List[Dict[str, Any]]:
    """EcartOut -> dict, pour rendre_pdf."""
    return [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in ecarts]
