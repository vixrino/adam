# 01 - Documentation BDD

Cette page décrit les tables de la base PostgreSQL de NOTA, regroupées par module. Pour chaque table : à quoi elle sert, puis ses colonnes.

**Conventions**

* Toutes les dates sont des `timestamptz` (date et heure avec fuseau). `created_at` et `updated_at` sont remplies automatiquement par la base.
* `PK` : clé primaire. `FK` : référence vers une autre table. `UNIQUE` : deux lignes ne peuvent pas avoir la même valeur.
* Les statuts et les rôles sont stockés en texte, en majuscules (`ACTIVE`, `OPERATOR`…).
* Le schéma est créé et mis à jour uniquement par les migrations Alembic.

**Sommaire**

* Module Utilisateurs et organisations : ORGANISATION, USER, USER_PROJECT
* Module Projet et schéma : PROJECT, DOC_SCHEMA, SCHEMA_PAGE, FIELD_SPEC
* Module Documents : DATASET, FILE, DOCUMENT, DOCUMENT_PROGRESS, OCR_RESULT, DOCUMENT_FIELD
* Module Labellisation : JOB, FIELD_PROPOSAL
* Module Tests de qualité OCR : DATASET_EXPORT, TEST_RECIPE, TEST_EXECUTION, COMPARISON_RESULT, EVALUATION_REPORT

---

## Module : Utilisateurs et organisations

### 1. Table ORGANISATION

*Une organisation est une entité cliente de NOTA (par exemple une direction). Un utilisateur ne voit que les données de son organisation, sauf les rôles de plateforme NOTA_SUPERVISOR et NOTA_ADMIN.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `name` | `varchar NOT NULL` | Nom de l'organisation |
| `slug` | `varchar NOT NULL UNIQUE` | Identifiant court et lisible, ex. `dires` |
| `created_at` | `timestamptz NOT NULL` | Date de création |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |
| `deleted_at` | `timestamptz nullable` | Date de suppression logique ; vide tant que l'organisation existe |

---

### 2. Table USER

*Un agent qui utilise NOTA. Il est reconnu par son matricule, lu dans le jeton de connexion FBI. Il appartient à une seule organisation.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `organisation_id` | `int NOT NULL FK` | Organisation de l'agent, référence `ORGANISATION.id` |
| `email` | `varchar NOT NULL UNIQUE` | Adresse électronique |
| `full_name` | `varchar NOT NULL` | Nom complet |
| `matricule` | `varchar NOT NULL UNIQUE` | Matricule Banque de France, sert à reconnaître l'agent à la connexion |
| `platform_role` | `varchar nullable` | Rôle sur toute la plateforme : `NOTA_SUPERVISOR`, `NOTA_ADMIN`, `NOTA_CLIENT` ; vide pour un agent sans rôle de plateforme |
| `status` | `varchar NOT NULL default 'ACTIVE'` | `ACTIVE`, `INACTIVE`, `SUSPENDED` |
| `created_at` | `timestamptz NOT NULL` | Date de création |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |
| `last_login_at` | `timestamptz nullable` | Dernière connexion réussie |
| `deleted_at` | `timestamptz nullable` | Date de suppression logique |

---

### 3. Table USER_PROJECT

*Table de jointure entre utilisateurs et projets. Le rôle détermine ce que l'agent peut faire dans le projet.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `user_id` | `int NOT NULL FK` | Référence `USER.id` |
| `project_id` | `int NOT NULL FK` | Référence `PROJECT.id` |
| `role` | `varchar NOT NULL default 'OPERATOR'` | Rôle dans le projet : `OPERATOR` (vérifie les documents), `BUSINESS_ADMIN` (administrateur métier, tranche les litiges) |
| `created_at` | `timestamptz NOT NULL` | Date d'affectation au projet |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

*Clé primaire composite sur `(user_id, project_id)`.*

---

## Module : Projet et schéma

### 4. Table PROJECT

*Un projet regroupe des lots de documents (datasets) d'une même organisation.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `organisation_id` | `int NOT NULL FK` | Organisation propriétaire, référence `ORGANISATION.id` |
| `name` | `varchar NOT NULL` | Nom du projet |
| `description` | `text nullable` | Description libre |
| `status` | `varchar NOT NULL default 'ACTIVE'` | `ACTIVE`, `ARCHIVED` |
| `created_at` | `timestamptz NOT NULL` | Date de création |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

---

### 5. Table DOC_SCHEMA

*Décrit un type de document : quelles pages, quels champs, de quel type. Un schéma appartient à un projet et porte un numéro de version.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `project_id` | `int NOT NULL FK` | Projet propriétaire, référence `PROJECT.id` |
| `version` | `int NOT NULL default 1` | Version du schéma, commence à 1 |
| `name` | `varchar NOT NULL` | Nom lisible |
| `document_type` | `varchar NOT NULL` | Type de document, ex. `CERFA_13710` |
| `created_at` | `timestamptz NOT NULL` | Date de création |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

---

### 6. Table SCHEMA_PAGE

*Une page attendue du document. Sa description sert à l'IA pour reconnaître la page, même si le PDF a été scanné dans le désordre.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `schema_id` | `int NOT NULL FK` | Schéma de la page, référence `DOC_SCHEMA.id` |
| `page_number` | `int NOT NULL` | Numéro de la page, à partir de 1 |
| `description` | `text NOT NULL` | Titres de rubrique imprimés sur la page, qui permettent de la reconnaître |
| `created_at` | `timestamptz NOT NULL` | Date de création |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

*Unicité sur `(schema_id, page_number)`.*

---

### 7. Table FIELD_SPEC

*Un champ du schéma : sa page, sa rubrique, son type et son libellé. Les champs d'un tableau (une ligne par crédit, par personne à charge…) sont répétés avec un `group_id` différent.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `schema_id` | `int NOT NULL FK` | Schéma du champ, référence `DOC_SCHEMA.id` |
| `page` | `int NOT NULL` | Page où le champ apparaît |
| `section_id` | `varchar NOT NULL` | Identifiant technique de la rubrique, ex. `credits_consommation` |
| `section_label` | `varchar NOT NULL` | Libellé de la rubrique affiché à l'opérateur |
| `group_id` | `varchar nullable` | Ligne d'un tableau, ex. `pret_1` ; vide pour un champ isolé |
| `field_key` | `varchar NOT NULL` | Clé du champ dans la rubrique, ex. `reference` |
| `display_label` | `varchar NOT NULL` | Libellé affiché à l'opérateur |
| `description` | `text nullable` | Consigne de lecture du champ, transmise à l'IA |
| `value_type` | `varchar NOT NULL default 'TEXT'` | `TEXT`, `NUMBER`, `DATE`, `DATETIME`, `BOOLEAN` |
| `required` | `boolean NOT NULL default false` | Champ obligatoire |
| `sensitive` | `boolean NOT NULL default false` | Donnée sensible (état civil, IBAN…) : sa valeur n'apparaît jamais dans les résultats de test |
| `display_order` | `int NOT NULL default 0` | Ordre d'affichage, aligné sur le formulaire papier |
| `polygon` | `float[] nullable` | Position du champ sur la page : 4 points, soit 8 nombres |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

*Unicité sur `(schema_id, section_id, group_id, field_key)`.*

---

## Module : Documents

### 8. Table DATASET

*Un lot de documents d'un même type, rattaché à un projet et à un schéma. Il fixe aussi le moteur OCR et le nombre d'opérateurs requis.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `project_id` | `int NOT NULL FK` | Projet, référence `PROJECT.id` |
| `schema_id` | `int NOT NULL FK` | Schéma imposé aux documents du lot, référence `DOC_SCHEMA.id` |
| `name` | `varchar NOT NULL` | Nom du lot |
| `description` | `text nullable` | Description libre |
| `ocr_provider` | `varchar(128) NOT NULL default 'PULSAR'` | Moteur OCR : `PULSAR`, `MISTRAL` |
| `ocr_model_id` | `varchar nullable` | Version du modèle OCR |
| `status` | `varchar NOT NULL default 'DRAFT'` | Cycle de vie : `DRAFT` → `ACTIVE` → `ARCHIVED` |
| `ocr_job_enabled` | `boolean NOT NULL default true` | Active le préremplissage automatique par l'OCR |
| `required_operators` | `int NOT NULL default 3` | Nombre d'opérateurs qui doivent vérifier chaque document |
| `expected_page_count` | `int nullable` | Nombre de pages exigé (12 pour le CERFA) ; un PDF qui n'a pas ce nombre est mis en `ERROR`. Vide = aucun contrôle |
| `configs` | `jsonb NOT NULL default '{}'` | Réglages libres du lot |
| `created_at` | `timestamptz NOT NULL` | Date de création |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

---

### 9. Table FILE

*Le fichier PDF physique stocké sur le PVC. Un même fichier n'est stocké qu'une fois, grâce à son empreinte SHA-256.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `file_path` | `varchar NOT NULL` | Chemin du fichier sur le PVC |
| `storage_type` | `varchar NOT NULL default 'pvc'` | Type de stockage |
| `mime_type` | `varchar NOT NULL default 'application/pdf'` | Type du fichier |
| `page_count` | `int NOT NULL default 1` | Nombre de pages, renseigné quand les images des pages sont produites |
| `file_size_bytes` | `int NOT NULL` | Taille en octets, pour suivre le volume stocké |
| `sha256_checksum` | `varchar NOT NULL UNIQUE` | Empreinte SHA-256 : évite les doublons et vérifie l'intégrité |
| `created_at` | `timestamptz NOT NULL` | Date de première réception |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

---

### 10. Table DOCUMENT

*Un document reçu dans un lot. Il pointe vers son fichier PDF et suit les étapes du traitement.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `dataset_id` | `int NOT NULL FK` | Lot du document, référence `DATASET.id` |
| `file_id` | `int NOT NULL FK` | Fichier PDF, référence `FILE.id` |
| `file_name` | `varchar NOT NULL` | Nom de fichier d'origine |
| `metadata` | `jsonb nullable` | Informations de réception : source, lot, date de dépôt, motif d'erreur… |
| `status` | `varchar NOT NULL default 'RECEIVED'` | `RECEIVED` → `INGESTED` (images prêtes) → `IN_PROGRESS` → `PENDING_CONSENSUS` → `VALIDATED` → `EXPORTED` → `ARCHIVED`. Aussi `DISPUTED` (litige) et `ERROR` (document refusé ou illisible) |
| `created_at` | `timestamptz NOT NULL` | Date de réception |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

---

### 11. Table DOCUMENT_PROGRESS

*L'avancement d'un document, recalculé en continu par un traitement automatique. Rien n'y est écrit à la main : c'est un constat de l'état réel des autres tables.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `document_id` | `int PK FK` | Document suivi, référence `DOCUMENT.id` |
| `stage` | `varchar NOT NULL` | Étape atteinte : `INGESTED`, `PAGES_RENDERED`, `OCR_AVAILABLE`, `FIELDS_PREFILLED`, `ANNOTATION`, `CONSENSUS_REACHED` |
| `pdf_received` | `boolean NOT NULL default false` | Le fichier PDF existe |
| `pages_rendered` | `boolean NOT NULL default false` | Les images des pages sont produites |
| `ocr_available` | `boolean NOT NULL default false` | Une lecture OCR existe |
| `fields_total` | `int NOT NULL default 0` | Nombre de champs du document |
| `fields_filled` | `int NOT NULL default 0` | Champs qui ont une valeur (OCR ou validée) |
| `fields_validated` | `int NOT NULL default 0` | Champs validés |
| `jobs_submitted` | `int NOT NULL default 0` | Vérifications soumises par les opérateurs |
| `jobs_required` | `int NOT NULL default 0` | Vérifications requises (`DATASET.required_operators`) |
| `computed_at` | `timestamptz NOT NULL` | Date du dernier calcul |

---

### 12. Table OCR_RESULT

*La réponse complète du moteur OCR pour un document.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `document_id` | `int NOT NULL FK` | Document lu, référence `DOCUMENT.id` |
| `dataset_id` | `int NOT NULL FK` | Lot, référence `DATASET.id` |
| `storage_mode` | `varchar NOT NULL default 'JSONB'` | `JSONB` (réponse stockée en base) ou `FILE` (sur le PVC) |
| `raw_json` | `jsonb nullable` | Réponse OCR complète ; vide si `storage_mode = FILE` |
| `processed_at` | `timestamptz NOT NULL` | Date de la lecture |

