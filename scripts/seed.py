"""
 scripts/seed.py
 ----------
 Seed unifie de la base ADAM.
 Modes :
     - Par defaut : CERFA surendettement, schema seul. Champs et groupes
       repetables derives de adam_core.schemas.cerfa_v2, plus le lot qui va
       avec. Aucun document : on en depose un ensuite, et ce sont les workers
       qui l'OCRisent.
     - --pdf <fichier> : idem, plus un vrai CERFA copie sur le PVC en statut
       RECEIVED. PageImageWorker en rend les pages, PrepopulationWorker appelle
       l'OCR et cree les champs. Les valeurs annotees sont celles du document.
     - --fake-ocr : idem, plus un dossier fictif ecrit directement en base,
       sans PDF ni appel OCR. Demo hors ligne, sans rien a afficher en regard.
     - --form-demo : ancien formulaire synthetique hardcode (demandeur, bien,
       creance), conserve pour les tests qui s'y appuient.
     - --json : schema et champs derives d'un fichier format formulaire v0.3.
Usage :
    python scripts/seed.py --reset
    python scripts/seed.py --reset --pdf ~/cerfa_rempli.pdf
    python scripts/seed.py --reset --fake-ocr
    python scripts/seed.py --form-demo --reset
    python scripts/seed.py --json form_demo_v0.3.json --reset
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from adam_core.core.config import CoreSettings
from adam_core.utils.hashing import sha256_bytes
from adam_core.db.session import create_tables, get_engine, init_engine
from adam_core.enums.ocr import OcrProvider, StorageMode
from adam_core.enums.roles import PlatformRole, ProjectRole
from adam_core.enums.status import (
    DatasetStatus,
    DocumentFieldStatus,
    DocumentStatus,
    FieldValueType,
    ProjectStatus,
    UserStatus,
)
from adam_core.models import (
    Dataset,
    DocSchema,
    Document,
    DocumentField,
    FieldSpec,
    File,
    OcrResult,
    Organisation,
    Project,
    User,
    UserProject,
)
# Le chemin du PVC est un reglage d'API, pas de coeur : c'est la que vivent
# les workers qui liront le PDF depose ici.
from adam_api.core.config import settings as api_settings
from adam_core.schemas.cerfa_v2 import CERFA_V2_PAGE_FIELDS

# Le seed fabrique les DocumentField que le worker de pre-alimentation creerait
# a partir d'un vrai PDF : reprendre sa constante de resolveur garde les deux
# chemins indiscernables en base.
from adam_worker.prepopulation.merger import OCR_RESOLVER

# Le depliage des champs du CERFA en FieldSpec — sections repetables comprises —
# vit dans seed_schema_cerfa.py, qui ne cree que le schema. Le reimporter ici
# evite d'en tenir deux copies qui divergeraient des le prochain CERFA.
from seed_schema_cerfa import REPEATABLE_SECTIONS, SECTION_LABELS, build_specs

settings = CoreSettings()
SEPARATOR = "-" * 55
# Reset
async def reset_db(session: AsyncSession) -> None:
    print(" Reset de la base...")
    tables = [
        "document_field", "ocr_result", "document", "file",
        "dataset", "field_spec", "doc_schema",
        "user_project", "project", "user", "organisation",
    ]
    for table in tables:
        await session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
    await session.commit()
    print(" Tables videes")
# Infrastructure commune
#
# Les DIRES sont les directions regionales qui instruisent les dossiers de
# surendettement : une organisation par direction, chacune avec ses agents et
# son projet. Le decoupage rend visible ce que le seed precedent, avec ses deux
# "Org Alpha" et "Org Beta" vides, ne montrait pas — un agent ne voit que les
# projets de sa direction, et c'est la premiere chose qu'une demonstration doit
# donner a voir.
#
# La premiere de la liste est la direction de reference : c'est elle que le
# reste du seed alimente en schema, dataset et documents, et c'est la qu'on
# retrouve les trois matricules attendus par check_project_scoping.py.

#: (slug, nom). Ajouter une ligne suffit a creer une direction de plus.
ORGANISATIONS = [
    ("dires-idf", "DIRES Ile-de-France"),
    ("dires-paca", "DIRES Provence-Alpes-Cote d'Azur"),
    ("dires-ara", "DIRES Auvergne-Rhone-Alpes"),
]

#: Agents, par slug d'organisation : (matricule, prenom, nom, role projet,
#: role plateforme). Les identites sont fictives ; les matricules MAT00001 a
#: MAT00003 gardent en revanche leur signification, check_project_scoping.py et
#: la valeur par defaut d'API_DEV_MATRICULE s'appuyant dessus.
#:
#: Les prenoms et noms evitent les accents : le repr des lignes est imprime sur
#: la sortie standard, qui n'est pas toujours en UTF-8 sous Windows.
AGENTS = {
    "dires-idf": [
        ("MAT00001", "Philippe", "Bernard", ProjectRole.BUSINESS_ADMIN, None),
        ("MAT00002", "Nadia", "Fontaine", ProjectRole.OPERATOR, None),
        ("MAT00003", "Sylvie", "Marchand", None, PlatformRole.NOTA_ADMIN),
        ("MAT00005", "Karim", "Belkacem", ProjectRole.OPERATOR, None),
    ],
    "dires-paca": [
        ("MAT00010", "Martine", "Vasseur", ProjectRole.BUSINESS_ADMIN, None),
        ("MAT00011", "Thomas", "Roux", ProjectRole.OPERATOR, None),
        ("MAT00012", "Awa", "Diallo", ProjectRole.OPERATOR, None),
    ],
    "dires-ara": [
        ("MAT00020", "Michel", "Perrot", ProjectRole.BUSINESS_ADMIN, None),
        ("MAT00021", "Claire", "Lemoine", ProjectRole.OPERATOR, None),
    ],
}

#: Projet type, decline dans chaque direction. Le libelle porte la direction :
#: deux projets homonymes dans deux organisations sont indiscernables dans une
#: liste, alors que le filtrage par organisation les separe deja en base.
PROJECT_NAME = "Traitement des declarations de surendettement"
PROJECT_DESCRIPTION = "Annotation des CERFA 13594*02 recus par la direction"

#: Nom des lots : le formulaire et sa version, pas une date de reception. Un lot
#: se retrouve par ce qu'il contient ; "Lot janvier 2024" obligeait a l'ouvrir
#: pour savoir de quel formulaire il s'agissait.
#:
#: Deux noms parce que les modes du seed ne portent pas le meme formulaire. Les
#: modes CERFA et JSON decrivent le meme formulaire — le premier depuis
#: cerfa_v2.py, le second depuis form_demo_v0.3.json — et partagent donc le nom
#: de lot. Le mode --form-demo, lui, decrit un formulaire synthetique —
#: demandeur, bien, creance — qu'aucun CERFA ne reprend : lui donner un numero
#: de CERFA serait faux.
CERFA_DATASET_NAME = "cerfa_13594-02_v2"
DEMO_DATASET_NAME = "form_demo_v2"


def _email(first_name: str, last_name: str) -> str:
    return f"{first_name.lower()}.{last_name.lower()}@banque-france.fr"


async def seed_infrastructure(session: AsyncSession) -> Tuple:
    print("\n [1/3] Organisations...")
    organisations = {}
    for slug, name in ORGANISATIONS:
        org = Organisation(name=name, slug=slug)
        session.add(org)
        organisations[slug] = org
    await session.flush()
    for org in organisations.values():
        print(f"        {org}")

    print(" [2/3] Users...")
    users_by_slug: Dict[str, List[Tuple[User, Optional[ProjectRole]]]] = {}
    for slug, agents in AGENTS.items():
        users_by_slug[slug] = []
        for matricule, first_name, last_name, project_role, platform_role in agents:
            user = User(
                organisation_id=organisations[slug].id,
                email=_email(first_name, last_name),
                full_name=f"{first_name} {last_name}",
                matricule=matricule,
                platform_role=platform_role.value if platform_role else None,
                status=UserStatus.ACTIVE.value,
            )
            session.add(user)
            users_by_slug[slug].append((user, project_role))
    await session.flush()
    for slug, entries in users_by_slug.items():
        for user, project_role in entries:
            role = user.platform_role or (project_role.value if project_role else "sans role")
            print(f"        [{slug}] {user.matricule} {user.full_name} - {role}")

    print(" [3/3] Projects + UserProjects...")
    projects = {}
    for slug, org in organisations.items():
        project = Project(
            organisation_id=org.id,
            name=f"{PROJECT_NAME} - {org.name}",
            description=PROJECT_DESCRIPTION,
            status=ProjectStatus.ACTIVE.value,
        )
        session.add(project)
        projects[slug] = project
    await session.flush()

    for slug, entries in users_by_slug.items():
        for user, project_role in entries:
            # L'administrateur NOTA n'est inscrit dans aucun projet : son role de
            # plateforme neutralise le filtrage, une adhesion serait redondante
            # et masquerait ce que le scoping fait reellement.
            if project_role is None:
                continue
            session.add(
                UserProject(
                    user_id=user.id,
                    project_id=projects[slug].id,
                    role=project_role.value,
                )
            )
    await session.flush()
    for project in projects.values():
        print(f"        {project}")

    reference_slug = ORGANISATIONS[0][0]
    reference_users = {user.matricule: user for user, _ in users_by_slug[reference_slug]}
    return (
        organisations[reference_slug],
        reference_users["MAT00001"],
        reference_users["MAT00002"],
        projects[reference_slug],
    )
# Mode 1 : Donnees hardcodees
HARDCODED_FIELD_SPECS = [
    ("demandeur", "Demandeur", "demandeur.nom", "Nom de naissance", FieldValueType.TEXT.value, 1),
    ("demandeur", "Demandeur", "demandeur.prenom", "Prenom", FieldValueType.TEXT.value, 1),
    ("demandeur", "Demandeur", "demandeur.date_naissance", "Date de naissance", FieldValueType.DATE.value, 1),
    ("demandeur", "Demandeur", "demandeur.civilite_m", "Monsieur", FieldValueType.BOOLEAN.value, 1),
    ("demandeur", "Demandeur", "demandeur.civilite_mme", "Madame", FieldValueType.BOOLEAN.value, 1),
    ("bien", "Bien", "bien.adresse", "Adresse du bien", FieldValueType.TEXT.value, 1),
    ("bien", "Bien", "bien.valeur", "Valeur du bien (EUR)", FieldValueType.NUMBER.value, 1),
    ("bien", "Bien", "bien.superficie", "Superficie (m2)", FieldValueType.NUMBER.value, 1),
    ("creance", "Creance", "creance.montant", "Montant creance", FieldValueType.NUMBER.value, 1),
    ("creance", "Creance", "creance.date_echeance", "Date d'echeance", FieldValueType.DATE.value, 1),
]
HARDCODED_OCR_VALUES: Dict = {
    "demandeur.nom":                 ("NOM01",                      0.98, [182,282,298,182,298,168,82,168]),
    "demandeur.prenom":              ("P02",                        0.97, [82,142,288,142,288,168,82,168]),
    "demandeur.date_naissance":      ("1985-01-01",                  0.95, [82,182,218,182,218,208,82,208]),
    "demandeur.civilite_m":          ("true",                        1.00, [82,222,118,222,118,238,82,238]),
    "demandeur.civilite_mme":        ("false",                       1.00, [132,222,178,222,178,238,132,238]),
    "bien.adresse":                 ("1 rue Demo 00000 Villedemo", 0.91, [82,102,498,102,498,128,82,128]),
    "bien.valeur":                  ("450000",                      0.88, [82,142,298,142,298,168,82,168]),
    "bien.superficie":              ("85",                          0.93, [322,142,448,142,448,168,322,168]),
    "creance.montant":              ("320000",                      0.90, [82,222,298,222,298,248,82,248]),
    "creance.date_echeance":        ("2040-01-15",                  0.94, [322,222,498,222,498,248,322,248]),
}
HARDCODED_RAW_JSON = {
    "smartdoc_version": "0.3",
    "document_id": "form_demo_001",
    "coordinate_unit": "pixel",
    "page_count": 2,
    "metadata": {"ocr": {"provider": "PULSAR", "processed_at": "2024-01-15T10:00:00Z"}},
    "pages": [],
}
async def seed_hardcoded(session: AsyncSession, project: Project) -> None:
    print("\n --- Mode : donnees hardcodees (Formulaire Demo v2) ---")
    print(" [4/8] DocSchema...")
    schema = DocSchema(
       project_id=project.id,
       version=2,
       name="Schema Formulaire Demo v2",
       document_type="FORM_DEMO_02",
    )
    session.add(schema)
    await session.flush()
    print(f"        {schema}")
    print(" [5/8] FieldSpecs...")
    field_specs = []
    for i, (sec_id, sec_label, key, label, ftype, page) in enumerate(HARDCODED_FIELD_SPECS):
       fs = FieldSpec(
           schema_id=schema.id, page=page,
           section_id=sec_id, section_label=sec_label,
           field_key=key, display_label=label,
           value_type=ftype, required=False,
           display_order=i,
       )
       field_specs.append(fs)
    session.add_all(field_specs)
    await session.flush()
    print(f"    --- {len(field_specs)} FieldSpecs crees")
    await _seed_dataset_to_fields(
       session, project, schema, field_specs,
       file_path="/pvc/org-beta/forms/2024_01/2024_01_15_1200/form_demo_001.pdf",
       file_name="form_demo_001.pdf",
       raw_json=HARDCODED_RAW_JSON,
       ocr_values=HARDCODED_OCR_VALUES,
       document_id_str="form_demo_001",
       step_offset=6,
    )
# Mode 2 : Depuis JSON formulaire
async def seed_from_form_json(
    session: AsyncSession, project: Project, json_path: Path
) -> None:
    from adam_core.schemas.interface_contract import SmartdocDocument
    print(f"\n --- Mode : FORM JSON ({json_path.name}) ---")
    with open(json_path, encoding="utf-8") as f:
       json_raw = json.load(f)
    form_doc = SmartdocDocument.model_validate(json_raw)
    print(f" JSON valide : {form_doc.page_count} pages, document_id={form_doc.document_id}")
    print(" [4/8] DocSchema...")
    schema = DocSchema(
       project_id=project.id,
       version=1,
       name="Formulaire Demo",
       document_type="FORM_DEMO_01",
    )
    session.add(schema)
    await session.flush()
    print(f"        {schema}")
    print(" [5/8] FieldSpecs (dérivés du JSON)...")
    specs_data = form_doc.extract_field_specs()
    field_spec_index: Dict = {}
    field_specs = []
    for spec in specs_data:
       fs = FieldSpec(
           schema_id=schema.id,
           page=spec["page"],
           section_id=spec["section_id"],
           section_label=spec["section_label"],
           field_key=spec["field_key"],
           display_label=spec["display_label"],
           value_type=spec["value_type"],
           required=spec["required"],
           display_order=spec["display_order"],
           polygon=spec["polygon"],
       )
       field_specs.append(fs)
       session.add(fs)
       await session.flush()
       field_spec_index[(spec["section_id"], spec["field_key"])] = fs
    print(f"        {len(field_specs)} FieldSpecs créés depuis {form_doc.page_count} pages")
    print(" [6/8] Dataset...")
    dataset = Dataset(
       project_id=project.id, schema_id=schema.id,
       name=CERFA_DATASET_NAME,
       ocr_provider=OcrProvider.PULSAR.value,
       status=DatasetStatus.ACTIVE.value,
       required_operators=2,
       configs={"confidence_threshold": 0.8},
    )
    session.add(dataset)
    await session.flush()
    print(f"        {dataset=}")
    print(" [7/8] File + Document...")
    json_bytes = json.dumps(json_raw, ensure_ascii=False).encode("utf-8")
    sha256 = sha256_bytes(json_bytes)
    file_ = File(
       file_path=f"/pvc/forms/demo/{form_doc.document_id}.pdf",
       storage_type="pvc", mime_type="application/pdf",
       page_count=form_doc.page_count,
       file_size_bytes=len(json_bytes),
       sha256_checksum=sha256,
    )
    session.add(file_)
    await session.flush()
    document = Document(
       dataset_id=dataset.id, file_id=file_.id,
       file_name=f"{form_doc.document_id}.pdf",
       metadata={
           "smartdoc_version": form_doc.smartdoc_version,
           "document_id": form_doc.document_id,
           "coordinate_unit": form_doc.coordinate_unit,
       },
       status=DocumentStatus.IN_PROGRESS.value,
    )
    session.add(document)
    await session.flush()
    print(f"        {file_}")
    print(f"        {document}")
    print("    [8/8] OcrResult + DocumentFields...")
    ocr_result = OcrResult(
       document_id=document.id, dataset_id=dataset.id,
       storage_mode=StorageMode.JSONB.value,
       raw_json=json_raw,
    )
    session.add(ocr_result)
    await session.flush()
    doc_fields = []
    skipped = 0
    for _, section, kv in form_doc.iter_kv_pairs():
       fs = field_spec_index.get((section.id, kv.field_key))
       if not fs:
           skipped += 1
           continue
       doc_fields.append(DocumentField(
           document_id=document.id, field_spec_id=fs.id,
           group_id=kv.group_id,
           ocr_value=kv.extracted_value, resolved_value=kv.extracted_value,
           status=DocumentFieldStatus.PENDING.value,
           ocr_confidence=kv.confidence, consensus_reached=False,
           ocr_polygon=kv.polygon,
       ))
    session.add_all(doc_fields)
    await session.flush()
    print(f"            {len(doc_fields)} DocumentFields crees")
    if skipped:
       print(f"            {skipped} KVPairs ignores (fieldSpec manquant)")
    print(f"\n Resume : {len(field_specs)} FieldSpecs, {len(doc_fields)} DocumentFields, {form_doc.page_count}")
# Mode 3 : CERFA surendettement (schema reel, champs de cerfa_v2.py)
#
# Le mode hardcode monte un formulaire synthetique — demandeur, bien, creance —
# qui ne correspond a aucun CERFA. Pour une demonstration, l'ecran d'annotation
# doit montrer les champs que l'operateur verra en production : ceux que
# cerfa_v2.py declare page par page, avec leurs sections repetables. C'est le
# role de ce mode, qui reprend la construction des FieldSpec de
# seed_schema_cerfa.py au lieu de la dupliquer, et y ajoute un dossier fictif
# complet : dataset, document, resultat OCR et valeurs annotees.

CERFA_SCHEMA_NAME = "Declaration de surendettement (CERFA 13594*02)"
CERFA_DOCUMENT_TYPE = "CERFA_SURENDETTEMENT_V2"
CERFA_SCHEMA_VERSION = 2

#: Dossier fictif. Les cles suivent la clef complete d'un FieldSpec :
#: "<section_id>.<field_key>" pour une section simple,
#: "<section_id>.<group_id>.<field_key>" pour une instance d'une section
#: repetable. Un champ absent de cette table reste vide en base : c'est le cas
#: normal du CERFA, ou la plupart des emplacements repetables ne sont pas
#: remplis, et c'est ce que l'operateur doit voir.
CERFA_DOSSIER: Dict[str, str] = {
    # Page 1
    "deposant.civilite_monsieur": "true",
    "deposant.civilite_madame": "false",
    "deposant.nom_naissance": "MOREAU",
    "deposant.nom_usage": "MOREAU",
    "deposant.prenoms": "Julien Pierre",
    "deposant.date_naissance": "1979-04-12",
    "deposant.lieu_naissance": "Meaux",
    "deposant.dept_naissance": "77",
    "deposant.pays_naissance": "France",
    "co_deposant.civilite_monsieur": "false",
    "co_deposant.civilite_madame": "true",
    "co_deposant.nom_naissance": "LAMBERT",
    "co_deposant.nom_usage": "MOREAU",
    "co_deposant.prenoms": "Sophie Anne",
    "co_deposant.date_naissance": "1982-09-30",
    "co_deposant.lieu_naissance": "Melun",
    "co_deposant.dept_naissance": "77",
    "co_deposant.pays_naissance": "France",
    "coordonnees_personnelles.batiment": "B",
    "coordonnees_personnelles.escalier": "2",
    "coordonnees_personnelles.etage": "3",
    "coordonnees_personnelles.appartement": "312",
    "coordonnees_personnelles.numero": "14",
    "coordonnees_personnelles.voie": "rue des Lilas",
    "coordonnees_personnelles.code_postal": "77100",
    "coordonnees_personnelles.localite": "Meaux",
    "coordonnees_personnelles.pays": "France",
    "coordonnees_personnelles.telephone_deposant": "0612345678",
    "coordonnees_personnelles.telephone_co_deposant": "0698765432",
    "coordonnees_personnelles.courriel": "j.moreau@example.fr",
    "coordonnees_personnelles.courriel_co_deposant": "s.moreau@example.fr",
    "assist_travailleur_social.nom": "DUPONT",
    "assist_travailleur_social.prenom": "Claire",
    "assist_travailleur_social.adresse": "CCAS, 3 place de la Mairie, 77100 Meaux",
    "assist_travailleur_social.telephone": "0164000000",
    "assist_travailleur_social.courriel": "ccas.meaux@example.fr",
    "certification.fait_a": "Meaux",
    "certification.date": "2024-03-05",
    "certification.signature_deposant": "true",
    "certification.signature_codeposant": "true",
    # Page 2
    "dossier_precedent.non": "true",
    "dossier_precedent.oui": "false",
    "situation_familiale.marie": "true",
    "situation_familiale.marie_date": "2006-06-17",
    "situation_familiale.pacse": "false",
    "situation_familiale.concubin": "false",
    "situation_familiale.celibataire": "false",
    "situation_familiale.separe": "false",
    "situation_familiale.divorce": "false",
    "situation_familiale.veuf": "false",
    "personnes_a_charge.personne_1.lien_parente": "Fille",
    "personnes_a_charge.personne_1.date_naissance": "2011-02-08",
    "personnes_a_charge.personne_1.situation_garde": "Au domicile",
    "personnes_a_charge.personne_1.ressources_oui": "false",
    "personnes_a_charge.personne_1.ressources_non": "true",
    "personnes_a_charge.personne_2.lien_parente": "Fils",
    "personnes_a_charge.personne_2.date_naissance": "2014-11-22",
    "personnes_a_charge.personne_2.situation_garde": "Garde alternee",
    "personnes_a_charge.personne_2.ressources_oui": "false",
    "personnes_a_charge.personne_2.ressources_non": "true",
    "situation_logement_deposant.locataire": "false",
    "situation_logement_deposant.expulsion_oui": "false",
    "situation_logement_deposant.expulsion_non": "true",
    "situation_logement_deposant.proprietaire": "true",
    "situation_logement_deposant.saisie_immobiliere_oui": "false",
    "situation_logement_deposant.saisie_immobiliere_non": "true",
    # Page 6 : deux dettes remplies sur les quatre et cinq emplacements ouverts
    "dettes_logement.dette_logement_1.nom_creancier": "Syndic Foncia Meaux",
    "dettes_logement.dette_logement_1.adresse_creancier": "8 rue Saint-Remy, 77100 Meaux",
    "dettes_logement.dette_logement_1.reference": "COPRO-2021-118",
    "dettes_logement.dette_logement_1.montant_impaye": "2450.80",
    "dettes_logement.dette_logement_1.poursuites_oui": "false",
    "dettes_logement.dette_logement_1.poursuites_non": "true",
    "dettes_courantes.dette_courante_1.nom_creancier": "EDF",
    "dettes_courantes.dette_courante_1.adresse_creancier": "TSA 70254, 92919 La Defense",
    "dettes_courantes.dette_courante_1.reference": "CT-4455-8821",
    "dettes_courantes.dette_courante_1.montant_impaye": "612.35",
    "dettes_courantes.dette_courante_1.poursuites_oui": "false",
    "dettes_courantes.dette_courante_1.poursuites_non": "true",
    "dettes_courantes.dette_courante_2.nom_creancier": "Tresor Public - SIP Meaux",
    "dettes_courantes.dette_courante_2.adresse_creancier": "2 avenue Salvador Allende, 77100 Meaux",
    "dettes_courantes.dette_courante_2.reference": "Taxe fonciere 2023",
    "dettes_courantes.dette_courante_2.montant_impaye": "940.00",
    "dettes_courantes.dette_courante_2.poursuites_oui": "true",
    "dettes_courantes.dette_courante_2.poursuites_non": "false",
    # Page 9
    "credits_immobiliers.pret_immo_1.nom_creancier": "Credit Foncier Regional",
    "credits_immobiliers.pret_immo_1.adresse_creancier": "19 boulevard Jourdan, 75014 Paris",
    "credits_immobiliers.pret_immo_1.nom_assureur": "Assur'Pret SA, 5 rue du Port, 75012 Paris",
    "credits_immobiliers.pret_immo_1.reference": "IMMO-2015-77321",
    "credits_immobiliers.pret_immo_1.date_octroi": "2015-07-01",
    "credits_immobiliers.pret_immo_1.capital_emprunte": "185000",
    "credits_immobiliers.pret_immo_1.taux": "2,15 %",
    "credits_immobiliers.pret_immo_1.mensualite": "842.60",
    "credits_immobiliers.pret_immo_1.assurance_mensuelle": "46.20",
    "credits_immobiliers.pret_immo_1.restant_du": "121450.00",
    "credits_immobiliers.pret_immo_1.montant_impaye": "2527.80",
    "credits_immobiliers.pret_immo_1.montant_exigible": "0",
    "credits_immobiliers.pret_immo_1.poursuites_oui": "false",
    "credits_immobiliers.pret_immo_1.poursuites_non": "true",
    # Page 10 : deux prets a la consommation sur les six emplacements ouverts
    "credits_consommation.pret_1.nom_creancier": "Sofinco",
    "credits_consommation.pret_1.adresse_creancier": "1 boulevard de la Liberte, 59000 Lille",
    "credits_consommation.pret_1.reference": "CONSO-2021-99812",
    "credits_consommation.pret_1.date_octroi": "2021-03-15",
    "credits_consommation.pret_1.capital_emprunte": "12000",
    "credits_consommation.pret_1.taux": "5,90 %",
    "credits_consommation.pret_1.mensualite": "245.10",
    "credits_consommation.pret_1.restant_du": "6890.40",
    "credits_consommation.pret_1.montant_impaye": "735.30",
    "credits_consommation.pret_1.montant_exigible": "0",
    "credits_consommation.pret_1.poursuites_oui": "false",
    "credits_consommation.pret_1.poursuites_non": "true",
    "credits_consommation.pret_2.nom_creancier": "Cetelem",
    "credits_consommation.pret_2.adresse_creancier": "61 avenue Halley, 59650 Villeneuve-d'Ascq",
    "credits_consommation.pret_2.reference": "CONSO-2022-33190",
    "credits_consommation.pret_2.date_octroi": "2022-10-04",
    "credits_consommation.pret_2.capital_emprunte": "5000",
    "credits_consommation.pret_2.taux": "6,40 %",
    "credits_consommation.pret_2.mensualite": "132.75",
    "credits_consommation.pret_2.restant_du": "3410.00",
    "credits_consommation.pret_2.montant_impaye": "398.25",
    "credits_consommation.pret_2.montant_exigible": "398.25",
    "credits_consommation.pret_2.poursuites_oui": "true",
    "credits_consommation.pret_2.poursuites_non": "false",
}

#: Champs que l'OCR rend avec une confiance basse. Le dataset porte un seuil a
#: 0.8 : ces champs passent donc en dessous, ce qui donne a la demonstration des
#: cas a arbitrer au lieu d'un document uniformement vert. Les cles sont celles
#: de CERFA_DOSSIER.
CERFA_LOW_CONFIDENCE = {
    "deposant.prenoms": 0.61,
    "co_deposant.nom_naissance": 0.68,
    "coordonnees_personnelles.telephone_co_deposant": 0.54,
    "assist_travailleur_social.adresse": 0.72,
    "dettes_logement.dette_logement_1.montant_impaye": 0.66,
    "credits_immobiliers.pret_immo_1.taux": 0.58,
    "credits_consommation.pret_2.reference": 0.71,
}

#: Confiance des champs lus sans difficulte.
CERFA_DEFAULT_CONFIDENCE = 0.94


def _cerfa_key(section_id: str, group_id: Optional[str], field_key: str) -> str:
    """Clef de CERFA_DOSSIER pour un FieldSpec donne."""
    if group_id:
        return f"{section_id}.{group_id}.{field_key}"
    return f"{section_id}.{field_key}"


def _cerfa_raw_json(specs: List[Dict]) -> dict:
    """Resultat OCR fictif, reconstruit depuis le dossier.

    Le contenu reste volontairement minimal : le seed n'a pas de PDF a lire, et
    raw_json ne sert ici qu'a ce que l'ecran de relecture trouve une trace de
    l'appel OCR derriere les valeurs annotees.
    """
    pages: Dict[int, List[dict]] = {}
    for spec in specs:
        key = _cerfa_key(spec["section_id"], spec["group_id"], spec["field_key"])
        value = CERFA_DOSSIER.get(key)
        if value is None:
            continue
        pages.setdefault(spec["page"], []).append(
            {
                "section_id": spec["section_id"],
                "group_id": spec["group_id"],
                "field_key": spec["field_key"],
                "extracted_value": value,
                "confidence": CERFA_LOW_CONFIDENCE.get(key, CERFA_DEFAULT_CONFIDENCE),
            }
        )
    return {
        "smartdoc_version": "0.3",
        "document_id": "cerfa_13594-02_000001",
        "coordinate_unit": "pixel",
        "page_count": 12,
        "metadata": {
            "ocr": {"provider": OcrProvider.MISTRAL.value, "processed_at": "2024-03-08T09:12:00Z"},
            "document_type": CERFA_DOCUMENT_TYPE,
        },
        "pages": [
            {"page_number": page, "fields": fields} for page, fields in sorted(pages.items())
        ],
    }


async def seed_cerfa(
    session: AsyncSession,
    project: Project,
    pdf_path: Optional[Path],
    fake_ocr: bool,
) -> None:
    """Schema CERFA, et selon le cas le document qui va avec.

    Trois issues, de la plus fidele a la plus rapide :

        --pdf <fichier>   un vrai CERFA depose sur le PVC, en statut RECEIVED.
                          PageImageWorker en rend les pages, puis
                          PrepopulationWorker appelle l'OCR et cree les champs.
                          Les valeurs annotees sont alors celles du document.
        --fake-ocr        un dossier fictif ecrit directement en base, sans PDF
                          ni appel OCR. Rien a afficher dans le visualiseur.
        par defaut        schema et lot seuls. C'est ce qu'il faut pour deposer
                          ensuite un document par l'IHM ou par l'API.
    """
    print("\n --- Mode : CERFA surendettement 13594*02 (champs de cerfa_v2.py) ---")

    print(" [4/8] DocSchema...")
    schema = DocSchema(
        project_id=project.id,
        version=CERFA_SCHEMA_VERSION,
        name=CERFA_SCHEMA_NAME,
        document_type=CERFA_DOCUMENT_TYPE,
    )
    session.add(schema)
    await session.flush()
    print(f"        {schema}")

    print(" [5/8] FieldSpecs (derives de cerfa_v2.py)...")
    specs = build_specs()
    field_specs = [
        FieldSpec(
            schema_id=schema.id,
            page=spec["page"],
            section_id=spec["section_id"],
            section_label=spec["section_label"],
            group_id=spec["group_id"],
            field_key=spec["field_key"],
            display_label=spec["display_label"],
            value_type=spec["value_type"],
            required=spec["required"],
            display_order=spec["display_order"],
        )
        for spec in specs
    ]
    session.add_all(field_specs)
    await session.flush()
    grouped = sum(1 for spec in specs if spec["group_id"] is not None)
    print(
        f"        {len(field_specs)} FieldSpecs crees sur {len(CERFA_V2_PAGE_FIELDS)} pages, "
        f"dont {grouped} dans une section repetable"
    )
    for section_id, (count, prefix, _) in REPEATABLE_SECTIONS.items():
        per_instance = sum(1 for spec in specs if spec["section_id"] == section_id) // count
        print(
            f"            {SECTION_LABELS.get(section_id, section_id)} : "
            f"{count} instances ({prefix}_1 a {prefix}_{count}), "
            f"{per_instance} champs chacune"
        )

    print(" [6/8] Dataset...")
    dataset = Dataset(
        project_id=project.id,
        schema_id=schema.id,
        name=CERFA_DATASET_NAME,
        description="Lot de declarations de surendettement",
        ocr_provider=OcrProvider.MISTRAL.value,
        status=DatasetStatus.ACTIVE.value,
        required_operators=2,
        configs={"confidence_threshold": 0.8, "export_format": "json_pdf"},
    )
    session.add(dataset)
    await session.flush()
    print(f"        {dataset}")

    if pdf_path is not None:
        await _seed_cerfa_real_pdf(session, dataset, pdf_path)
        return
    if not fake_ocr:
        print("\n Schema et lot crees, sans document.")
        print(" Deposer un CERFA dans ce lot, puis lancer les workers :")
        print("     python -m adam_worker.main")
        print(" Ou partir d'un PDF local : seed.py --pdf <fichier.pdf>")
        return

    print(" [7/8] File + Document (dossier fictif, sans appel OCR)...")
    raw_json = _cerfa_raw_json(specs)
    json_bytes = json.dumps(raw_json, ensure_ascii=False).encode("utf-8")
    file_ = File(
        file_path="/pvc/dires-idf/cerfa/2024_03/cerfa_13594-02_000001.pdf",
        storage_type="PVC",
        mime_type="application/pdf",
        page_count=raw_json["page_count"],
        file_size_bytes=len(json_bytes),
        sha256_checksum=sha256_bytes(json_bytes),
    )
    session.add(file_)
    await session.flush()
    document = Document(
        dataset_id=dataset.id,
        file_id=file_.id,
        file_name="cerfa_13594-02_000001.pdf",
        metadata={
            "source": "PVC",
            "lot": "2024-03",
            "reception_date": "2024-03-07",
            "document_type": CERFA_DOCUMENT_TYPE,
        },
        status=DocumentStatus.IN_PROGRESS.value,
    )
    session.add(document)
    await session.flush()
    print(f"        {file_}")
    print(f"        {document}")

    print(" [8/8] OcrResult + DocumentFields...")
    ocr_result = OcrResult(
        document_id=document.id,
        dataset_id=dataset.id,
        storage_mode=StorageMode.JSONB.value,
        raw_json=raw_json,
    )
    session.add(ocr_result)
    await session.flush()

    doc_fields = []
    filled = 0
    for fs in field_specs:
        key = _cerfa_key(fs.section_id, fs.group_id, fs.field_key)
        value = CERFA_DOSSIER.get(key)
        confidence = (
            CERFA_LOW_CONFIDENCE.get(key, CERFA_DEFAULT_CONFIDENCE) if value is not None else None
        )
        if value is not None:
            filled += 1
        doc_fields.append(
            DocumentField(
                document_id=document.id,
                field_spec_id=fs.id,
                group_id=fs.group_id,
                ocr_value=value,
                resolved_value=value,
                status=DocumentFieldStatus.PENDING.value,
                ocr_confidence=confidence,
                consensus_reached=False,
                # Meme marquage que le worker de pre-alimentation : un champ
                # detecte porte ocr_system, un champ vide n'a pas de resolveur.
                resolved_by=OCR_RESOLVER if value is not None else None,
            )
        )
    session.add_all(doc_fields)
    await session.flush()
    below = sum(1 for fs in field_specs if _cerfa_key(fs.section_id, fs.group_id, fs.field_key) in CERFA_LOW_CONFIDENCE)
    print(f"        {len(doc_fields)} DocumentFields crees, dont {filled} renseignes par l'OCR")
    print(f"        {below} sous le seuil de confiance du dataset (0.8)")


async def _seed_cerfa_real_pdf(session: AsyncSession, dataset: Dataset, pdf_path: Path) -> None:
    """Depose un vrai CERFA dans le lot, et laisse les workers faire le reste.

    Le document est cree en RECEIVED, sans le moindre champ : c'est
    PageImageWorker qui en rendra les pages, puis PrepopulationWorker qui
    appellera l'OCR et creera les DOCUMENT_FIELD depuis le schema. Ecrire ici
    des champs vides les mettrait en concurrence avec ceux du worker, que la
    contrainte d'unicite (document_id, field_spec_id, group_id) rejetterait.

    Le PDF est copie sous le PVC, pas lu sur place : file_path est relatif a la
    racine du PVC pour les workers comme pour l'API, et un chemin pointant hors
    du volume serait introuvable des que l'un des deux tourne dans un conteneur.
    """
    print(" [7/8] Copie du PDF sur le PVC...")
    pvc_root = Path(api_settings.pvc_mount_path)
    relative_path = Path("cerfa") / pdf_path.name
    destination = pvc_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = pdf_path.read_bytes()
    destination.write_bytes(pdf_bytes)
    print(f"        {pdf_path} -> {destination}")

    # Compte reel des pages : le worker le recalculera au rendu, mais page_count
    # est non nul en base et un 1 provisoire ferait mentir toute lecture faite
    # entre le seed et le premier cycle du worker.
    page_count = _pdf_page_count(pdf_path)

    print(" [8/8] File + Document (statut RECEIVED)...")
    file_ = File(
        file_path=str(relative_path).replace("\\", "/"),
        storage_type="PVC",
        mime_type="application/pdf",
        page_count=page_count,
        file_size_bytes=len(pdf_bytes),
        sha256_checksum=sha256_bytes(pdf_bytes),
    )
    session.add(file_)
    await session.flush()
    document = Document(
        dataset_id=dataset.id,
        file_id=file_.id,
        file_name=pdf_path.name,
        metadata={
            "source": "seed",
            "document_type": CERFA_DOCUMENT_TYPE,
            "origine": str(pdf_path),
        },
        status=DocumentStatus.RECEIVED.value,
    )
    session.add(document)
    await session.flush()
    print(f"        {file_}")
    print(f"        {document}")

    print(f"\n Document {document.id} depose, {page_count} page(s), aucun champ.")
    print(" Lancer les workers pour le rendu des pages puis l'OCR :")
    print("     python -m adam_worker.main")
    print(f" Puis verifier ce que l'OCR a reellement rendu, palier par palier :")
    print(f"     python scripts/diag_prepopulation.py {document.id}")


def _pdf_page_count(pdf_path: Path) -> int:
    """Nombre de pages du PDF, ou 1 si PyMuPDF n'est pas installe.

    Le seed n'a pas besoin de rendre les pages, seulement de les compter : un
    environnement sans moteur de rendu doit pouvoir seeder quand meme, quitte a
    ce que le worker corrige le compte a son premier cycle.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("        PyMuPDF absent : page_count pose a 1, le worker le corrigera")
        return 1
    with fitz.open(pdf_path) as pdf:
        return pdf.page_count



