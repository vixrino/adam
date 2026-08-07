# ADAM - Annotation et Données Automatisées


SELECT document_id, field_spec_id, group_id, count(*)
FROM document_field
GROUP BY document_id, field_spec_id, group_id
HAVING count(*) > 1;
