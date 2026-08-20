# ADAM - Annotation et Données Automatisées

-- 1. la colonne est là    
SELECT column_name FROM information_schema.columns    
WHERE table_name = 'field_spec' AND column_name = 'is_sensitive';    
    
-- 2. les 4 tables sont complètes (échantillon : les colonnes sensibles des écarts)    
SELECT column_name FROM information_schema.columns    
WHERE table_name = 'comparison_result'    
ORDER BY ordinal_position;  
