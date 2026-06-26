$version = "5.17.14"
$base = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@$version"
$out = "src/adam_api/static"

New-Item -ItemType Directory -Force -Path $out
Invoke-WebRequest "$base/swagger-ui-bundle.js" -OutFile "$out/swagger-ui-bundle.js"
Invoke-WebRequest "$base/swagger-ui.css"        -OutFile "$out/swagger-ui.css"

Write-Host "Swagger UI $version telecharge" -ForegroundColor Green
