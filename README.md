# ADAM - Annotation et Données Automatisées

$pid8000 = (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess
Get-Process -Id $pid8000 | Select-Object Id, ProcessName, StartTime

