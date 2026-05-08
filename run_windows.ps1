$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    python -m venv (Join-Path $root ".venv")
}

& $venvPython -m pip install -r (Join-Path $root "requirements.txt")

$env:API_KEY = "devkey"
$env:UI_PASSWORD = "changeme"
$env:SESSION_HOURS = "8"
$env:COOKIE_SECURE = "false"
$env:KEEP_ALIVE = "30m"
$env:OLLAMA_BASE_URL = "http://140.128.103.191:11434"
$env:OLLAMA_TRANS_MODEL = "llama-3.2-3b-instruct-translator-baseline150:q8"
$env:OLLAMA_SUM_MODEL = "llama-3.2-3b-instruct-summarizer-clinical-v4:q8"

Set-Location (Join-Path $root "proxy")
& $venvPython -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload
