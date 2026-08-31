"""Enumerations roles utilisateur.

Le RACI NOTA distingue quatre acteurs humains qui ne se rattachent pas au meme
niveau. Deux enumerations les separent donc, plutot qu'une seule ou les valeurs
ne seraient pas comparables entre elles.

Roles de projet (table ``user_project``)
----------------------------------------
    OPERATOR        Operateur Metier : annote, corrige l'OCR, participe au
                    consensus. Aucune lecture transverse.
    BUSINESS_ADMIN  Administrateur Metier : affecte les documents, supervise
                    les workflows de validation, arbitre les divergences de
                    consensus, gere les projets ou il est inscrit.

Un utilisateur peut porter un role different selon le projet, ce qui autorise
plusieurs administrateurs metier sur des perimetres distincts.

Roles de plateforme (colonne ``user.platform_role``)
----------------------------------------------------
    NOTA_SUPERVISOR Superviseur NOTA : datasets de reference, recettes de
                    tests, campagnes, rapports, export, verrouillage.
    NOTA_ADMIN      Administrateur NOTA : organisations, utilisateurs et
                    droits, configuration de la plateforme, schemas JSON.

Ces deux roles sont transverses : ils n'ont pas de sens rattaches a un projet
donne, et ils franchissent la frontiere d'organisation. La docstring de
``adam_api.dependencies.db`` en tire les consequences sur le filtrage.

Pourquoi l'ancien UserRole a disparu
------------------------------------
UserRole valait {OPERATOR, SUPERVISOR, ADMIN}. Sa valeur ADMIN recouvrait a la
fois l'Administrateur Metier et l'Administrateur NOTA, dont le RACI oppose les
responsabilites : administrer les utilisateurs et droits est R pour le second et
I pour le premier, affecter les taches aux operateurs est l'inverse. Les
confondre revenait a accorder a chacun les droits de l'autre. SUPERVISOR, de son
cote, etait stocke sur une adhesion a un projet alors qu'il designe un role
transverse, ce qui obligeait a inscrire un superviseur dans chaque projet.
"""

from enum import Enum


class ProjectRole(str, Enum):
    """Role d'un utilisateur au sein d'un projet donne."""

    OPERATOR = "OPERATOR"
    BUSINESS_ADMIN = "BUSINESS_ADMIN"


class PlatformRole(str, Enum):
    """Role transverse, independant de tout projet et de toute organisation."""

    NOTA_SUPERVISOR = "NOTA_SUPERVISOR"
    NOTA_ADMIN = "NOTA_ADMIN"


#: Valeurs des roles de plateforme, pour les tests d'appartenance.
PLATFORM_ROLE_VALUES = frozenset(role.value for role in PlatformRole)


class ExportFormat(str, Enum):
    """Format d'export dataset."""

    JSON = "JSON"
    CSV = "CSV"
    PDF = "PDF"
