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
