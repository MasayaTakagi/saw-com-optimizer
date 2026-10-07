param(
    [Parameter(Mandatory=$true)][string]$Module,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$CliArgs
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtual environment is missing: $python. This historical Windows launcher requires an existing Windows environment. Use WSL and uv for current development; see docs/guides/development_environment.md."
}
$env:PYTHONPATH = "$projectRoot\src"

Push-Location $projectRoot
try {
    & $python -m $Module @CliArgs
    $sawExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $sawExitCode
