
SELECT pg_terminate_backend(pid)  
FROM pg_stat_activity  
WHERE datname = 'nota_db_demo_metriques' AND pid <> pg_backend_pid();  
  
DROP DATABASE nota_db_demo_metriques;  
