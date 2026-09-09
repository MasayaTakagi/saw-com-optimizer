param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CliArgs)

& (Join-Path $PSScriptRoot '..\common\invoke-sawopt.ps1') -Module sawopt.optimization.stage2_study @CliArgs
exit $LASTEXITCODE
