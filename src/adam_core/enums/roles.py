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
    NOTA_CLIENT     Client NOTA : commanditaire des travaux de labellisation,
                    consulte l'avancement et les livrables de son organisation.

Porter un role de plateforme et franchir la frontiere d'organisation sont deux
choses distinctes
------------------------------------------------------------------------------
NOTA_SUPERVISOR et NOTA_ADMIN sont transverses : ils n'ont pas de sens rattaches
a un projet donne, et leurs responsabilites — gerer LES organisations, tenir les
datasets de reference de toute la plateforme — deviennent inapplicables sous un
filtre par organisation.

NOTA_CLIENT est l'inverse : c'est precisement un acteur d'une organisation, et
lui ouvrir les autres serait une fuite de donnees entre clients. Il est classe
ici parce qu'il ne se rattache a aucun projet en particulier, pas parce qu'il
serait transverse.

Les deux sets ci-dessous portent cette distinction. ``PLATFORM_ROLE_VALUES``
repond a "ce role vit-il sur ``user.platform_role`` ?", et sert a valider une
valeur ; ``CROSS_ORGANISATION_ROLE_VALUES`` repond a "ce role neutralise-t-il le
filtrage ?", et c'est celui qu'utilise ``adam_api.dependencies.db``. Les
confondre — un seul set derive de l'enumeration entiere — ferait de tout nouveau
role de plateforme un acces total a la plateforme par le seul fait de l'ajouter.

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
    """Role porte par l'utilisateur lui-meme, independant de tout projet.

    Independant d'un projet ne veut pas dire independant d'une organisation :
    NOTA_CLIENT reste enferme dans la sienne (cf. docstring du module).
    """

    NOTA_SUPERVISOR = "NOTA_SUPERVISOR"
    NOTA_ADMIN = "NOTA_ADMIN"
    NOTA_CLIENT = "NOTA_CLIENT"


#: Valeurs admises sur ``user.platform_role``, pour les tests d'appartenance.
PLATFORM_ROLE_VALUES = frozenset(role.value for role in PlatformRole)

#: Roles dont la session s'ouvre sans filtrage : ils traversent organisations et
#: projets. Enumere explicitement, et non derive de PlatformRole : le filtrage
#: reste ainsi ferme par defaut, et ouvrir un nouveau role est un acte delibere.
CROSS_ORGANISATION_ROLE_VALUES = frozenset(
    {
        PlatformRole.NOTA_SUPERVISOR.value,
        PlatformRole.NOTA_ADMIN.value,
    }
)


class ExportFormat(str, Enum):
    """Format d'export dataset."""

    JSON = "JSON"
    CSV = "CSV"
    PDF = "PDF"
