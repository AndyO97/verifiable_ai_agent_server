#!/usr/bin/env pwsh
# Setup script for Windows PowerShell
# Initializes the development environment for the verifiable AI agent server
# Uses uv for dependency management (faster, more reliable than pip/poetry)

Write-Host "🔐 Verifiable AI Agent Server - Development Setup" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "Checking Python 3.11+..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($pythonVersion -match "3\.(1[1-9]|[2-9]\d)") {
    Write-Host "✓ Python $pythonVersion found" -ForegroundColor Green
} else {
    Write-Host "✗ Python 3.11+ required. Found: $pythonVersion" -ForegroundColor Red
    exit 1
}

# Check/Install uv
Write-Host "Checking uv package manager..." -ForegroundColor Yellow
$uv = uv --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ $uv found" -ForegroundColor Green
} else {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    pip install uv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Failed to install uv" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ uv installed" -ForegroundColor Green
}

# Create virtual environment with uv
Write-Host ""
Write-Host "Setting up virtual environment with uv..." -ForegroundColor Yellow
uv venv

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Failed to create virtual environment" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Virtual environment created" -ForegroundColor Green

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

# Install dependencies using uv
Write-Host ""
Write-Host "Installing dependencies with uv..." -ForegroundColor Yellow
uv pip install -e ".[dev]"

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Failed to install dependencies" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Dependencies installed" -ForegroundColor Green

# Create .env file if not exists
if (!(Test-Path ".env")) {
    Write-Host ""
    Write-Host "Creating .env template..." -ForegroundColor Yellow
    
    $envContent = @"
# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DATABASE=verifiable_agent

# OpenTelemetry Configuration
OTEL_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=verifiable-ai-agent

# Langfuse Configuration (configure after deploying Langfuse)
LANGFUSE_API_ENDPOINT=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk_xxxxx
LANGFUSE_SECRET_KEY=sk_xxxxx

# Server Configuration
HOST=0.0.0.0
PORT=8000

# AWS S3 (optional)
# S3_ACCESS_KEY_ID=
# S3_SECRET_ACCESS_KEY=
# S3_BUCKET=verifiable-agent-logs

# Environment
ENVIRONMENT=development
DEBUG=true
"@
    
    Set-Content -Path ".env" -Value $envContent
    Write-Host "✓ Created .env file (update with your credentials)" -ForegroundColor Green
}

# Run tests
Write-Host ""
Write-Host "Running tests..." -ForegroundColor Yellow
python -m pytest tests/ -v --tb=short

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Setup complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Update .env with your PostgreSQL and Langfuse credentials"
    Write-Host "2. Review README.md for architecture and usage"
    Write-Host "3. Run example: python examples/basic_run.py"
    Write-Host ""
    Write-Host "Development commands:" -ForegroundColor Cyan
    Write-Host "  python -m pytest tests/ -v          - Run all tests"
    Write-Host "  ruff check src/                     - Lint code"
    Write-Host "  mypy src/                           - Type checking"
    Write-Host "  black src/ tests/                   - Format code"
    Write-Host "  python -m src.tools.verify_cli --help  - Verification CLI"
    Write-Host ""
    Write-Host "Virtual environment info:" -ForegroundColor Cyan
    Write-Host "  Activate:   .\venv\Scripts\Activate.ps1"
    Write-Host "  Deactivate: deactivate"
} else {
    Write-Host ""
    Write-Host "❌ Tests failed. Fix issues above." -ForegroundColor Red
    exit 1
}

