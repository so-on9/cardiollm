$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    python -m venv (Join-Path $root ".venv")
}

& $venvPython -m pip install -r (Join-Path $root "requirements.txt")

$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $name, $value = $line -split "=", 2
            [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
        }
    }
}

function Set-EnvDefault($Name, $Value) {
    if (-not [Environment]::GetEnvironmentVariable($Name, "Process")) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

Set-EnvDefault "API_KEY" "replace-with-your-api-key"
Set-EnvDefault "UI_PASSWORD" "replace-with-your-ui-password"
Set-EnvDefault "SESSION_HOURS" "8"
Set-EnvDefault "COOKIE_SECURE" "false"
Set-EnvDefault "KEEP_ALIVE" "30m"
Set-EnvDefault "OLLAMA_BASE_URL" "http://replace-with-ollama-host:11434"
Set-EnvDefault "OLLAMA_TRANS_MODEL" "replace-with-your-translator-model"
Set-EnvDefault "OLLAMA_SUM_MODEL" "replace-with-your-summarizer-model"

Set-Location (Join-Path $root "proxy")
& $venvPython -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload
