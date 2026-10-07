# User-gated installer. Never auto-elevates, restarts Windows, or launches Ubuntu.
[CmdletBinding()]
param(
    [string]$PreflightPath,
    [switch]$PlanOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outputRoot = Join-Path $repoRoot 'artifacts\wsl-qualification'
$targetDistro = 'Ubuntu-24.04'
$preflightWasProvided = -not [string]::IsNullOrWhiteSpace($PreflightPath)
if (-not $preflightWasProvided) { $PreflightPath = Join-Path $outputRoot 'preflight.json' }

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Write-InstallState($Value) {
    New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
    $path = Join-Path $outputRoot 'install-state.json'
    $Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $path -Encoding utf8
    Write-Output ([ordered]@{ status = $Value.status; output = $path; case = $Value.case } | ConvertTo-Json -Compress)
}

if (-not $preflightWasProvided) {
    & (Join-Path $PSScriptRoot 'preflight.ps1') -OutputPath $PreflightPath | Out-Null
}
$preflight = Get-Content -LiteralPath $PreflightPath -Raw | ConvertFrom-Json
$case = [string]$preflight.wsl.case
$diagnosticCase = [string]$preflight.wsl.diagnosticCase
$unknownDiagnostic = ($case -eq 'UNKNOWN' -or $case.StartsWith('UNKNOWN_', [StringComparison]::OrdinalIgnoreCase) -or $diagnosticCase.StartsWith('UNKNOWN_', [StringComparison]::OrdinalIgnoreCase))
if ($unknownDiagnostic) { $case = 'UNKNOWN' }
$reboot = $preflight.windows.reboot
$rebootHardBlocker = $null
if ($null -ne $reboot -and $null -ne $reboot.PSObject.Properties['hardBlocker'] -and $null -ne $reboot.hardBlocker) {
    $rebootHardBlocker = [bool]$reboot.hardBlocker
}
$rebootBlocked = ($rebootHardBlocker -ne $false)
$rebootBlockReason = if ($rebootHardBlocker -eq $true) { [string]::Join(',', [string[]]$reboot.reasons) } else { 'REBOOT_STATE_UNKNOWN' }
$planBlocked = ($unknownDiagnostic -or $rebootBlocked)
$currentWslPackage = $preflight.wsl.appxPackages | Where-Object { $_.name -eq 'MicrosoftCorporationII.WindowsSubsystemForLinux' } | Select-Object -First 1
$currentWslPackageVersion = if ($null -ne $currentWslPackage) { [string]$currentWslPackage.version } else { $null }
$ubuntu = @($preflight.wsl.ubuntuDistributions)
$setDefaultVersionRequired = ($case -eq 'B' -and [int]$preflight.wsl.defaultVersion -ne 2)
$actions = if ($unknownDiagnostic) {
    @('Stop: WSL state is unknown or has a diagnostic-only subtype. Resolve the recorded blocker before installing or converting any distribution.')
} elseif ($rebootBlocked) {
    @("Stop: reboot gate is not clear ($rebootBlockReason). No WSL installation or conversion is allowed.")
} else { switch ($case) {
    'A' { @("Install stable WSL and $targetDistro with WSL 2 as the default; keep Ubuntu unopened.") }
    'B' {
        if ($setDefaultVersionRequired) { @('Set WSL 2 as the default for new distributions.', "Install $targetDistro without launching it.") }
        else { @("Install $targetDistro only without launching it; WSL 2 is already the default.") }
    }
    'C' { @('Reuse the detected Ubuntu distribution already running under WSL 2; make no installation changes.') }
    'D' { @('Export the existing WSL 1 Ubuntu distribution to a local backup, then convert it to WSL 2.') }
    default { throw "Unrecognized WSL install case in preflight: $case" }
} }

if ($PlanOnly) {
    $planStatus = if ($planBlocked) { 'PLAN_BLOCKED' } else { 'PLAN_ONLY' }
    Write-Output ([ordered]@{
        status = $planStatus
        case = $case
        reason = if ($planBlocked) { if ($unknownDiagnostic) { $diagnosticCase } else { $rebootBlockReason } } else { [string]$preflight.wsl.reason }
        targetDistribution = $targetDistro
        actions = [string[]]$actions
        currentWslPackageVersion = $currentWslPackageVersion
        defaultWslVersion = $preflight.wsl.defaultVersion
        setDefaultWslVersion = $setDefaultVersionRequired
        windowsFeatureChanges = @()
        wslReinstall = $false
        wslDowngrade = $false
        enableHyperV = $false
        rebootClassification = [string]$reboot.classification
        pendingFileRenameRelevantToWsl = $reboot.pendingFileRenameRelevantToWsl
        preflight = $PreflightPath
    } | ConvertTo-Json -Depth 6)
    return
}

if ($planBlocked) {
    $blockReason = if ($unknownDiagnostic) { $diagnosticCase } else { $rebootBlockReason }
    throw "WSL install is blocked ($blockReason). No installation changes were started."
}
if ($case -eq 'C') {
    Write-InstallState ([ordered]@{
        status = 'READY_EXISTING_WSL2'
        case = $case
        targetDistribution = ($ubuntu | Where-Object { $_.wslVersion -eq 2 } | Select-Object -First 1).name
        windowsChanged = $false
        firstLinuxUser = ($ubuntu | Where-Object { $_.wslVersion -eq 2 } | Select-Object -First 1).linuxUserSetup
        actions = $actions
    })
    return
}
if (-not (Test-Administrator)) {
    throw 'This installation case changes Windows WSL features. Open an elevated PowerShell and rerun this script; it does not request elevation.'
}
if ([string]$preflight.windows.virtualizationFirmwareEnabled -ne 'True') {
    throw 'Firmware virtualization is not affirmatively enabled in the elevated preflight. No WSL changes were started.'
}
if ($preflight.windows.virtualizationQuery -eq 'ACCESS_DENIED_OR_UNAVAILABLE') {
    throw 'Virtualization capability could not be read in the elevated preflight. No WSL changes were started.'
}
$backupPath = $null
$wslChanged = $false
if ($case -eq 'A') {
    # Microsoft stable install path: no preview flags and no pre-release channel.
    & wsl.exe --install --distribution $targetDistro --no-launch
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Stable WSL installation failed with exit code $code. No automatic restart was requested." }
    $wslChanged = $true
} elseif ($case -eq 'B') {
    if ($setDefaultVersionRequired) {
        & wsl.exe --set-default-version 2
        if ($LASTEXITCODE -ne 0) { throw "Setting WSL 2 as the default failed (exit $LASTEXITCODE)." }
    }
    & wsl.exe --install --distribution $targetDistro --no-launch
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Ubuntu installation failed with exit code $code. No automatic restart was requested." }
    $wslChanged = $true
} elseif ($case -eq 'D') {
    $legacy = $ubuntu | Where-Object { $_.wslVersion -eq 1 } | Select-Object -First 1
    if ($null -eq $legacy) { throw 'Preflight classified Case D but found no WSL 1 Ubuntu distribution; refusing an ambiguous conversion.' }
    & wsl.exe --set-default-version 2
    if ($LASTEXITCODE -ne 0) { throw "Setting WSL 2 as the default failed (exit $LASTEXITCODE)." }
    $backupDir = Join-Path $outputRoot 'distribution-backups'
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $safeName = [regex]::Replace([string]$legacy.name, '[^A-Za-z0-9_.-]', '_')
    $backupPath = Join-Path $backupDir "$safeName-before-wsl2.tar"
    if (Test-Path $backupPath) { throw "Backup already exists; refusing to overwrite it: $backupPath" }
    & wsl.exe --export $legacy.name $backupPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $backupPath) -or (Get-Item $backupPath).Length -le 0) {
        throw "Export backup failed for $($legacy.name); conversion was not started."
    }
    & wsl.exe --set-version $legacy.name 2
    if ($LASTEXITCODE -ne 0) { throw "WSL 1 to WSL 2 conversion failed. Preserve the export at $backupPath and inspect the WSL diagnostics." }
    $wslChanged = $true
}

