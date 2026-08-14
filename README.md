# ADAM - Annotation et Données Automatisées

uv run python -c "import base64; t=open(r'C:\DEV\fbi-mock\token.txt').read().strip(); p=t.split('.')[1]; p+='='*(-len(p)%4); print(base64.urlsafe_b64decode(p).decode())"
