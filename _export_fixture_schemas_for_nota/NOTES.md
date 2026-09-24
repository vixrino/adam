# Correctif de la fixture de test des schemas, pour NOTA

Ne PAS remplacer tests/unit/test_router_schemas.py en entier : NOTA rend 409
sur le verrou de schema la ou ADAM rend 423, un remplacement integral casserait
les assertions. Deux blocs seulement sont a porter, ils sont dans
fixture_mock_db.py.

## Le diagnostic

Douze tests echouaient, dont neuf en 409 sur /schemas/1/field-specs. Le detail
de la reponse le disait :

    Schema 1 verrouille. Creer une nouvelle version (POST /schemas/1/duplicate)

Ce n'est ni la contrainte d'unicite, ni une regle metier absente : c'est le
bouchon. La fixture mock_db de NOTA ne bouchonne qu'une partie des accesseurs
de resultat SQLAlchemy. Un accesseur oublie rend un MagicMock, et un MagicMock
est vrai : la route qui cherche un dataset actif pour verifier le verrou croit
en trouver un, et refuse. Les trois JSONDecodeError ont la meme origine — la
route leve, la reponse n'a pas de corps.

## Les deux blocs

1. La fixture mock_db bouchonne TOUS les accesseurs, y compris ceux qu'aucune
   route n'utilise aujourd'hui. C'est deliberé : la prochaine route qui lira
   .first() ou .scalar() ne fera pas reapparaitre la panne.

2. Le helper _unlocked_db, a appeler en debut des tests qui modifient un
   schema — add, patch, delete de field-specs — pour poser explicitement
   « schema non verrouille, aucun document_field referencant » :

       def test_returns_201(self, client, mock_db) -> None:
           _unlocked_db(mock_db)
           ...

   Les tests qui verifient le verrou lui-meme ne l'appellent pas, evidemment :
   ils ont besoin que le dataset actif soit trouve.

## Hors perimetre

test_router_documents.py::test_ocr_polygon_persisted_and_returned n'existe pas
dans ADAM : ce test est propre a NOTA, je ne peux pas dire d'ici si c'est le
test ou la route PATCH /documents qui est en cause. A regarder separement,
une fois les onze autres verts.

## Verification

    uv run pytest tests/unit/test_router_schemas.py -v

---

# Mise a jour : les neuf 409 restants

Apres le retablissement du `return db`, trente tests repassent et il en reste
neuf, tous en 409 sur add / patch / delete de field-specs. `_unlocked_db` dans
sa premiere forme ne pouvait rien pour eux.

## Ce que dit le message

    {"detail": "Doc_schema : Schema 1 verrouille. Creer une nouvelle version
                (POST /schemas/1/duplicate) pour reprendre l'edition."}

Le prefixe « Doc_schema : » vient de `raise_conflict(DocSchema, ...)` :
`_name()` lit `__tablename__`, soit `doc_schema`, et le capitalise
(nota_core/utils/exceptions.py). Le verrou de NOTA fait donc la meme chose
que celui d'ADAM, en 409 la ou ADAM rend 423.

## La cause

Le test pose UN bouchon que DEUX requetes consomment : la verification du
verrou d'abord, la recuperation du schema ensuite. La premiere voit l'objet
destine a la seconde, le trouve vrai, et conclut au verrou.

## Le correctif

unlocked_db.py, a cote de cette note, remplace integralement le helper. Il
traite le premier execute() a part — celui du verrou, qui ne doit rien
trouver — et laisse les suivants retomber sur le bouchon de la fixture.

Le patron vient d'un test d'ADAM qui affronte le meme enchainement,
test_409_when_referenced_by_document_field, ou le commentaire dit
explicitement « premier execute : lock check ».

## Reserve

Ce correctif n'a pas pu etre execute : le routeur de NOTA n'existe pas dans
ADAM, et c'est lui qui decide du nombre de requetes avant celle du schema. Si
le verrou de NOTA en fait deux plutot qu'une, il faudra etendre `not_locked`
aux deux premiers appels — la forme du helper ne change pas, seule la
condition `calls["n"] == 1` devient `<= 2`.
