Clear-Content .\app.log

Get-Content .\app.log -Wait |
ForEach-Object {

    $line = $_

    if ($line -match 'ERROR|CRITICAL|FATAL') {
        Write-Host $line -ForegroundColor Red
    }
    elseif ($line -match 'Exception|Traceback') {
        Write-Host $line -ForegroundColor Magenta
    }
    elseif ($line -match 'WARN|WARNING') {
        Write-Host $line -ForegroundColor Yellow
    }
    elseif ($line -match '\[INFO\]') {
        Write-Host $line -ForegroundColor Green
    }
    elseif ($line -match '\[api\]') {
        Write-Host $line -ForegroundColor Cyan
    }
    elseif ($line -match '\[worker\]') {
        Write-Host $line -ForegroundColor DarkGray
    }
    else {
        Write-Host $line
    }
}