#!/usr/bin/env pwsh
# deploy.ps1 - Clean deploy script for Vidtory-Agent
# Usage:
#   .\deploy.ps1          -> restart with current images (no rebuild)
#   .\deploy.ps1 --build  -> rebuild images then restart

param(
    [switch]$Build = $false
)

Write-Host "🛑 Stopping existing containers..." -ForegroundColor Yellow
docker-compose down 2>&1 | Out-Null
Write-Host "  ✓ Containers stopped and removed" -ForegroundColor Gray

if ($Build) {
    Write-Host "🔨 Building new images..." -ForegroundColor Cyan
    docker-compose build 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Build failed." -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ Images built" -ForegroundColor Gray
}

Write-Host "🚀 Starting containers..." -ForegroundColor Cyan
docker-compose up -d 2>&1

Start-Sleep -Seconds 3
Write-Host ""
$running = docker ps --filter "name=vidtoryagent" --format "{{.Names}}: {{.Status}}" 2>&1
if ($running) {
    Write-Host "✅ Containers running:" -ForegroundColor Green
    $running | ForEach-Object { Write-Host "   $_" -ForegroundColor White }
} else {
    Write-Host "❌ No containers running — check logs with: docker logs vidtoryagent-gateway" -ForegroundColor Red
    exit 1
}
