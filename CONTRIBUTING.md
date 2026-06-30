# Contribuer au projet ADAM

## Branches

- `main` <- production, protégée, merge via MR uniquement
- `develop` <- intégration continue, base de toutes les branches
- `feature/xxx` <- nouvelle fonctionnalité (depuis develop)
- `fix/xxx` <- correction de bug (depuis develop)

## Convention de commits

Format : `<type>(<scope>): <description courte>`

| Type | Usage |
| :--- | :--- |
| `feat` | Nouvelle fonctionnalité |
| `fix` | Correction de bug |
| `refactor` | Refactoring sans changement fonctionnel |
| `test` | Ajout ou modification de tests |
| `docs` | Documentation uniquement |
| `chore` | Outillage, config, dépendances |
| `migration` | Migration Alembic |

### Exemples

- `feat(orm): add FieldSpec model with section_id and polygon constraint`
- `feat(api): add GET /documents/{id}/fields/by-section endpoint`
- `fix(session): handle special characters in POSTGRES_PASSWORD via URL.create`
- `migration: init tables labellisation`
- `chore(config): add pylint and coverage quality gates`
- `docs(adam_core): add README with Alembic workflow`

## Quality Gates

Avant merge sur `develop` :

| Métrique | Seuil |
| :--- | :--- |
| Pylint score | >= 9.0 / 10 |
| Couverture de tests | >= 80% |
| Alembic migrations | `alembic upgrade head` sans erreur |
| API startup | `uvicorn` démarre sans erreur |

### Commandes de vérification

```bash
python -m pylint src/adam_core src/adam_api
python -m pytest --cov=src --cov-report=term-missing
cd src/adam_core && python -m alembic upgrade head
```

## Workflow Sprint

1. Créer la branche : `git checkout -b feature/ma-feature develop`
2. Développer + commit au fil de l'eau
3. Vérifier les quality gates localement
4. Push : `git push origin feature/ma-feature`
5. Ouvrir une Merge Request vers `develop`
6. Review + merge


Daily resume : 
---
Rapport de sprint — Schemas Pydantic de réponse (adam)

Période : vendredi 27 juin → dimanche 29 juin 2026

---
Contexte

L'objectif était de remplacer tous les retours non typés (Dict[str, Any]) des endpoints FastAPI par des schemas Pydantic stricts, centralisés dans src/adam_core/schemas/responses.py. Chaque endpoint expose maintenant un response_model explicite, ce qui garantit la sérialisation, la validation, et la documentation Swagger auto-générée.

---
Schemas créés — 46 schemas en 10 catégories

Catégorie: Organisation
Schemas: OrganisationOut, OrganisationPatchOut, OrganisationArchiveOut,
  OrgUserOut, UserProjectRefOut
────────────────────────────────────────
Catégorie: Project
Schemas: ProjectOut, ProjectDetailOut, ProjectCreatedOut, UserProjectOut,
  UserRolePatchOut
────────────────────────────────────────
Catégorie: Dataset
Schemas: DatasetOut, DatasetStatsOut
────────────────────────────────────────
Catégorie: File
Schemas: FileOut, FileDetailOut, FileCreatedOut, FilePatchOut, FileRefOut
────────────────────────────────────────
Catégorie: Document
Schemas: DocumentOut, DocumentFullOut, DocumentFieldInPageOut,
  DocumentSectionOut, DocumentPageOut, DocumentOcrResultOut, DocumentJobOut,
  DocumentFieldOut, DocumentFieldPatchOut, FieldBySectionItemOut,
  DocumentFieldsBySectionOut
────────────────────────────────────────
Catégorie: Job
Schemas: JobOut, JobCreatedOut, JobSubmitOut, FieldProposalOut, JobDetailOut,
  JobFieldItemOut, JobSectionOut, JobPageOut
