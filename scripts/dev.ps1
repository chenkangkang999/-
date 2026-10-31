[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    & .\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
}
finally { Pop-Location }