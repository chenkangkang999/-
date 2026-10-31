<#
.SYNOPSIS
  一键初始化本地开发环境（Windows）。
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
#>
[CmdletBinding()]
param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    if (-not (Test-Path ".venv")) {
        & $Python -m venv .venv
    }
    $py = Join-Path $repo ".venv\Scripts\python.exe"
    & $py -m pip install --upgrade pip
    & $py -m pip install -r requirements\dev.txt
    if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
    & $py manage.py migrate
    Write-Host "`n初始化完成。启动开发服务器：" -ForegroundColor Green
    Write-Host "  .\.venv\Scripts\python.exe manage.py runserver"
    Write-Host "前端：cd frontend; npm install; npm run dev"
}
finally { Pop-Location }