# ADAM - Annotation et Données Automatisées

SELECT u.matricule, up.role, p.name 
FROM "user" u 
JOIN user_project up ON up.user_id = u.id 
JOIN project p ON p.id = up.project_id 
ORDER BY u.matricule; 
