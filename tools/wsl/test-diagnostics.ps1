$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'diagnostic-helpers.ps1')

function Assert-Equal($Actual, $Expected, [string]$Name) {
    if ($Actual -ne $Expected) { throw "$Name failed: expected '$Expected', got '$Actual'." }
}

$case = Get-WslInstallCase -RuntimeInstalled $true -RegistryReadStatus 'READ' -RegistryDistroCount 0 -WslStatusExitCode 0 -DefaultVersion 2 -WslListExitCode -1 -ListConfirmsNoDistro $true -UbuntuVersions @()
Assert-Equal $case 'B' 'Store WSL with default v2 and no distro is Case B'
$deniedCase = Get-WslInstallCase -RuntimeInstalled $true -RegistryReadStatus 'READ' -RegistryDistroCount 0 -WslStatusExitCode -1 -DefaultVersion 2 -WslListExitCode -1 -ListConfirmsNoDistro $false -UbuntuVersions @()
Assert-Equal $deniedCase 'UNKNOWN' 'Access denied without no-distro evidence stays unknown'

$unrelatedRename = Get-PendingRenameAnalysis -Operations @('\??\C:\Users\tester\AppData\Local\Temp\orphan.tmp', '') -UserProfile 'C:\Users\tester'
$advisory = Get-RebootGateState -CbsPending $false -WindowsUpdatePending $false -PendingRenameReadStatus 'READ' -PendingRenameAnalysis $unrelatedRename
Assert-Equal $advisory.hardBlocker $false 'Unrelated pending rename is not a hard blocker'
Assert-Equal $advisory.classification 'REBOOT_ADVISORY_ONLY' 'Unrelated pending rename is advisory'
if (($unrelatedRename.entries[0].source + $unrelatedRename.entries[0].destination) -match 'tester') { throw 'User-specific path was not redacted.' }
$chromeRename = Get-PendingRenameAnalysis -Operations @('\??\C:\Program Files\Google\Chrome\Temp\old_chrome.exe', '') -UserProfile 'C:\Users\tester'
Assert-Equal $chromeRename.entries[0].component 'Google Chrome' 'Chrome component classification'
$officeRename = Get-PendingRenameAnalysis -Operations @('\??\C:\Program Files\Common Files\Microsoft Shared\ClickToRun\Updates\update.exe', '') -UserProfile 'C:\Users\tester'
Assert-Equal $officeRename.entries[0].component 'Microsoft Office' 'Office component classification'
$printingRename = Get-PendingRenameAnalysis -Operations @('\??\C:\Windows\System32\spool\V4Dirs\driver.gpd', '') -UserProfile 'C:\Users\tester'
Assert-Equal $printingRename.entries[0].component 'Windows printing' 'Printing component classification'

$cbsBlocked = Get-RebootGateState -CbsPending $true -WindowsUpdatePending $false -PendingRenameReadStatus 'READ' -PendingRenameAnalysis $unrelatedRename
Assert-Equal $cbsBlocked.hardBlocker $true 'CBS reboot pending remains blocked'
$wuBlocked = Get-RebootGateState -CbsPending $false -WindowsUpdatePending $true -PendingRenameReadStatus 'READ' -PendingRenameAnalysis $unrelatedRename
Assert-Equal $wuBlocked.hardBlocker $true 'Windows Update reboot required remains blocked'

$wslRename = Get-PendingRenameAnalysis -Operations @('\??\C:\Program Files\WSL\wslservice.old', '\??\C:\Program Files\WSL\wslservice.exe') -UserProfile 'C:\Users\tester'
$wslBlocked = Get-RebootGateState -CbsPending $false -WindowsUpdatePending $false -PendingRenameReadStatus 'READ' -PendingRenameAnalysis $wslRename
Assert-Equal $wslRename.relevantToWsl $true 'WSL rename is marked relevant'
Assert-Equal $wslBlocked.hardBlocker $true 'WSL-related pending rename blocks installation'

$virtualizationRename = Get-PendingRenameAnalysis -Operations @('\??\C:\Windows\System32\vmcompute.old', '\??\C:\Windows\System32\vmcompute.exe') -UserProfile 'C:\Users\tester'
$virtualizationBlocked = Get-RebootGateState -CbsPending $false -WindowsUpdatePending $false -PendingRenameReadStatus 'READ' -PendingRenameAnalysis $virtualizationRename
Assert-Equal $virtualizationBlocked.hardBlocker $true 'Virtualization-related pending rename blocks installation'

