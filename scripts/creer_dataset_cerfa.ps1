# scripts/creer_dataset_cerfa.ps1
# Cree le dataset CERFA dans le projet dgser (fiche de passation, etape 2.2).
# Le dataset nait en DRAFT et passe ACTIVE a l'ajout des premiers PDF.
#
# Usage, depuis C:\DEV\nota-back, API demarree :
#   powershell -ExecutionPolicy Bypass -File scripts\creer_dataset_cerfa.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\creer_dataset_cerfa.ps1 -ProjectId 4 -SchemaId 2

param(
    [string]$Api = "http://localhost:8001/api/v1",
    [int]$ProjectId = 4,
    [int]$SchemaId = 2,
    [string]$Name = "CERFA surendettement"
)

$ErrorActionPreference = "Stop"

$body = @{
    project_id          = $ProjectId
    schema_id           = $SchemaId
    name                = $Name
    ocr_provider        = "MISTRAL"
    required_operators  = 2
    expected_page_count = 12
} | ConvertTo-Json

$dataset = Invoke-RestMethod "$Api/datasets" -Method Post -ContentType "application/json" -Body $body
$dataset | Format-List id, name, status, project_id, schema_id