& (Join-Path $PSScriptRoot 'preflight.ps1') -OutputPath $PreflightPath | Out-Null
$postflight = Get-Content -LiteralPath $PreflightPath -Raw | ConvertFrom-Json
$restartRequired = ($null -eq $postflight.windows.reboot.hardBlocker -or [bool]$postflight.windows.reboot.hardBlocker)
$afterList = [string]$postflight.wsl.listVerboseCommand.output
if ($postflight.wsl.listVerboseCommand.exitCode -ne 0) { $restartRequired = $true }
$firstUser = switch ($case) {
    { $_ -in 'A', 'B' } { 'NOT_STARTED; FIRST_LAUNCH_REQUIRED_FOR_NEW_DISTRIBUTION' }
    'D' { [string]$legacy.linuxUserSetup }
    default { 'NOT_REQUIRED' }
}
$status = if ($restartRequired) { 'RESTART_REQUIRED' }
          elseif ($case -in 'A', 'B') { 'WAITING_FOR_FIRST_LINUX_USER' }
          else { 'WSL2_CONVERSION_COMPLETED' }
Write-InstallState ([ordered]@{
    status = $status
    case = $case
    targetDistribution = $targetDistro
    wslChanged = $wslChanged
    restartRequired = $restartRequired
    restartAutomatic = $false
    firstLinuxUser = $firstUser
    ubuntuListAfter = $afterList
    existingDistributionBackup = $backupPath
    previewWslUsed = $false
    preReleaseUsed = $false
    actions = $actions
})
if ($restartRequired) {
    Write-Warning 'Restart Windows manually before continuing. This script will not restart the machine.'
} elseif ($case -in 'A', 'B') {
    Write-Warning 'Start the detected Ubuntu distribution yourself once to create its Linux username and password; this script never launches it.'
}