# Helper partagé
async def _seed_dataset_to_fields(
    session: AsyncSession,
    project: Project,
    schema: DocSchema,
    field_specs: List[FieldSpec],
    file_path: str,
    file_name: str,
    raw_json: dict,
    ocr_values: Dict,
    document_id_str: str,
    step_offset: int,
) -> None:
    print(f"  [{step_offset}/8] Dataset...")
    dataset = Dataset(
       project_id=project.id, schema_id=schema.id,
       name=DEMO_DATASET_NAME,
       description="Premier lot de documents",
       ocr_provider=OcrProvider.PULSAR.value,
       status=DatasetStatus.ACTIVE.value,
       required_operators=2,
       configs={"confidence_threshold": 0.8, "export_format": "json_pdf"},
    )
    session.add(dataset)
    await session.flush()
    print(f"        {dataset}")
    print(f"  [{step_offset + 1}/8] File + Document...")
    json_bytes = json.dumps(raw_json, ensure_ascii=False).encode("utf-8")
    sha256 = sha256_bytes(json_bytes)
    file_ = File(
       file_path=file_path, storage_type="PVC",
       mime_type="application/pdf", page_count=raw_json.get("page_count", 2),
       file_size_bytes=len(json_bytes), sha256_checksum=sha256,
    )
    session.add(file_)
    await session.flush()
    document = Document(
       dataset_id=dataset.id, file_id=file_.id, file_name=file_name,
       metadata={"source": "PVC", "lot": "2024-01", "reception_date": "2024-01-15"},
       status=DocumentStatus.IN_PROGRESS.value,
    )
    session.add(document)
    await session.flush()
    print(f"        {file_}")
    print(f"        {document}")
    print(f"  [{step_offset + 2}/8] OcrResult + DocumentFields...")
    ocr_result = OcrResult(
       document_id=document.id, dataset_id=dataset.id,
       storage_mode=StorageMode.JSONB.value, raw_json=raw_json,
    )
    session.add(ocr_result)
    await session.flush()
    doc_fields = []
    for fs in field_specs:
       ocr_val, confidence, polygon = ocr_values.get(fs.field_key, (None, None, None))
       doc_fields.append(DocumentField(
           document_id=document.id, field_spec_id=fs.id, group_id=None,
           ocr_value=ocr_val, resolved_value=ocr_val,
           status=DocumentFieldStatus.PENDING.value,
           ocr_confidence=confidence, consensus_reached=False, ocr_polygon=polygon,
       ))
    session.add_all(doc_fields)
    await session.flush()
    print(f"        {len(doc_fields)} DocumentFields crees")
