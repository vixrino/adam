<#
.SYNOPSIS
    Runs Python formatting, linting, security checks, and tests in the optimal order.
#>

$ErrorActionPreference = "Stop"
$UseUv = $null -ne (Get-Command uv -ErrorAction SilentlyContinue)

function Invoke-Check {
    param (
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Running: $Name" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan

    # Execute the command
    & $Command

    # Check the exit code of the Python process
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n[X] ERROR: $Name failed with exit code $LASTEXITCODE." -ForegroundColor Red
        Write-Host "Aborting subsequent checks.`n" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    Write-Host "[OK] $Name completed successfully.`n" -ForegroundColor Green
}

function Invoke-Module {
    param (
        [string]$Name,
        [string[]]$Arguments
    )

    Invoke-Check $Name {
        if ($UseUv) {
            & uv run @Arguments
        }
        else {
            & python -m @Arguments
        }
    }
}

if ($UseUv) {
    Write-Host "Using uv environment" -ForegroundColor Green
}
else {
    Write-Host "Using Python/pip environment" -ForegroundColor Yellow
}

Invoke-Check "Project sync" {
    if ($UseUv) {
        uv sync > $null 2>&1
    }
    else {
        python -m pip install -e . > $null 2>&1
    }
}

# 0. Sync requirements.txt / requirements.dev.txt with pyproject.toml
Invoke-Check "Export requirements files" {
    if ($UseUv) {
        uv run scripts\export_requirements.py
    }
    else {
        python scripts\export_requirements.py
    }
}

# 1. Format code
Invoke-Module "black (Code Formatting)" @(
    "black",
    "src\"
)

# 2. Format imports
Invoke-Module "isort (Import Sorting)" @(
    "isort",
    "src\"
)

# 3. Linting
Invoke-Module "pylint (Code Linting)" @(
    "pylint",
    ".\src\"
)

# 4. Static type checking
Invoke-Module "mypy (Type Checking)" @(
    "mypy",
    "src\",
    "--strict",
    "--ignore-missing-imports"
)

# 5. Security Scanning
Invoke-Module "bandit (Security Scan)" @(
    "bandit",
    "-ll",
    "-r",
    "src\"
)

# 6. Unit Tests & Coverage
Invoke-Module "pytest (Tests & Coverage)" @(
    "pytest",
    "-p",
    "no:cacheprovider",
    "--cov=.",
    "--cov-report=term-missing"
)

Write-Host "========================================" -ForegroundColor Green
Write-Host "All checks passed successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green