# ADAM - Annotation et Données Automatisées
1. La colonne platform_role existe bien

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'user' AND column_name = 'platform_role';

Attendu : une ligne, platform_role | character varying | YES. Zéro ligne = la migration n'est pas passée.

2. L'index a été créé

SELECT indexname FROM pg_indexes
WHERE tablename = 'user' AND indexname = 'ix_user_platform_role';

Attendu : une ligne.

3. Les rôles de projet ont été convertis

SELECT role, count(*) FROM user_project GROUP BY role ORDER BY role;

Attendu : uniquement OPERATOR et/ou BUSINESS_ADMIN. Tout ADMIN ou SUPERVISOR restant signale une conversion incomplète.

4. Les superviseurs ont bien basculé en rôle de plateforme

SELECT platform_role, count(*) FROM "user" GROUP BY platform_role ORDER BY platform_role;

Attendu : une ligne NULL pour les utilisateurs purement métier, plus une ligne NOTA_SUPERVISOR s'il y avait des superviseurs avant migration. Les guillemets doubles autour de "user" sont obligatoires, c'est un mot réservé.

5. Contrôle croisé — plus aucune adhésion pour les comptes plateforme

SELECT u.id, u.platform_role, count(up.user_id) AS adhesions
FROM "user" u
LEFT JOIN user_project up ON up.user_id = u.id
WHERE u.platform_role IS NOT NULL
GROUP BY u.id, u.platform_role;