# Main
async def main(
    reset: bool,
    json_path: Optional[Path],
    form_demo: bool,
    pdf_path: Optional[Path],
    fake_ocr: bool,
) -> None:
    init_engine(settings.async_database_url, echo=False)
    await create_tables()
    factory = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    async with factory() as session:
       if reset:
           await reset_db(session)
       _, admin, operator, project = await seed_infrastructure(session)
       if json_path:
           await seed_from_form_json(session, project, json_path)
       elif form_demo:
           await seed_hardcoded(session, project)
       else:
           await seed_cerfa(session, project, pdf_path=pdf_path, fake_ocr=fake_ocr)
       await session.commit()
    await get_engine().dispose()
    print("\n Seed termine avec succes")
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed ADAM database")
    parser.add_argument("--reset", action="store_true", help="Vide les tables avant de seeder")
    parser.add_argument("--json", default=None, help="Chemin vers un fichier JSON format formulaire v0.3")
    parser.add_argument(
        "--form-demo",
        action="store_true",
        help="Ancien formulaire synthetique hardcode, au lieu du CERFA surendettement",
    )
    parser.add_argument(
        "--pdf",
        default=None,
        help=(
            "Chemin d'un vrai CERFA a deposer dans le lot. Il est copie sur le "
            "PVC en statut RECEIVED : les workers en font le rendu puis l'OCR"
        ),
    )
    parser.add_argument(
        "--fake-ocr",
        action="store_true",
        help=(
            "Remplit les champs avec un dossier fictif, sans PDF ni appel OCR. "
            "Pratique pour une demo hors ligne, mais rien a afficher en regard"
        ),
    )
    args = parser.parse_args()

    if args.pdf and args.fake_ocr:
       print("--pdf et --fake-ocr s'excluent : l'un fait appeler l'OCR, l'autre l'evite")
       sys.exit(1)

    pdf_path = None
    if args.pdf:
       pdf_path = Path(args.pdf)
       if not pdf_path.exists():
           print(f"PDF introuvable : {args.pdf}")
           sys.exit(1)
    json_path = None
    if args.json:
       json_path = Path(args.json)
       if not json_path.exists():
           json_path = Path(__file__).parent.parent / args.json
       if not json_path.exists():
           json_path = Path(__file__).parent / args.json
       if not json_path.exists():
           print(f"Fichier introuvable : {args.json}")
           sys.exit(1)
    print(SEPARATOR)
    print("Seed de la base de donnees")
    if json_path:
       mode = "FORM JSON"
    elif args.form_demo:
       mode = "Formulaire demo hardcode"
    elif pdf_path:
       mode = f"CERFA surendettement 13594*02 + document reel ({pdf_path.name})"
    elif args.fake_ocr:
       mode = "CERFA surendettement 13594*02 + dossier fictif"
    else:
       mode = "CERFA surendettement 13594*02, schema seul"
    print(f" Mode : {mode}")
    print(SEPARATOR)
    asyncio.run(
       main(
           reset=args.reset,
           json_path=json_path,
           form_demo=args.form_demo,
           pdf_path=pdf_path,
           fake_ocr=args.fake_ocr,
       )
    )
    print(SEPARATOR)