*Unicité sur `(document_id, dataset_id)`.*

---

### 13. Table DOCUMENT_FIELD

*La valeur d'un champ pour un document donné : ce que l'OCR a lu, puis la valeur retenue après vérification.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `document_id` | `int NOT NULL FK` | Document, référence `DOCUMENT.id` |
| `field_spec_id` | `int NOT NULL FK` | Champ du schéma, référence `FIELD_SPEC.id` |
| `group_id` | `varchar nullable` | Ligne de tableau, ex. `pret_1` ; vide pour un champ isolé |
| `ocr_value` | `varchar nullable` | Valeur lue par l'OCR au préremplissage |
| `resolved_value` | `varchar nullable` | Valeur retenue, mise à jour à chaque vérification |
| `status` | `varchar NOT NULL default 'PENDING'` | `PENDING`, `CORRECTED`, `VALIDATED`, `DISPUTED` |
| `ocr_confidence` | `float nullable` | Confiance de l'OCR, entre 0 et 1 |
| `consensus_reached` | `boolean NOT NULL default false` | Les opérateurs sont d'accord sur ce champ |
| `ocr_polygon` | `float[] nullable` | Zone lue par l'OCR : 4 points, soit 8 nombres |
| `resolved_by` | `varchar nullable` | Origine de la valeur retenue : identifiant de la proposition, ou `ocr_system` |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

*Unicité sur `(document_id, field_spec_id, group_id)`, et sur `(document_id, field_spec_id)` pour un champ sans ligne de tableau.*

---

## Module : Labellisation

### 14. Table JOB

*Une tâche de vérification : un opérateur vérifie un document, à une étape donnée.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `dataset_id` | `int NOT NULL FK` | Lot, référence `DATASET.id` |
| `document_id` | `int NOT NULL FK` | Document à vérifier, référence `DOCUMENT.id` |
| `agent_id` | `int NOT NULL FK` | Opérateur, référence `USER.id` |
| `state` | `varchar NOT NULL default 'ASSIGNED'` | `ASSIGNED`, `IN_PROGRESS`, `SUBMITTED`, `CANCELLED` |
| `step` | `varchar NOT NULL default 'VALIDATION'` | `VALIDATION`, `CORRECTION`, `CONSENSUS` |
| `started_at` | `timestamptz NOT NULL` | Début de la tâche |
| `submitted_at` | `timestamptz nullable` | Date de soumission |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

---

### 15. Table FIELD_PROPOSAL

*La valeur proposée par un opérateur pour un champ, pendant une tâche. C'est l'historique des vérifications : rien n'y est effacé.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `document_field_id` | `int NOT NULL FK` | Champ du document, référence `DOCUMENT_FIELD.id` |
| `job_id` | `int NOT NULL FK` | Tâche, référence `JOB.id` |
| `step` | `varchar NOT NULL default 'VALIDATION'` | Étape de la proposition |
| `value_type` | `varchar NOT NULL default 'TEXT'` | `TEXT`, `NUMBER`, `DATE`, `DATETIME`, `BOOLEAN` |
| `value` | `varchar nullable` | Valeur proposée ; vide si l'opérateur juge le champ vide |
| `reason` | `text nullable` | Justification facultative d'une correction |
| `created_at` | `timestamptz NOT NULL` | Date de la proposition |

---

## Module : Tests de qualité OCR

*Ces tables servent à mesurer la qualité de la lecture : l'IA relit des documents déjà vérifiés par des agents, et l'outil compare les deux réponses.*

### 16. Table DATASET_EXPORT

*Une copie figée d'une liste de documents vérifiés. Les tests se font toujours sur un export, pour que deux tests portent exactement sur les mêmes documents.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `dataset_id` | `int NOT NULL FK` | Lot d'origine, référence `DATASET.id` |
| `schema_id` | `int NOT NULL FK` | Schéma au moment de l'export, référence `DOC_SCHEMA.id` |
| `schema_hash` | `varchar NOT NULL` | Empreinte du schéma : révèle s'il a changé depuis l'export |
| `name` | `varchar NOT NULL` | Nom de l'export |
| `description` | `text nullable` | Description libre |
| `document_ids` | `int[] NOT NULL` | Documents de l'export |
| `verite_empreintes` | `jsonb nullable` | Empreinte de la vérification humaine, document par document : révèle une correction faite après l'export, sans copier les valeurs |
| `created_by_user_id` | `int NOT NULL FK` | Auteur, référence `USER.id` |
| `created_at` | `timestamptz NOT NULL` | Date de l'export |

