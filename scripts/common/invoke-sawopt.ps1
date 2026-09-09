param(
    [Parameter(Mandatory=$true)][string]$Module,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$CliArgs
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = 'C:\Users\sub\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = "$projectRoot\src;$projectRoot\..\.deps"

Push-Location $projectRoot
try {
    & $python -m $Module @CliArgs
    $sawExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $sawExitCode
