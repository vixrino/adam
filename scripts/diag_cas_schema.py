"""Rejoue la pre-alimentation d'un meme document avec plusieurs variantes de schema.

Un document passe en ERROR selon le schema de son dataset (« pages du formulaire
introuvables », « aucune page du formulaire reconnue »), sans que les logs disent
quelle propriete du schema est en cause. Ce script prend un document deja rendu en
images et le soumet au vrai connecteur avec une serie de schemas construits en
memoire : un seul champ, champ obligatoire ou non, pages decrites ou non, champ
sans libelle, repetable, sensible, autre type, deux champs, champ en double...
Pour chaque cas il rend le verdict de la pre-alimentation (OK ou ERROR et son
motif) et la page que le moteur a reconnue sur chaque image.

Aucune ecriture en base : ni schema, ni champ, ni statut. Les variantes viennent
d'un schema source (par defaut le premier schema CERFA), lu comme le lit le
worker. --schemas ajoute des schemas reels, rejoues tels qu'en base : c'est la
facon de tester un schema cree a l'ecran qui casse.

Cout : l'OCR de chaque page n'est fait qu'une fois et mis en cache. Chaque cas
coute ensuite un appel d'identification par page, plus un appel d'extraction par
page reconnue qui porte des champs.

    uv run python scripts/diag_cas_schema.py --document-id 42
    uv run python scripts/diag_cas_schema.py --document-id 42 --schemas 12,13
    uv run python scripts/diag_cas_schema.py --document-id 42 --champ deposant.nom
    uv run python scripts/diag_cas_schema.py --document-id 42 --cas 1champ_sans_page,1champ_sans_page_obligatoire
    uv run python scripts/diag_cas_schema.py --lister-cas

Le script tourne tel quel dans nota-back et dans adam (paquets nota_* ou adam_*).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

try:  # les deux miroirs du projet ne portent pas le meme nom de paquet
    from nota_api.core.config import settings
    from nota_core.core.config import get_core_settings
    from nota_core.db.session import get_async_session, init_engine
    from nota_core.models import Dataset, DocSchema, Document
    from nota_worker.connectors import connector_from_settings
    from nota_worker.connectors.base import DocumentNonConforme, OcrConnectorError
    from nota_worker.connectors.modele import ModeleDocument
    from nota_worker.prepopulation.merger import count_detected, merge
    from nota_worker.prepopulation.poller import default_pages_dir
except ImportError:  # pragma: no cover
    from adam_api.core.config import settings
    from adam_core.core.config import get_core_settings
    from adam_core.db.session import get_async_session, init_engine
    from adam_core.models import Dataset, DocSchema, Document
    from adam_worker.connectors import connector_from_settings
    from adam_worker.connectors.base import DocumentNonConforme, OcrConnectorError
    from adam_worker.connectors.modele import ModeleDocument
    from adam_worker.prepopulation.merger import count_detected, merge
    from adam_worker.prepopulation.poller import default_pages_dir

CERFA_DOCUMENT_TYPE = "CERFA_SURENDETTEMENT_V2"
SEP = "=" * 78


def construire_modele(schema: Dict[str, Any]) -> Any:
    """ModeleDocument.from_schema (nota) ou depuis_schema (adam)."""
    fabrique = getattr(ModeleDocument, "from_schema", None) or getattr(
        ModeleDocument, "depuis_schema"
    )
    return fabrique(schema)


# -- Lecture des schemas, a l'identique du worker -------------------------------


def schema_en_dict(schema: Any) -> Dict[str, Any]:
    """Meme forme que PrepopulationWorker._load_schema : toutes les colonnes."""
    return {
        "id": schema.id,
        "name": schema.name,
        "pages": [
            {"page_number": p.page_number, "description": p.description}
            for p in sorted(schema.pages, key=lambda p: p.page_number)
        ],
        "field_specs": [
            {c.name: getattr(fs, c.name) for c in fs.__table__.columns}
            for fs in sorted(schema.field_specs, key=lambda x: (x.page, x.display_order))
        ],
    }


async def charger_schema(schema_id: Optional[int]) -> Dict[str, Any]:
    async with get_async_session() as db:
        requete = select(DocSchema).options(
            selectinload(DocSchema.field_specs), selectinload(DocSchema.pages)
        )
        if schema_id is not None:
            requete = requete.where(DocSchema.id == schema_id)
        else:
            requete = requete.where(DocSchema.document_type == CERFA_DOCUMENT_TYPE).order_by(
                DocSchema.id
            )
        schema = (await db.execute(requete)).scalars().first()
        if schema is None:
            raise SystemExit(
                f"schema {schema_id} introuvable"
                if schema_id
                else "aucun schema CERFA : passer --source"
            )
        return schema_en_dict(schema)


async def images_du_document(document_id: int) -> Tuple[List[Path], Optional[int]]:
    """Images de page du document, et le schema de son dataset."""
    async with get_async_session() as db:
        row = (
            await db.execute(
                select(Document.file_id, Dataset.schema_id)
                .join(Dataset, Document.dataset_id == Dataset.id)
                .where(Document.id == document_id)
            )
        ).one_or_none()
    if row is None:
        raise SystemExit(f"document {document_id} introuvable")
    dossier = Path(settings.pvc_mount_path) / default_pages_dir(int(row.file_id))
    images = sorted(dossier.glob("*.png")) if dossier.is_dir() else []
    if not images:
        raise SystemExit(
            f"aucune image de page dans {dossier} : le document doit avoir ete rendu "
            "(statut INGESTED ou au-dela)"
        )
    return images, row.schema_id


# -- Cas de test ----------------------------------------------------------------


@dataclass
class Cas:
    nom: str
    but: str
    schema: Dict[str, Any]


def _schema(nom: str, pages: List[Dict[str, Any]], specs: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"name": nom, "pages": pages, "field_specs": specs}


def _spec(spec: Dict[str, Any], **changes: Any) -> Dict[str, Any]:
    copie = dict(spec)
    copie.update(changes)
    return copie


def construire_cas(source: Dict[str, Any], champ: Optional[str]) -> List[Cas]:
    specs: List[Dict[str, Any]] = source["field_specs"]
    pages: List[Dict[str, Any]] = [p for p in source["pages"] if p.get("description")]
    if not specs:
        raise SystemExit(f"le schema source {source['id']} n'a aucun champ")
    simples = [s for s in specs if not s.get("group_id")]
    if champ:
        choisis = [s for s in specs if s["field_key"] == champ]
        if not choisis:
            raise SystemExit(f"champ {champ} absent du schema source {source['id']}")
        base = choisis[0]
    else:
        base = (simples or specs)[0]
    page = int(base["page"])
    nom = source["name"]
    sa_page = [p for p in pages if int(p["page_number"]) == page]
    un = _spec(base, required=False)
    oblig = _spec(base, required=True)

    cas = [
        Cas("reference", "schema source complet, tel qu'en base", source),
        Cas(
            "1champ_pages_toutes", "un champ, toutes les pages decrites", _schema(nom, pages, [un])
        ),
        Cas(
            "1champ_pages_toutes_obligatoire",
            "idem, champ obligatoire",
            _schema(nom, pages, [oblig]),
        ),
        Cas(
            "1champ_page_seule", "un champ, seule sa page est decrite", _schema(nom, sa_page, [un])
        ),
        Cas(
            "1champ_page_seule_obligatoire",
            "idem, champ obligatoire",
            _schema(nom, sa_page, [oblig]),
        ),
        Cas(
            "1champ_sans_page",
            "un champ, aucune page decrite (schema cree a l'ecran)",
            _schema(nom, [], [un]),
        ),
        Cas("1champ_sans_page_obligatoire", "idem, champ obligatoire", _schema(nom, [], [oblig])),
        Cas(
            "1champ_page_description_vide",
            "un champ, sa page existe avec une description vide",
            _schema(nom, [{"page_number": page, "description": ""}], [un]),
        ),
        Cas(
            "1champ_autre_nom_sans_page",
            "un champ, aucune page decrite, nom de schema generique",
            _schema("Nouveau schema", [], [un]),
        ),
        Cas(
            "1champ_sans_libelle",
            "un champ sans description ni libelle, pages decrites",
            _schema(nom, pages, [_spec(un, description=None, display_label=None)]),
        ),
        Cas(
            "1champ_sensible",
            "un champ sensible, pages decrites",
            _schema(nom, pages, [_spec(un, sensitive=True)]),
        ),
        Cas(
            "1champ_double",
            "le meme champ declare deux fois",
            _schema(nom, pages, [un, _spec(un, id=None)]),
        ),
    ]
    for value_type in ("BOOLEAN", "NUMBER", "DATE"):
        if str(base.get("value_type") or "TEXT").upper() != value_type:
            cas.append(
                Cas(
                    f"1champ_type_{value_type.lower()}",
                    f"un champ de type {value_type}, pages decrites",
                    _schema(nom, pages, [_spec(un, value_type=value_type)]),
                )
            )
    derniere = max(specs, key=lambda s: int(s["page"]))
    if int(derniere["page"]) != page:
        cas.append(
            Cas(
                "1champ_derniere_page_sans_page",
                f"un champ de la page {derniere['page']}, aucune page decrite",
                _schema(nom, [], [_spec(derniere, required=False)]),
            )
        )
    repetables = [s for s in specs if s.get("group_id")]
    if repetables:
        cas.append(
            Cas(
                "1champ_repetable",
                f"une ligne de tableau ({repetables[0]['group_id']}), pages decrites",
                _schema(nom, pages, [_spec(repetables[0], required=False)]),
            )
        )
    autre_page = next((s for s in simples if int(s["page"]) != page), None)
    if autre_page:
        cas.append(
            Cas(
                "2champs_2pages",
                f"deux champs, pages {page} et {autre_page['page']}, pages decrites",
                _schema(nom, pages, [un, _spec(autre_page, required=False)]),
            )
        )
        cas.append(
            Cas(
                "2champs_2pages_un_obligatoire",
                "idem, le second champ obligatoire",
                _schema(nom, pages, [un, _spec(autre_page, required=True)]),
            )
        )
    return cas


# -- Execution d'un cas, a l'identique de la pre-alimentation -------------------


@dataclass
class Resultat:
    cas: Cas
    verdict: str
    motif: str = ""
    detectes: int = 0
    identifications: Dict[int, Optional[int]] = field(default_factory=dict)
    anomalies: List[Dict[str, Any]] = field(default_factory=list)


def instrumenter(connecteur: Any) -> Callable[[], Dict[int, Optional[int]]]:
    """Met l'OCR en cache et releve la page reconnue sur chaque image.

    L'OCR ne depend pas du schema : le refaire a chaque cas paierait N appels
    pour rien. L'identification, elle, depend du schema et reste appelee.
    """
    cache: Dict[str, Any] = {}
    lire = connecteur._read_page  # pylint: disable=protected-access
    identifier = connecteur._identify  # pylint: disable=protected-access
    vues: Dict[int, Optional[int]] = {}

    async def lire_en_cache(image: Path, rang: int) -> Any:
        cle = str(image)
        if cle not in cache:
            cache[cle] = await lire(image, rang)
        return cache[cle]

    async def identifier_trace(markdown: str, rang: int, consigne: str, descriptions: Any) -> Any:
        page = await identifier(markdown, rang, consigne, descriptions)
        vues[rang] = page
        return page

    connecteur._read_page = lire_en_cache  # pylint: disable=protected-access
    connecteur._identify = identifier_trace  # pylint: disable=protected-access

    def relever() -> Dict[int, Optional[int]]:
        copie = dict(sorted(vues.items()))
        vues.clear()
        return copie

    return relever


async def jouer(
    connecteur: Any, images: List[Path], cas: Cas, relever: Callable[[], Any]
) -> Resultat:
    specs = cas.schema["field_specs"]
    try:
        modele = construire_modele(cas.schema)
        ocr = await connecteur.extract(images, modele)
    except DocumentNonConforme as exc:
        return Resultat(
            cas, "ERROR", f"document non conforme : {exc}", 0, relever(), list(exc.anomalies)
        )
    except OcrConnectorError as exc:
        return Resultat(cas, "ERROR", f"connecteur OCR en echec : {exc}", 0, relever())
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return Resultat(
            cas, "ERROR", f"echec inattendu : {type(exc).__name__} : {exc}", 0, relever()
        )
    vues = relever()
    anomalies = list((ocr.metadata.get("anomalies_pages") if ocr is not None else None) or [])
    manquantes = [a for a in anomalies if a.get("type") == "pages_manquantes"]
    if manquantes:
        return Resultat(
            cas,
            "ERROR",
            f"pages du formulaire introuvables : {manquantes[0].get('pages')}",
            0,
            vues,
            anomalies,
        )
    payloads = merge(specs, ocr)
    if not payloads:
        return Resultat(cas, "ERROR", "schema sans field_spec", 0, vues, anomalies)
    motif = "aucune valeur lue : champs crees vides" if ocr is None else ""
    return Resultat(cas, "OK", motif, count_detected(payloads), vues, anomalies)


def afficher(r: Resultat) -> None:
    s = r.cas.schema
    decrites = sorted(int(p["page_number"]) for p in s["pages"] if p.get("description"))
    pages_champs = sorted({int(f["page"]) for f in s["field_specs"]})
    oblig = sum(1 for f in s["field_specs"] if f.get("required"))
    print(f"\n[{r.verdict:5}] {r.cas.nom}  -  {r.cas.but}")
    print(
        f"        schema : {len(s['field_specs'])} champ(s) sur page(s) {pages_champs}, "
        f"{oblig} obligatoire(s), pages decrites {decrites or 'aucune'}"
    )
    if r.motif:
        print(f"        motif  : {r.motif}")
    if r.verdict == "OK":
        print(f"        valeurs lues : {r.detectes}")
    reconnues = ", ".join(
        f"{rang}->{page if page is not None else '-'}" for rang, page in r.identifications.items()
    )
    print(f"        image->page reconnue : {reconnues or 'aucune identification'}")
    for a in r.anomalies:
        if a.get("type") != "pages_manquantes":
            print(f"        anomalie : {a}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--document-id", type=int, help="document de test, deja rendu en images")
    parser.add_argument(
        "--source", type=int, help="schema d'ou tirer les variantes (defaut : CERFA)"
    )
    parser.add_argument(
        "--champ", help="field_key du champ des cas a un champ (defaut : le premier)"
    )
    parser.add_argument(
        "--schemas", default="", help="ids de schemas reels a rejouer tels quels, ex. 12,13"
    )
    parser.add_argument(
        "--cas", default="", help="ne jouer que ces cas, ex. 1champ_sans_page,reference"
    )
    parser.add_argument(
        "--lister-cas", action="store_true", help="afficher les cas sans rien appeler"
    )
    parser.add_argument(
        "--accepter-mock", action="store_true", help="tourner meme avec le connecteur simule"
    )
    args = parser.parse_args()

    init_engine(get_core_settings().async_database_url, echo=False)
    source = await charger_schema(args.source)
    tous = construire_cas(source, args.champ)
    for schema_id in [int(x) for x in args.schemas.split(",") if x.strip()]:
        reel = await charger_schema(schema_id)
        tous.insert(
            0,
            Cas(f"reel_{schema_id}", f"schema {schema_id} « {reel['name']} » tel qu'en base", reel),
        )
    if args.cas:
        voulus = {c.strip() for c in args.cas.split(",")}
        inconnus = voulus - {c.nom for c in tous}
        if inconnus:
            raise SystemExit(f"cas inconnus : {sorted(inconnus)}")
        tous = [c for c in tous if c.nom in voulus]

    print(SEP)
    print(f"schema source : {source['id']} « {source['name']} »")
    if args.lister_cas or args.document_id is None:
        for c in tous:
            print(f"  {c.nom:38} {c.but}")
        if args.document_id is None and not args.lister_cas:
            print("\n--document-id manquant : rien n'a ete appele.")
        return

    images, schema_du_dataset = await images_du_document(args.document_id)
    connecteur = connector_from_settings(settings)
    nom_connecteur = getattr(connecteur, "name", type(connecteur).__name__)
    print(
        f"document      : {args.document_id}, {len(images)} image(s), dataset sur le schema {schema_du_dataset}"
    )
    print(f"connecteur    : {nom_connecteur}")
    if getattr(settings, "ocr_mock_enabled", False) and not args.accepter_mock:
        raise SystemExit(
            "connecteur simule actif (OCR_MOCK_ENABLED) : il ne reconnait aucune page, "
            "le diagnostic serait faux. Desactiver le mock, ou --accepter-mock."
        )
    if not hasattr(connecteur, "_read_page") or not hasattr(connecteur, "_identify"):
        raise SystemExit(
            f"connecteur {nom_connecteur} sans lecture page par page : diagnostic impossible"
        )
    appels = len(images) + len(tous) * (len(images) + 2)
    print(f"cas           : {len(tous)}, environ {appels} appels au moteur au plus")
    print(SEP)

    relever = instrumenter(connecteur)
    resultats: List[Resultat] = []
    for c in tous:
        r = await jouer(connecteur, images, c, relever)
        afficher(r)
        resultats.append(r)

    print("\n" + SEP)
    print("SYNTHESE")
    print(SEP)
    for r in resultats:
        print(f"  {r.verdict:5}  {r.cas.nom:38} {r.motif}")
    erreurs = [r for r in resultats if r.verdict != "OK"]
    if not erreurs:
        print("\nAucun cas en ERROR : le probleme ne vient pas d'une de ces proprietes du schema.")
        print("Rejouer le schema qui casse avec --schemas <id> pour le comparer a ces cas.")


if __name__ == "__main__":
    asyncio.run(main())