*Unicité sur `(dataset_id, name)`.*

---

### 17. Table TEST_RECIPE

*Une recette de test : quels documents relire, avec quel moteur OCR, quels modèles et quelle consigne. Une recette verrouillée ne change plus ; pour la modifier, on crée une nouvelle version.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `dataset_id` | `int NOT NULL FK` | Lot, référence `DATASET.id` |
| `dataset_export_id` | `int nullable FK` | Export utilisé, référence `DATASET_EXPORT.id` |
| `tout_l_export` | `boolean NOT NULL default false` | La recette prend tous les documents de l'export |
| `name` | `varchar NOT NULL` | Nom de la recette |
| `description` | `text nullable` | Description libre |
| `version` | `int NOT NULL default 1` | Version de la recette |
| `recette_racine_id` | `int nullable FK` | Première version de la recette, référence `TEST_RECIPE.id` |
| `document_ids` | `int[] NOT NULL` | Documents testés |
| `status` | `varchar NOT NULL default 'DRAFT'` | `DRAFT` (modifiable), `LOCKED` (figée, requise pour lancer un test), `ARCHIVED` |
| `config` | `jsonb NOT NULL default '{}'` | Moteur OCR (fournisseur, modèles, consigne) et seuils |
| `locked_at` | `timestamptz nullable` | Date de verrouillage |
| `created_by_user_id` | `int NOT NULL FK` | Auteur, référence `USER.id` |
| `created_at` | `timestamptz NOT NULL` | Date de création |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

*Unicité sur `(dataset_id, name, version)`.*

---

### 18. Table TEST_EXECUTION

*Une exécution d'une recette : son état, ses compteurs et les empreintes qui permettent de savoir si deux exécutions sont comparables.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `recipe_id` | `int NOT NULL FK` | Recette exécutée, référence `TEST_RECIPE.id` |
| `status` | `varchar NOT NULL default 'PENDING'` | `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED` |
| `ocr_provider` | `varchar NOT NULL` | Moteur OCR utilisé |
| `ocr_model_id` | `varchar nullable` | Modèle OCR utilisé |
| `error_message` | `text nullable` | Cause de l'échec, le cas échéant |
| `comparateur_version` | `varchar nullable` | Version des règles de comparaison |
| `schema_hash` | `varchar nullable` | Empreinte du schéma utilisé |
| `verite_hash` | `varchar nullable` | Empreinte de la vérification humaine utilisée |
| `documents_compared` | `int NOT NULL default 0` | Documents comparés |
| `documents_traites` | `int NOT NULL default 0` | Documents traités, pour suivre l'avancement |
| `fields_compared` | `int NOT NULL default 0` | Champs comparés |
| `fields_human_verified` | `int NOT NULL default 0` | Champs vérifiés par un humain |
| `diff_count` | `int NOT NULL default 0` | Nombre d'écarts |
| `unexpected_count` | `int NOT NULL default 0` | Valeurs lues sur des champs absents du schéma |
| `ocr_calls_made` | `int NOT NULL default 0` | Appels au moteur OCR |
| `pages_processed` | `int NOT NULL default 0` | Pages traitées |
| `confidence_histogram` | `jsonb nullable` | Répartition de la confiance OCR, chez les valeurs justes et chez les fausses |
| `created_by_user_id` | `int NOT NULL FK` | Auteur, référence `USER.id` |
| `created_at` | `timestamptz NOT NULL` | Date de création |
| `started_at` | `timestamptz nullable` | Début de l'exécution |
| `finished_at` | `timestamptz nullable` | Fin de l'exécution |
| `updated_at` | `timestamptz NOT NULL` | Date de dernière modification |

---

### 19. Table COMPARISON_RESULT

