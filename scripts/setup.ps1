# 1. Extraire uniquement le MATRICULE
$whoami_output = whoami
# whoami donne "DOMAINE\MATRICULE_YYYY". On coupe au '\' et on prend la partie droite.
$user_id_full = $whoami_output.Split('\')[1] 
# Ensuite, on coupe au '_' et on garde la partie gauche (la MATRICULE pur).
$user_id = $user_id_full.Split('_')[0]

# 2. Construire le chemin exact vers les scripts Python 3.12
$python_scripts_path = "C:\Users\$user_id\AppData\Roaming\Python\Python312\Scripts"

# 3. Vérifier l'existence du dossier ET protéger le PATH contre les doublons
if (Test-Path $python_scripts_path) {
    
    # On transforme le PATH actuel en un tableau (liste) pour chercher précisément le chemin
    $path_array = $env:PATH -split ';'
    
    if ($path_array -notcontains $python_scripts_path) {
        Write-Host "-> Ajout de $python_scripts_path au PATH..." -ForegroundColor Green
        $env:PATH += ";$python_scripts_path"
    } else {
        Write-Host "-> Le chemin est déjà dans le PATH. On ignore l'ajout." -ForegroundColor Gray
    }

} else {
    Write-Host "-> Attention : Le dossier $python_scripts_path n'existe pas." -ForegroundColor Yellow
}

# 4. Lancer la synchronisation uv avec les certificats système
Write-Host "-> Exécution de 'uv sync --system-certs'..." -ForegroundColor Cyan
uv sync --system-certs 