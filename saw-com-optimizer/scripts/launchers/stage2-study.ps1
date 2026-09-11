param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CliArgs)

& (Join-Path $PSScriptRoot '..\common\invoke-sawopt.ps1') -Module sawopt.studies.topology_screening @CliArgs
exit $LASTEXITCODE