────────────────────────────────────────
Catégorie: Ingestion
Schemas: FileIngestionItemOut, IngestionOut
────────────────────────────────────────
Catégorie: OCR
Schemas: OcrResultOut, OcrResultDetailOut, OcrResultCreatedOut
────────────────────────────────────────
Catégorie: Schema
Schemas: SchemaListItemOut, SchemaDetailOut, SchemaCreatedOut,
  FieldSpecItemOut, FieldSpecDetailOut, FieldSpecCreatedOut
────────────────────────────────────────
Catégorie: User
Schemas: UserListItemOut, UserDetailOut, UserCreatedOut, UserPatchOut,
  UserProjectDetailOut

---
Mapping complet endpoints → response_model

Datasets — DatasetOut, DatasetStatsOut, IngestionOut
Documents — DocumentOut, DocumentFullOut, DocumentFieldOut, DocumentFieldsBySectionOut, DocumentFieldPatchOut
Files — FileOut, FileDetailOut, FileCreatedOut, FilePatchOut
Jobs — JobOut, JobDetailOut, JobCreatedOut, JobSubmitOut, FieldProposalOut
Organisations — OrganisationOut, OrgUserOut
Projects — ProjectOut, ProjectDetailOut, ProjectCreatedOut, UserProjectOut, UserRolePatchOut
OCR — OcrResultOut, OcrResultDetailOut, OcrResultCreatedOut
Schemas — SchemaListItemOut, SchemaDetailOut, FieldSpecDetailOut, SchemaCreatedOut, FieldSpecCreatedOut, FieldSpecItemOut
Users — UserListItemOut, UserDetailOut, UserCreatedOut, UserPatchOut

---
Techniques utilisées

ConfigDict(from_attributes=True) — sur tous les schemas ORM-facing. Permet Schema.model_validate(orm_object) directement sans conversion manuelle.

validation_alias — dans DocumentOut pour mapper metadata_ (nom ORM, évite le conflit avec Pydantic) vers metadata (nom API) :
metadata: Optional[Dict[str, Any]] = Field(default=None, validation_alias="metadata_")

Schemas imbriqués — vues hiérarchiques profondes pour les endpoints détaillés :
- DocumentFullOut → List[DocumentPageOut] → List[DocumentSectionOut] → List[DocumentFieldInPageOut]
- JobDetailOut → List[JobPageOut] → List[JobSectionOut] → List[JobFieldItemOut]

Schemas spécialisés par action — un schema distinct par verbe HTTP, jamais un schema générique fourre-tout : FileOut (lecture), FileCreatedOut (POST + flag deduplicated), FilePatchOut (PATCH champs mutables seulement), FileDetailOut (GET/{id} avec documents_count calculé).

Champs calculés hors ORM — certains champs n'existent pas directement en base et sont injectés dans le router : FileDetailOut.documents_count, DatasetStatsOut.documents_total/validated, SchemaCreatedOut.field_specs_created.

page_count via property ORM — Document.page_count est une @property qui lit File.page_count quand la relation est chargée (selectinload(Document.file) ajouté dans tous les endpoints documents concernés).

Garde de verrouillage (423 Locked) — _check_schema_not_locked() dans le router schemas bloque toute mutation sur un schema utilisé par un dataset non-brouillon.

Protection intégrité référentielle (409 Conflict) — DELETE /field-specs vérifie via func.count(DocumentField.id) qu'aucun document ne référence la spec avant suppression.

---
Tests écrits — détail par fichier

Fichier: test_schemas_responses.py
Tests: 45
Ce qui est couvert: Instanciation pure Pydantic de tous les schemas, alias
  metadata_, from_orm, imbrication profonde, cas limites
────────────────────────────────────────
Fichier: test_router_schemas.py
Tests: 39
Ce qui est couvert: Tous les endpoints schemas, codes
  200/201/204/404/409/422/423, verrou, duplication, pattern field_key
────────────────────────────────────────
Fichier: test_router_organisations.py
Tests: 28
Ce qui est couvert: CRUD orgs, liste users, archive/restore
────────────────────────────────────────
Fichier: test_router_users.py
Tests: 26
Ce qui est couvert: CRUD users, relations projets, archive/restore
────────────────────────────────────────
Fichier: test_router_documents.py
Tests: 25
Ce qui est couvert: Liste, vue simple/full, champs, by-section, PATCH
  status/field, 422
