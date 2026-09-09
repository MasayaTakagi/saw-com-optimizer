param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CliArgs)

& (Join-Path $PSScriptRoot '..\common\invoke-sawopt.ps1') -Module sawopt.optimization.hybrid_study @CliArgs
exit $LASTEXITCODE
