# ADAM - Annotation et Données Automatisées

cd C:\DEV\nota-back        
git status                                  # vérifie ce qui a bougé
git add src/adam_api/dependencies/auth.py src/adam_api/core/config.py .env.template conf src/adam_api/core/security.py src/adam_api/main.py tests/unit/test_resolve_caller.py tests/unit/test_jwt_middleware.py        
git commit -m "feat(auth): raccorde l'API a FBI via exa-pie        
        
Le UserCaller ecrit en dur disparait. Le token valide par exa-pie fournit le
matricule, la base fournit l'organisation et le role de plateforme : FBI
authentifie, l'application autorise.

Verifie de bout en bout contre le mock FBI 2.0.6 : sans token 400, un OPERATOR
voit son projet seul, un BUSINESS_ADMIN les deux de son organisation."

