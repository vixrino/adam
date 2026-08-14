# ADAM - Annotation et Données Automatisées

$t = "<colle_le_access_token_ici>"
$p = $t.Split('.')[1].Replace('-','+').Replace('_','/')
while ($p.Length % 4) { $p += '=' }
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($p))