$fixture = [System.IO.Path]::GetTempFileName()
try {
    $fixtureData = [ordered]@{
        wsl = [ordered]@{ case = 'B'; diagnosticCase = 'CASE_B_CONFIRMED'; reason = 'NO_DISTRO_INSTALLED'; defaultVersion = 2; appxPackages = @(@{ name = 'MicrosoftCorporationII.WindowsSubsystemForLinux'; version = '3.0.1.0' }); ubuntuDistributions = @() }
        windows = [ordered]@{ reboot = [ordered]@{ hardBlocker = $false; classification = 'REBOOT_ADVISORY_ONLY'; pendingFileRenameRelevantToWsl = $false; reasons = @() } }
    }
    $fixtureData | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $fixture -Encoding utf8
    $plan = (& (Join-Path $PSScriptRoot 'install-wsl.ps1') -PreflightPath $fixture -PlanOnly | ConvertFrom-Json)
    Assert-Equal $plan.status 'PLAN_ONLY' 'Case B with advisory rename is plan-ready'
    Assert-Equal $plan.case 'B' 'Plan retains Case B'
    Assert-Equal $plan.setDefaultWslVersion $false 'Existing WSL 2 default is not changed'
    Assert-Equal $plan.currentWslPackageVersion '3.0.1.0' 'Plan records the current Store WSL version'
    Assert-Equal $plan.actions.Count 1 'Plan has one install action'
    if ($plan.actions[0] -notmatch 'Install Ubuntu-24\.04 only') { throw 'Case B plan does not contain Ubuntu-only action.' }
    Assert-Equal $plan.windowsFeatureChanges.Count 0 'Plan makes no Windows feature changes'
    Assert-Equal $plan.enableHyperV $false 'Plan does not enable Hyper-V'
    Assert-Equal $plan.wslReinstall $false 'Plan does not reinstall WSL'
    Assert-Equal $plan.wslDowngrade $false 'Plan does not downgrade WSL'

    $fixtureData.windows.reboot.hardBlocker = $true
    $fixtureData.windows.reboot.classification = 'BLOCKED'
    $fixtureData.windows.reboot.reasons = @('CBS_REBOOT_PENDING')
    $fixtureData | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $fixture -Encoding utf8
    $blockedPlan = (& (Join-Path $PSScriptRoot 'install-wsl.ps1') -PreflightPath $fixture -PlanOnly | ConvertFrom-Json)
    Assert-Equal $blockedPlan.status 'PLAN_BLOCKED' 'CBS pending blocks Case B plan'
    $fixtureData.wsl.case = 'C'
    $blockedExistingPlan = (& (Join-Path $PSScriptRoot 'install-wsl.ps1') -PreflightPath $fixture -PlanOnly | ConvertFrom-Json)
    Assert-Equal $blockedExistingPlan.status 'PLAN_BLOCKED' 'CBS pending blocks all install plan cases'
} finally {
    Remove-Item -LiteralPath $fixture -Force -ErrorAction SilentlyContinue
}

$state = -join @([char]0x72B6, [char]0x614B)
$enabled = -join @([char]0x6709, [char]0x52B9)
$statePattern = '(?im)^\s*(?:State|\u72B6\u614B)\s*:\s*(?:Enabled|\u6709\u52B9)\s*$'
if (-not [regex]::IsMatch("$state`: $enabled", $statePattern)) { throw 'Japanese Unicode-escaped regex compatibility failed.' }
$noDistro = -join @([char]0x30A4, [char]0x30F3, [char]0x30B9, [char]0x30C8, [char]0x30FC, [char]0x30EB, [char]0x3055, [char]0x308C, [char]0x3066, [char]0x3044, [char]0x308B, [char]0x30C7, [char]0x30A3, [char]0x30B9, [char]0x30C8, [char]0x30EA, [char]0x30D3, [char]0x30E5, [char]0x30FC, [char]0x30B7, [char]0x30E7, [char]0x30F3, [char]0x306F, [char]0x3042, [char]0x308A, [char]0x307E, [char]0x305B, [char]0x3093)
$noDistroPattern = '(?i)no installed distributions|no distributions installed|\u30A4\u30F3\u30B9\u30C8\u30FC\u30EB\u3055\u308C\u3066\u3044\u308B\u30C7\u30A3\u30B9\u30C8\u30EA\u30D3\u30E5\u30FC\u30B7\u30E7\u30F3\u306F\u3042\u308A\u307E\u305B\u3093'
if (-not [regex]::IsMatch($noDistro, $noDistroPattern)) { throw 'Japanese no-distro message compatibility failed.' }
$defaultVersionLine = -join @([char]0x65E2, [char]0x5B9A, [char]0x306E, [char]0x30D0, [char]0x30FC, [char]0x30B8, [char]0x30E7, [char]0x30F3) + ': 2'
$defaultVersionPattern = '(?im)^.*(?:Default Version|\u65E2\u5B9A\u306E\u30D0\u30FC\u30B8\u30E7\u30F3).*?(?<version>[12])\s*$'
if (-not [regex]::IsMatch($defaultVersionLine, $defaultVersionPattern)) { throw 'Japanese default WSL version compatibility failed.' }

$sourceFiles = @('preflight.ps1', 'install-wsl.ps1', 'diagnostic-helpers.ps1', 'test-diagnostics.ps1')
foreach ($name in $sourceFiles) {
    $path = Join-Path $PSScriptRoot $name
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) { throw "$name has PowerShell parser errors: $($errors[0].Message)" }
    $source = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
    if (@($source.ToCharArray() | Where-Object { [int]$_ -gt 127 }).Count -gt 0) { throw "$name must remain ASCII-only for Windows PowerShell 5.1." }
}

Write-Output 'PASS: WSL diagnostics and fail-closed plan tests'