────────────────────────────────────────
Fichier: test_router_projects.py
Tests: 24
Ce qui est couvert: CRUD projets, gestion rôles utilisateurs
────────────────────────────────────────
Fichier: test_router_jobs.py
Tests: 21
Ce qui est couvert: Liste, détail structuré pages/sections, 409 sur
  soumis/annulé, 404
────────────────────────────────────────
Fichier: test_router_ocr.py
Tests: 15
Ce qui est couvert: Liste, détail, création résultat OCR
────────────────────────────────────────
Fichier: test_router_files.py
Tests: 16
Ce qui est couvert: Liste, détail + documents_count, déduplication (200 vs
  201), PATCH
────────────────────────────────────────
Fichier: test_router_datasets.py
Tests: 16
Ce qui est couvert: Liste, stats, création, PATCH, changement de statut avec
  garde enum
────────────────────────────────────────
Fichier: test_service_ingestion.py
Tests: 14
Ce qui est couvert: looks_like_pdf (magic bytes / content-type / extension),
  pvc_relative_path, _get_or_create_file (3 cas), ingest_pdf (already_exists /
   created / reused)
────────────────────────────────────────
Fichier: test_service_consensus.py
Tests: 10
Ce qui est couvert: _apply_vote (no proposals / majorité / tie), _resolve (6
  cas : error / already_validated / waiting / resolved / disputed),
  try_resolve exception handler
────────────────────────────────────────
Fichier: test_hashing.py
Tests: 7
Ce qui est couvert: sha256_bytes (conformité hashlib, longueur 64, vide),
  sha256_file (Path / str / vide / fichier > 1 Mo)

---
Progression git

# Vendredi 27 juin
fcb0b6d  feat(sprint3/CA-1,2): typed schemas + page_count in Document responses
3e87db0  test(sprint3): add 135 unit tests for schemas and routers

# Dimanche 29 juin
f2dbfc5  fix(mypy): type pages dict and import Any in jobs router
26572e6  fix(mypy): make started_at Optional in JobOut and JobDetailOut
8adee1e  test(hashing): add coverage for empty, string path, and multipart cases
a1982e4  test(services): add unit tests for consensus and ingestion services
69831ad  feat(schemas+routers+tests): type all Dict[str,Any] response models
b440da1  feat(ocr+org): align routers and schemas with full implementation
9a2451f  feat(users): align router and schemas with full implementation
78287e7  feat(sprint3): fully implement projects and schemas routers
d3c6113  feat(sprint3/schemas): full FieldSpec CRUD, duplicate endpoint, lock guard
99eeb52  fix(schemas): block delete_field_spec if DocumentField references the spec
509ea50  fix(mypy): annotate referenced as int
bf391a6  fix(tests): set scalar_one=0 in _unlocked_db for DocumentField count mock
b80b8ad  fix(pylint): disable not-callable false positive on func.count

---
Résultat final

295 passed, 1 failed (test_exceptions — non lié aux schemas)

Répartition :
  45  test_schemas_responses      (schemas Pydantic purs)
  39  test_router_schemas
  28  test_router_organisations
  26  test_router_users
  25  test_router_documents
  24  test_router_projects
  21  test_router_jobs
  16  test_router_files
  16  test_router_datasets
  15  test_router_ocr
  14  test_service_ingestion
  10  test_service_consensus
   7  test_hashing

Bilan :
- 100% des endpoints ont un response_model Pydantic typé
- Zéro Dict[str, Any] en retour d'endpoint
- Swagger UI (/docs) documente automatiquement tous les schemas
- Sérialisation ORM → Pydantic via from_attributes sans conversion manuelle
- Toute la logique métier (verrou 423, conflit 409, 404, consensus, ingestion, hashing) couverte par des tests unitaires
