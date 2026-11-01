[CmdletBinding()]
param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    if (-not (Test-Path ".venv")) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败，请用 -Python 指定有效解释器。" }
    }
    $py = Join-Path $repo ".venv\Scripts\python.exe"
    & $py -m pip install -r requirements\dev.txt
    if ($LASTEXITCODE -ne 0) { throw "安装依赖失败" }
    if (-not (Test-Path ".env")) {
        Copy-Item -LiteralPath ".env.example" -Destination ".env"
        & $py -c "import secrets; from dotenv import set_key; set_key('.env','DJANGO_SECRET_KEY',secrets.token_urlsafe(50))"
        if ($LASTEXITCODE -ne 0) { throw "生成本机密钥失败" }
    }
    & $py manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw "数据库迁移失败" }
    Write-Host "下一步：填写 .env 模型/预算；运行 python manage.py createsuperuser；管理后台配置 PricePlan。"
    Write-Host "后端：.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload"
    Write-Host "前端：cd frontend 后执行 npm ci 与 npm run dev"
} finally { Pop-Location }