*Un écart entre la lecture de l'IA et la vérification humaine, pour un champ. Les champs justes ne produisent pas de ligne.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `bigserial PK` | Identifiant auto-incrémenté |
| `execution_id` | `int NOT NULL FK` | Exécution, référence `TEST_EXECUTION.id` |
| `document_field_id` | `int NOT NULL FK` | Champ du document, référence `DOCUMENT_FIELD.id` |
| `verdict` | `varchar NOT NULL` | `MISSING` (l'IA n'a rien lu) ou `WRONG` (l'IA a lu autre chose) |
| `diff_kind` | `varchar nullable` | Nature d'une erreur `WRONG` : `CASE` (majuscules), `WHITESPACE` (espaces), `DIGIT` (chiffres), `FORMAT`, `TOTAL` |
| `ocr_confidence` | `float nullable` | Confiance de l'OCR sur cette valeur |
| `expected_value` | `varchar nullable` | Valeur attendue ; vide pour un champ sensible |
| `observed_value` | `varchar nullable` | Valeur lue ; vide pour un champ sensible |
| `observed_hmac` | `varchar nullable` | Empreinte chiffrée de la valeur lue : repère une erreur qui se répète sans révéler la valeur |
| `edit_distance` | `int nullable` | Nombre de caractères à changer pour passer de la valeur lue à la valeur attendue |
| `created_at` | `timestamptz NOT NULL` | Date de création |

*Unicité sur `(execution_id, document_field_id)`.*

---

### 20. Table EVALUATION_REPORT

*Les compteurs d'une exécution, champ par champ. Ce sont eux qui alimentent la page des métriques et le rapport PDF.*

| Colonne | Type | Détail |
| --- | --- | --- |
| `id` | `serial PK` | Identifiant auto-incrémenté |
| `execution_id` | `int NOT NULL FK` | Exécution, référence `TEST_EXECUTION.id` |
| `field_spec_id` | `int NOT NULL FK` | Champ du schéma, référence `FIELD_SPEC.id` |
| `field_key` | `varchar NOT NULL` | Clé du champ |
| `compared` | `int NOT NULL` | Valeurs comparées |
| `diff_count` | `int NOT NULL` | Écarts |
| `vp` | `int NOT NULL default 0` | Valeurs justes (vrais positifs) |
| `fp` | `int NOT NULL default 0` | Valeurs inventées : l'IA lit une valeur là où il n'y a rien (faux positifs) |
| `fn` | `int NOT NULL default 0` | Valeurs manquées (faux négatifs) |
| `vn` | `int NOT NULL default 0` | Champs vides des deux côtés (vrais négatifs) |
| `substitutions` | `int NOT NULL default 0` | Valeurs lues mais fausses |
| `somme_distance` | `int NOT NULL default 0` | Total des caractères erronés, pour le taux d'erreur par caractère |
| `somme_longueur_attendue` | `int NOT NULL default 0` | Total des caractères attendus |
| `page` | `int nullable` | Page du champ, pour les filtres |
| `section_id` | `varchar nullable` | Rubrique du champ, pour les filtres |
| `value_type` | `varchar nullable` | Type du champ, pour les filtres |
| `sensitive` | `boolean NOT NULL default false` | Champ sensible |

*Unicité sur `(execution_id, field_spec_id)`.*

---

## Changements par rapport à la version précédente

* **USER_ORGANISATION supprimée.** Un utilisateur appartient à une seule organisation, via `USER.organisation_id`.
* **Rôles.** Les rôles de projet sont `OPERATOR` et `BUSINESS_ADMIN`, au lieu de `operator`, `supervisor` et `admin`. Les rôles transverses sont passés sur `USER.platform_role` : `NOTA_SUPERVISOR`, `NOTA_ADMIN`, `NOTA_CLIENT`.
* **PROJECT.** Plus de `doc_schema_id` : c'est le schéma qui pointe vers son projet, et le lot (DATASET) qui fixe le schéma. Le statut `suspended` n'existe plus.
* **Nouvelles tables :** SCHEMA_PAGE, DOCUMENT_PROGRESS, et tout le module Tests de qualité OCR (DATASET_EXPORT, TEST_RECIPE, TEST_EXECUTION, COMPARISON_RESULT, EVALUATION_REPORT).
* **Nouvelles colonnes :** `DATASET.expected_page_count`, `FIELD_SPEC.sensitive` (anciennement `is_sensitive`) et `FIELD_SPEC.display_order`, `DOCUMENT_FIELD.consensus_reached`.
