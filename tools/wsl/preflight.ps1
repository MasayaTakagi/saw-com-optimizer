# Read-only Windows / WSL / SAW environment inventory. Output is local and ignored by Git.
[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = 'Continue'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outputRoot = Join-Path $repoRoot 'artifacts\wsl-qualification'
if (-not $OutputPath) { $OutputPath = Join-Path $outputRoot 'preflight.json' }
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

function Invoke-CapturedCommand([string]$File, [string[]]$CommandArgs) {
    try {
        $lines = @(& $File @CommandArgs 2>&1 | ForEach-Object { [string]$_ })
        $code = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
        return [ordered]@{
            exitCode = $code
            output = (($lines -join "`n") -replace "`0", '').Trim()
        }
    } catch {
        return [ordered]@{ exitCode = $null; output = "ERROR: $($_.Exception.Message)" }
    }
}

function Get-OptionalFeatureState([string]$FeatureName) {
    $result = Invoke-CapturedCommand 'dism.exe' @('/Online', '/Get-FeatureInfo', "/FeatureName:$FeatureName")
    $text = [string]$result.output
    if ($text -match '(?im)^\s*(?:State|\u72B6\u614B)\s*:\s*(?:Enabled|\u6709\u52B9)\s*$') { $state = 'ENABLED' }
    elseif ($text -match '(?im)^\s*(?:State|\u72B6\u614B)\s*:\s*(?:Disabled|\u7121\u52B9)\s*$') { $state = 'DISABLED' }
    elseif ($result.exitCode -eq 740 -or $text -match '(?i)administrator|elevation|required|\u7BA1\u7406\u8005|\u6607\u683C') { $state = 'ADMIN_REQUIRED' }
    else { $state = 'UNKNOWN' }
    return [ordered]@{ state = $state; exitCode = $result.exitCode; diagnostic = $text }
}

function Get-RegistryDistroState {
    $items = @()
    $keyPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
    if (Test-Path $keyPath) {
        foreach ($item in (Get-ChildItem $keyPath -ErrorAction SilentlyContinue)) {
            $value = Get-ItemProperty $item.PSPath -ErrorAction SilentlyContinue
            if ($value.DistributionName) {
                $uid = $null
                if ($null -ne $value.DefaultUid) { $uid = [uint32]$value.DefaultUid }
                $userSetup = if ($null -eq $uid) { 'UNKNOWN' } elseif ($uid -gt 0) { 'COMPLETE' } else { 'UNKNOWN_OR_ROOT_DEFAULT' }
                $items += [ordered]@{ name = [string]$value.DistributionName; defaultUid = $uid; userSetup = $userSetup }
            }
        }
    }
    return ,$items
}

$osKey = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction SilentlyContinue
$build = [string]$osKey.CurrentBuild
if ($null -ne $osKey.UBR) { $build = "$build.$($osKey.UBR)" }
$processor = $null
$computer = $null
$hardwareStatus = 'UNKNOWN'
try {
    $processor = Get-CimInstance Win32_Processor -ErrorAction Stop | Select-Object -First 1
    $computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $hardwareStatus = 'READ'
} catch {
    $hardwareStatus = 'ACCESS_DENIED_OR_UNAVAILABLE'
}

$appx = @()
try { $appx = @(Get-AppxPackage -Name 'MicrosoftCorporationII.WindowsSubsystemForLinux' -ErrorAction Stop) } catch { }
$wslVersion = Invoke-CapturedCommand 'wsl.exe' @('--version')
$wslStatus = Invoke-CapturedCommand 'wsl.exe' @('--status')
$wslList = Invoke-CapturedCommand 'wsl.exe' @('--list', '--verbose')
$wslHelp = Invoke-CapturedCommand 'wsl.exe' @('--help')
$runtimeInstalled = ($wslVersion.exitCode -eq 0) -or ($wslList.exitCode -eq 0) -or ($appx.Count -gt 0)

$distros = @()
if ($wslList.exitCode -eq 0) {
    foreach ($line in ([string]$wslList.output -split "`n")) {
        if ($line -match '^\s*\*?\s*(?<name>[A-Za-z0-9][A-Za-z0-9_.-]*)\s+\S+\s+(?<version>[12])\s*$') {
            $name = $Matches.name
            $regEntry = $null
            foreach ($entry in (Get-RegistryDistroState)) { if ($entry.name -eq $name) { $regEntry = $entry; break } }
            $distros += [ordered]@{
                name = $name
                wslVersion = [int]$Matches.version
                linuxUserSetup = if ($null -eq $regEntry) { 'UNKNOWN' } else { $regEntry.userSetup }
            }
        }
    }
}
$ubuntu = @($distros | Where-Object { $_.name -match '(?i)^Ubuntu(?:[-_].*)?$' })
$case = if (-not $runtimeInstalled) { 'A' }
        elseif ($wslList.exitCode -ne 0) { 'UNKNOWN' }
        elseif ($ubuntu.Count -eq 0) { 'B' }
        elseif (@($ubuntu | Where-Object { $_.wslVersion -eq 2 }).Count -gt 0) { 'C' }
        else { 'D' }

$statusText = [string]$wslStatus.output
$defaultVersion = $null
if ($statusText -match '(?im)^.*(?:Default Version|\u65E2\u5B9A\u306E\u30D0\u30FC\u30B8\u30E7\u30F3).*?(?<version>[12])\s*$') {
    $defaultVersion = [int]$Matches.version
}

$git = [ordered]@{
    version = (Invoke-CapturedCommand 'git.exe' @('--version')).output
    repositoryPath = $repoRoot
    head = (Invoke-CapturedCommand 'git.exe' @('-C', $repoRoot, 'rev-parse', 'HEAD')).output
    branch = (Invoke-CapturedCommand 'git.exe' @('-C', $repoRoot, 'branch', '--show-current')).output
    mainHead = (Invoke-CapturedCommand 'git.exe' @('-C', $repoRoot, 'rev-parse', '--verify', 'refs/remotes/origin/main')).output
    status = (Invoke-CapturedCommand 'git.exe' @('-C', $repoRoot, 'status', '--short', '--branch')).output
    worktrees = (Invoke-CapturedCommand 'git.exe' @('-C', $repoRoot, 'worktree', 'list', '--porcelain')).output
    safeDirectory = (Invoke-CapturedCommand 'git.exe' @('-C', $repoRoot, 'config', '--show-origin', '--get-all', 'safe.directory')).output
}
$aclSummary = 'UNAVAILABLE'
try {
    $acl = Get-Acl (Join-Path $repoRoot '.git') -ErrorAction Stop
    $aclSummary = [ordered]@{
        owner = [string]$acl.Owner
        explicitDenyRules = @($acl.Access | Where-Object { $_.AccessControlType -eq 'Deny' } | ForEach-Object { $_.IdentityReference.ToString() })
    }
} catch { $aclSummary = "ACCESS_DENIED_OR_UNAVAILABLE: $($_.Exception.Message)" }
$git['gitDirectoryAcl'] = $aclSummary

$pythonPath = Join-Path $repoRoot '.venv\Scripts\python.exe'
$python = if (Test-Path $pythonPath) {
    $probe = @'
import json, platform, sys
values = {'python': sys.version.split()[0], 'platform': platform.platform()}
for module, key in [('numpy','numpy'), ('scipy','scipy'), ('matplotlib','matplotlib'), ('yaml','pyyaml'), ('pytest','pytest')]:
    try:
        imported = __import__(module)
        values[key] = getattr(imported, '__version__', 'installed')
    except Exception as exc:
        values[key] = 'UNAVAILABLE: ' + type(exc).__name__
print(json.dumps(values, sort_keys=True))
'@
    $old = $env:PYTHONDONTWRITEBYTECODE
    $env:PYTHONDONTWRITEBYTECODE = '1'
    try { (Invoke-CapturedCommand $pythonPath @('-c', $probe)).output } finally { $env:PYTHONDONTWRITEBYTECODE = $old }
} else { 'MISSING: .venv\Scripts\python.exe' }

$codexCommand = Get-Command codex -ErrorAction SilentlyContinue
$codexVersion = 'NOT_FOUND'
if ($null -ne $codexCommand) {
    $versionHome = Join-Path $outputRoot 'codex-version-query'
    New-Item -ItemType Directory -Force -Path $versionHome | Out-Null
    $oldCodexHome = $env:CODEX_HOME
    $env:CODEX_HOME = $versionHome
    try { $codexVersion = (Invoke-CapturedCommand $codexCommand.Source @('--version')).output }
    finally { $env:CODEX_HOME = $oldCodexHome }
}
$node = if (Get-Command node -ErrorAction SilentlyContinue) { (Invoke-CapturedCommand 'node.exe' @('--version')).output } else { 'NOT_FOUND' }
$npm = if (Get-Command npm -ErrorAction SilentlyContinue) { (Invoke-CapturedCommand 'npm.cmd' @('--version')).output } else { 'NOT_FOUND' }

$featureStates = [ordered]@{
    wsl = Get-OptionalFeatureState 'Microsoft-Windows-Subsystem-Linux'
    virtualMachinePlatform = Get-OptionalFeatureState 'VirtualMachinePlatform'
    hyperV = Get-OptionalFeatureState 'Microsoft-Hyper-V-All'
}
$lockfiles = @()
foreach ($name in @('uv.lock', 'poetry.lock', 'Pipfile.lock', 'requirements.txt', 'requirements-dev.txt')) {
    if (Test-Path (Join-Path $repoRoot $name)) { $lockfiles += $name }
}

$document = [ordered]@{
    schemaVersion = 1
    capturedAt = (Get-Date).ToUniversalTime().ToString('o')
    windows = [ordered]@{
        product = [string]$osKey.ProductName
        edition = [string]$osKey.EditionID
        displayVersion = [string]$osKey.DisplayVersion
        build = $build
        architecture = [string][System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
        cpuArchitecture = [string]$env:PROCESSOR_ARCHITECTURE
        virtualizationQuery = $hardwareStatus
        virtualizationFirmwareEnabled = if ($null -ne $processor) { $processor.VirtualizationFirmwareEnabled } else { $null }
        vmMonitorModeExtensions = if ($null -ne $processor) { $processor.VMMonitorModeExtensions } else { $null }
        secondLevelAddressTranslationExtensions = if ($null -ne $processor) { $processor.SecondLevelAddressTranslationExtensions } else { $null }
        hypervisorPresent = if ($null -ne $computer) { $computer.HypervisorPresent } else { $null }
        optionalFeatures = $featureStates
    }
    wsl = [ordered]@{
        installed = $runtimeInstalled
        appxPackages = @($appx | ForEach-Object { [ordered]@{ version = [string]$_.Version; packageStatus = [string]$_.Status } })
        versionCommand = $wslVersion
        statusCommand = $wslStatus
        listVerboseCommand = $wslList
        helpCommandExitCode = $wslHelp.exitCode
        defaultVersion = $defaultVersion
        distributions = $distros
        ubuntuDistributions = $ubuntu
        case = $case
    }
    development = [ordered]@{
        codexCli = $codexVersion
        codexCommandPath = if ($null -ne $codexCommand) { [string]$codexCommand.Source } else { $null }
        git = $git
        pythonEnvironment = $python
        lockfiles = $lockfiles
        packageConfig = 'pyproject.toml; project dependencies are lower bounds; no lockfile found when list is empty'
        node = $node
        npm = $npm
        repositoryCodexDirectoryExists = Test-Path (Join-Path $repoRoot '.codex')
        windowsCodexDirectory = Join-Path $env:USERPROFILE '.codex'
        windowsCodexDirectoryExists = Test-Path (Join-Path $env:USERPROFILE '.codex')
    }
    recommendedInstallCase = $case
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null
$document | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $OutputPath -Encoding utf8
Write-Output ([ordered]@{ status = 'DIAGNOSTIC_CAPTURED'; output = $OutputPath; wslCase = $case } | ConvertTo-Json -Compress)
