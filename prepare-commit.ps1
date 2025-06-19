#!/usr/bin/env pwsh

# FedLoad - Commit Preparation Script (PowerShell)
# This script helps prepare for a major commit by checking project status

# Exit on any error
$ErrorActionPreference = "Stop"

Write-Host "🚀 FedLoad - Commit Preparation Script" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# Function to print colored output
function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Check if we're in the right directory
if (-not (Test-Path "main.py") -or -not (Test-Path "scheduler.py")) {
    Write-Error "This script must be run from the FedLoad project root directory"
    exit 1
}

Write-Status "Checking project status..."

# 1. Check Git status
Write-Host ""
Write-Host "📋 Git Status:" -ForegroundColor Cyan
Write-Host "==============" -ForegroundColor Cyan
git status --porcelain

# Count changes
$gitStatus = git status --porcelain
$MODIFIED = ($gitStatus | Select-String "^ M" | Measure-Object).Count
$ADDED = ($gitStatus | Select-String "^A" | Measure-Object).Count
$DELETED = ($gitStatus | Select-String "^D" | Measure-Object).Count
$UNTRACKED = ($gitStatus | Select-String "^??" | Measure-Object).Count

Write-Host ""
Write-Status "Changes summary:"
Write-Host "  Modified files: $MODIFIED"
Write-Host "  Added files: $ADDED"
Write-Host "  Deleted files: $DELETED"
Write-Host "  Untracked files: $UNTRACKED"

# 2. Check if virtual environment is active
Write-Host ""
Write-Host "🐍 Python Environment:" -ForegroundColor Cyan
Write-Host "=====================" -ForegroundColor Cyan
if (-not $env:VIRTUAL_ENV) {
    Write-Warning "Virtual environment not activated"
    Write-Host "  Run: .venv\Scripts\Activate.ps1 (Windows) or source .venv/bin/activate (Linux/Mac)"
} else {
    Write-Success "Virtual environment active: $env:VIRTUAL_ENV"
}

# 3. Check Python version
$PYTHON_VERSION = python --version 2>&1
Write-Status "Python version: $PYTHON_VERSION"

# 4. Run tests
Write-Host ""
Write-Host "🧪 Running Tests:" -ForegroundColor Cyan
Write-Host "================" -ForegroundColor Cyan
if (Get-Command pytest -ErrorAction SilentlyContinue) {
    Write-Status "Running pytest..."
    if (pytest tests/ -v --tb=short) {
        Write-Success "All tests passed!"
    } else {
        Write-Error "Some tests failed. Please fix before committing."
        exit 1
    }
} else {
    Write-Warning "pytest not found. Install with: pip install pytest"
}

# 5. Check linting
Write-Host ""
Write-Host "🔍 Code Quality Check:" -ForegroundColor Cyan
Write-Host "=====================" -ForegroundColor Cyan
if (Get-Command flake8 -ErrorAction SilentlyContinue) {
    Write-Status "Running flake8..."
    if (flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics) {
        Write-Success "No critical linting errors found"
    } else {
        Write-Warning "Linting errors found. Consider fixing before commit."
    }
} else {
    Write-Warning "flake8 not found. Install with: pip install flake8"
}

# 6. Check Docker files
Write-Host ""
Write-Host "🐳 Docker Configuration:" -ForegroundColor Cyan
Write-Host "=======================" -ForegroundColor Cyan
if (Test-Path "Dockerfile") {
    Write-Success "Dockerfile exists"
} else {
    Write-Error "Dockerfile missing"
}

if (Test-Path "docker-compose.yml") {
    Write-Success "docker-compose.yml exists"
} else {
    Write-Error "docker-compose.yml missing"
}

if (Test-Path ".dockerignore") {
    Write-Success ".dockerignore exists"
} else {
    Write-Warning ".dockerignore missing"
}

# 7. Check GitHub Actions
Write-Host ""
Write-Host "⚙️ GitHub Actions:" -ForegroundColor Cyan
Write-Host "==================" -ForegroundColor Cyan
if (Test-Path ".github/workflows/ci-cd.yml") {
    Write-Success "CI/CD workflow exists"
} else {
    Write-Error "CI/CD workflow missing"
}

# 8. Check configuration files
Write-Host ""
Write-Host "⚙️ Configuration Files:" -ForegroundColor Cyan
Write-Host "======================" -ForegroundColor Cyan
$CONFIG_FILES = @("config.json", "fed_entities.json", "tracked_sites.json", "requirements.txt")
foreach ($file in $CONFIG_FILES) {
    if (Test-Path $file) {
        Write-Success "$file exists"
    } else {
        Write-Error "$file missing"
    }
}

# 9. Check for large files that shouldn't be committed
Write-Host ""
Write-Host "📁 Large Files Check:" -ForegroundColor Cyan
Write-Host "====================" -ForegroundColor Cyan
$LARGE_FILES = Get-ChildItem -Recurse -File | Where-Object { $_.Length -gt 1MB -and $_.FullName -notmatch "\.git|\.venv|logs" } | Select-Object -ExpandProperty FullName
if (-not $LARGE_FILES) {
    Write-Success "No large files found"
} else {
    Write-Warning "Large files found (>1MB):"
    $LARGE_FILES | ForEach-Object { Write-Host "  $_" }
    Write-Host "  Consider adding to .gitignore if these are generated files"
}

# 10. Check .gitignore
Write-Host ""
Write-Host "🚫 .gitignore Check:" -ForegroundColor Cyan
Write-Host "===================" -ForegroundColor Cyan
$GITIGNORE_ITEMS = @("logs/", "*.log", "__pycache__/", ".coverage", "change_log.json", "entity_store.json")
foreach ($item in $GITIGNORE_ITEMS) {
    if (Select-String -Path ".gitignore" -Pattern [regex]::Escape($item) -Quiet) {
        Write-Success "$item is ignored"
    } else {
        Write-Warning "$item not in .gitignore"
    }
}

# 11. Security check
Write-Host ""
Write-Host "🔒 Security Check:" -ForegroundColor Cyan
Write-Host "==================" -ForegroundColor Cyan
if (Get-Command bandit -ErrorAction SilentlyContinue) {
    Write-Status "Running bandit security check..."
    if (bandit -r . -f json -o bandit-report.json -q) {
        Write-Success "No high-severity security issues found"
    } else {
        Write-Warning "Security issues found. Check bandit-report.json"
    }
} else {
    Write-Warning "bandit not found. Install with: pip install bandit"
}

# 12. Generate commit message suggestions
Write-Host ""
Write-Host "💬 Suggested Commit Messages:" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host "For major release:"
Write-Host "  feat: major release with Docker support and CI/CD pipeline"
Write-Host ""
Write-Host "For bug fix:"
Write-Host "  fix: resolve critical logger bug causing None attribute errors"
Write-Host ""
Write-Host "For documentation:"
Write-Host "  docs: add comprehensive Docker and GitHub Actions guides"
Write-Host ""
Write-Host "For tests:"
Write-Host "  test: add comprehensive test suite for configuration management"
Write-Host ""

Write-Host "✅ Commit preparation check complete!" -ForegroundColor Green 