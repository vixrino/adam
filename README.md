# ADAM - Annotation et Données Automatisées


function Get-Sub($t){ $p=$t.Split('.')[1].Replace('-','+').Replace('_','/'); while($p.Length%4){$p+='='}; ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($p)) | ConvertFrom-Json).sub }
Get-Sub $op
Get-Sub $ba
