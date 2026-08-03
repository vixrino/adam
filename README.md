# ADAM - Annotation et Données Automatisées
SELECT u.matricule, u.organisation_id, u.platform_role, up.project_id, up.role
FROM "user" u
LEFT JOIN user_project up ON up.user_id = u.id
ORDER BY u.matricule;
