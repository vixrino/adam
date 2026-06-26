<#
.SYNOPSIS
    Runs Python formatting, linting, security checks, and tests.
#>

$ErrorActionPreference = "Stop"

Function Invoke-Check {
    param (
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host "Running: $Name" -ForegroundColor Yellow
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] ERROR: $Name failed" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "[OK] $Name completed" -ForegroundColor Green
}

Invoke-Check "isort" { python -m isort src/ }
Invoke-Check "black" { python -m black src/ }
Invoke-Check "mypy" { python -m mypy src/ --ignore-missing-imports }
Invoke-Check "pylint" { python -m pylint src/adam_core src/adam_api }
Invoke-Check "bandit" { python -m bandit -ll -r src/ }
Invoke-Check "pytest" { python -m pytest --cov=src --cov-report=term-missing }

Write-Host "All checks passed!" -ForegroundColor Green
