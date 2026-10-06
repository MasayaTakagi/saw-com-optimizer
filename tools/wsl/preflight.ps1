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

function Convert-NativeOutputBytes([byte[]]$Bytes) {
    if ($null -eq $Bytes -or $Bytes.Length -eq 0) { return '' }
    if ($Bytes.Length -ge 2 -and $Bytes[0] -eq 0xFF -and $Bytes[1] -eq 0xFE) { return [System.Text.Encoding]::Unicode.GetString($Bytes, 2, $Bytes.Length - 2) }
    if ($Bytes.Length -ge 2 -and $Bytes[0] -eq 0xFE -and $Bytes[1] -eq 0xFF) { return [System.Text.Encoding]::BigEndianUnicode.GetString($Bytes, 2, $Bytes.Length - 2) }
    $oddZeroCount = 0
    $evenZeroCount = 0
    for ($index = 0; $index -lt $Bytes.Length; $index++) {
        if ($Bytes[$index] -eq 0) {
            if (($index % 2) -eq 0) { $evenZeroCount++ } else { $oddZeroCount++ }
        }
    }
    if (($Bytes.Length % 2) -eq 0 -and $oddZeroCount -ge [Math]::Max(2, [Math]::Floor($Bytes.Length / 12)) -and $oddZeroCount -gt (2 * $evenZeroCount)) {
        return [System.Text.Encoding]::Unicode.GetString($Bytes)
    }
    try { return (New-Object System.Text.UTF8Encoding($false, $true)).GetString($Bytes) }
    catch { return [System.Text.Encoding]::Default.GetString($Bytes) }
}

function Invoke-CapturedUtf8Command([string]$File, [string[]]$CommandArgs) {
    $process = $null
    $stdoutStream = $null
    $stderrStream = $null
    try {
        $command = Get-Command $File -ErrorAction Stop | Select-Object -First 1
        $quotedArgs = @($CommandArgs | ForEach-Object {
            $value = [string]$_
            if ($value -match '[\s"]') { '"' + $value.Replace('"', '\"') + '"' } else { $value }
        })
        $info = New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName = [string]$command.Source
        $info.Arguments = [string]::Join(' ', [string[]]$quotedArgs)
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $info
        [void]$process.Start()
        $stdoutStream = New-Object System.IO.MemoryStream
        $stderrStream = New-Object System.IO.MemoryStream
        $stdoutTask = $process.StandardOutput.BaseStream.CopyToAsync($stdoutStream)
        $stderrTask = $process.StandardError.BaseStream.CopyToAsync($stderrStream)
        $process.WaitForExit()
        $stdoutTask.Wait()
        $stderrTask.Wait()
        $stdout = Convert-NativeOutputBytes $stdoutStream.ToArray()
        $stderr = Convert-NativeOutputBytes $stderrStream.ToArray()
        $text = (($stdout, $stderr | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "`n").Trim()
        $hresult = $null
        if ($text -match '(?i)\b0x[0-9a-f]{8}\b') { $hresult = $Matches[0].ToUpperInvariant() }
        $errorToken = $null
        if ($text -match '(?i)\b(Wsl/[A-Za-z0-9_./-]+|E_ACCESSDENIED|E_[A-Z0-9_]+)\b') { $errorToken = $Matches[0] }
        return [ordered]@{
            exitCode = [int]$process.ExitCode
            output = $text
            hresult = $hresult
            errorToken = $errorToken
        }
    } catch {
        return [ordered]@{ exitCode = $null; output = "ERROR: $($_.Exception.Message)"; hresult = ('0x{0:X8}' -f $_.Exception.HResult); errorToken = 'POWERSHELL_EXCEPTION' }
    } finally {
        if ($null -ne $stdoutStream) { $stdoutStream.Dispose() }
        if ($null -ne $stderrStream) { $stderrStream.Dispose() }
        if ($null -ne $process) { $process.Dispose() }
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
    $items = New-Object System.Collections.Generic.List[object]
    $root = $null
    $sid = $null
    $keyExists = $false
    $subkeyCount = $null
    $readStatus = 'READ'
    try {
        $sid = [string][Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        $root = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Software\Microsoft\Windows\CurrentVersion\Lxss')
        if ($null -ne $root) {
            $keyExists = $true
            $subkeys = @($root.GetSubKeyNames())
            $subkeyCount = $subkeys.Count
            foreach ($subkeyName in $subkeys) {
                $distroKey = $null
                try {
                    $distroKey = $root.OpenSubKey([string]$subkeyName)
                    if ($null -eq $distroKey) { continue }
                    $name = $distroKey.GetValue('DistributionName', $null)
                    if ([string]::IsNullOrWhiteSpace([string]$name)) { continue }
                    $uidValue = $distroKey.GetValue('DefaultUid', $null)
                    $uid = if ($null -eq $uidValue) { $null } else { [uint32]$uidValue }
                    $versionValue = $distroKey.GetValue('Version', $null)
                    $basePath = [string]$distroKey.GetValue('BasePath', '')
                    $basePathExists = $null
                    if (-not [string]::IsNullOrWhiteSpace($basePath)) {
                        try { $basePathExists = [bool](Test-Path -LiteralPath $basePath) } catch { $basePathExists = $null }
                    }
                    $items.Add([ordered]@{
                        name = [string]$name
                        defaultUid = $uid
                        userSetup = if ($null -eq $uid) { 'UNKNOWN' } elseif ($uid -gt 0) { 'COMPLETE' } else { 'UNKNOWN_OR_ROOT_DEFAULT' }
                        version = if ($null -eq $versionValue) { $null } else { [int]$versionValue }
                        basePathExists = $basePathExists
                    })
                } finally {
                    if ($null -ne $distroKey) { $distroKey.Close() }
                }
            }
        } else { $subkeyCount = 0 }
    } catch {
        $readStatus = 'ACCESS_DENIED_OR_UNAVAILABLE'
    } finally {
        if ($null -ne $root) { $root.Close() }
    }
    return [ordered]@{
        readStatus = $readStatus
        currentUserSid = $sid
        keyExists = $keyExists
        subkeyCount = $subkeyCount
        distributions = [object[]]$items.ToArray()
    }
}

function Get-ServiceDiagnostic([string]$ServiceName) {
    $service = $null
    $serviceError = $null
    try { $service = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'" -ErrorAction Stop | Select-Object -First 1 }
    catch { $serviceError = [string]$_.Exception.Message }
    $qc = Invoke-CapturedCommand 'sc.exe' @('qc', $ServiceName)
    $query = Invoke-CapturedCommand 'sc.exe' @('queryex', $ServiceName)
    $state = if ($null -ne $service) { [string]$service.State }
             elseif ($qc.output -match '(?i)does not exist|1060') { 'NOT_FOUND' }
             elseif ($query.output -match '(?im)^\s*STATE\s*:\s*\d+\s+([A-Z_]+)') { $Matches[1] }
             else { 'UNKNOWN' }
    $startType = if ($null -ne $service) { [string]$service.StartMode }
                 elseif ($qc.output -match '(?im)^\s*START_TYPE\s*:\s*\d+\s+([A-Z_]+)') { $Matches[1] }
                 else { $null }
    $processId = if ($null -ne $service) { [uint32]$service.ProcessId }
                 elseif ($query.output -match '(?im)^\s*PID\s*:\s*(\d+)') { [uint32]$Matches[1] }
                 else { $null }
    $exists = if ($null -ne $service) { $true } elseif ($state -eq 'NOT_FOUND') { $false }
              elseif ($qc.output -match '(?i)QueryServiceConfig SUCCESS') { $true } else { $null }
    return [ordered]@{
        serviceName = $ServiceName
        state = $state
        startType = $startType
        processId = $processId
        exists = $exists
        queryError = $serviceError
        scQc = $qc
        scQueryEx = $query
    }
}

function Get-PendingRestartState {
    $baseKey = $null
    $components = [ordered]@{}
    $readFailed = $false
    try {
        $baseKey = [Microsoft.Win32.Registry]::LocalMachine
        foreach ($entry in @(
            @{ name = 'componentBasedServicing'; path = 'SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending' },
            @{ name = 'windowsUpdate'; path = 'SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired' }
        )) {
            try {
                $key = $baseKey.OpenSubKey([string]$entry.path)
                $components[$entry.name] = ($null -ne $key)
                if ($null -ne $key) { $key.Close() }
            } catch { $components[$entry.name] = $null; $readFailed = $true }
        }
        try {
            $sessionManager = $baseKey.OpenSubKey('SYSTEM\CurrentControlSet\Control\Session Manager')
            if ($null -eq $sessionManager) { $components['pendingFileRenameOperations'] = $null; $readFailed = $true }
            else {
                $names = @($sessionManager.GetValueNames())
                $hasValue = $names -contains 'PendingFileRenameOperations'
                $value = if ($hasValue) { $sessionManager.GetValue('PendingFileRenameOperations', $null) } else { $null }
                $pendingOperations = @($value | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
                $components['pendingFileRenameOperations'] = [bool]($hasValue -and $pendingOperations.Count -gt 0)
                $sessionManager.Close()
            }
        } catch { $components['pendingFileRenameOperations'] = $null; $readFailed = $true }
    } catch { $readFailed = $true }
    $values = @($components.Values)
    $state = if ($values -contains $true) { 'TRUE' } elseif ($readFailed -or $values -contains $null) { 'UNKNOWN' } else { 'FALSE' }
    return [ordered]@{ state = $state; components = $components }
}

function Get-RelevantEventLogs {
    $logs = @(
        'Microsoft-Windows-Lxss/Operational',
        'Microsoft-Windows-Subsystem-Linux/Operational',
        'Microsoft-Windows-Hyper-V-Compute-Admin',
        'Microsoft-Windows-Hyper-V-Compute-Operational'
    )
    $since = (Get-Date).AddHours(-24)
    $results = @()
    foreach ($logName in $logs) {
        try {
            $log = Get-WinEvent -ListLog $logName -ErrorAction Stop
            if (-not $log.IsEnabled) {
                $results += [ordered]@{ channel = $logName; status = 'DISABLED'; events = @() }
                continue
            }
            try {
                $events = @(Get-WinEvent -FilterHashtable @{ LogName = $logName; StartTime = $since } -MaxEvents 5 -ErrorAction Stop | ForEach-Object {
                    $message = [string]$_.Message
                    if ($message.Length -gt 1200) { $message = $message.Substring(0, 1200) }
                    [ordered]@{ timeCreated = $_.TimeCreated.ToUniversalTime().ToString('o'); id = [int]$_.Id; level = [string]$_.LevelDisplayName; message = $message }
                })
                $results += [ordered]@{ channel = $logName; status = 'READ'; events = $events }
            } catch {
                if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound,*') { $results += [ordered]@{ channel = $logName; status = 'READ'; events = @() } }
                else { $results += [ordered]@{ channel = $logName; status = 'ACCESS_DENIED_OR_UNAVAILABLE'; events = @(); error = [string]$_.Exception.Message } }
            }
        } catch {
            $results += [ordered]@{ channel = $logName; status = 'NOT_FOUND_OR_UNAVAILABLE'; events = @() }
        }
    }
    return ,$results
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
$appxQueryStatus = 'READ'
$appxQueryError = $null
try { $appx = @(Get-AppxPackage -Name 'MicrosoftCorporationII.WindowsSubsystemForLinux' -ErrorAction Stop) }
catch { $appxQueryStatus = 'ACCESS_DENIED_OR_UNAVAILABLE'; $appxQueryError = [string]$_.Exception.Message }
$wslCommand = Get-Command 'wsl.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
$wslExecutable = [ordered]@{ commandType = if ($null -ne $wslCommand) { [string]$wslCommand.CommandType } else { 'NOT_FOUND' }; resolvedPath = if ($null -ne $wslCommand) { [string]$wslCommand.Source } else { $null }; fileVersion = $null; productVersion = $null; pathExists = $false }
if ($null -ne $wslCommand -and (Test-Path -LiteralPath $wslCommand.Source)) {
    $wslExecutable.pathExists = $true
    try {
        $file = Get-Item -LiteralPath $wslCommand.Source -ErrorAction Stop
        $wslExecutable.fileVersion = [string]$file.VersionInfo.FileVersion
        $wslExecutable.productVersion = [string]$file.VersionInfo.ProductVersion
    } catch { }
}
$packageDetails = @($appx | ForEach-Object {
    [ordered]@{
        name = [string]$_.Name
        version = [string]$_.Version
        packageStatus = [string]$_.Status
        installLocationExists = if ([string]::IsNullOrWhiteSpace([string]$_.InstallLocation)) { $false } else { [bool](Test-Path -LiteralPath $_.InstallLocation) }
    }
})
$wslVersion = Invoke-CapturedUtf8Command 'wsl.exe' @('--version')
$wslStatus = Invoke-CapturedUtf8Command 'wsl.exe' @('--status')
$wslList = Invoke-CapturedUtf8Command 'wsl.exe' @('--list', '--verbose')
$wslHelp = Invoke-CapturedUtf8Command 'wsl.exe' @('--help')
$runtimeInstalled = ($wslVersion.exitCode -eq 0) -or ($wslList.exitCode -eq 0) -or ($appx.Count -gt 0)
$registryDistroState = Get-RegistryDistroState
$serviceNames = @('WslService', 'LxssManager', 'vmcompute', 'hns')
$serviceDiagnostics = @($serviceNames | ForEach-Object { Get-ServiceDiagnostic $_ })
$pendingRestart = Get-PendingRestartState
$recentEventLogs = Get-RelevantEventLogs

$distros = @()
if ($wslList.exitCode -eq 0) {
    foreach ($line in ([string]$wslList.output -split "`n")) {
        if ($line -match '^\s*\*?\s*(?<name>[A-Za-z0-9][A-Za-z0-9_.-]*)\s+\S+\s+(?<version>[12])\s*$') {
            $name = $Matches.name
            $regEntry = $null
            foreach ($entry in $registryDistroState.distributions) { if ($entry.name -eq $name) { $regEntry = $entry; break } }
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

$wslFailureText = @([string]$wslStatus.output, [string]$wslList.output) -join "`n"
$accessDenied = ($wslFailureText -match '(?i)E_ACCESSDENIED|0x80070005|access denied|permission denied|unauthorizedaccess')
$wslServiceCandidates = @($serviceDiagnostics | Where-Object { $_.serviceName -in @('WslService', 'LxssManager') })
$wslServiceSummary = if (@($wslServiceCandidates | Where-Object { $_.state -eq 'Running' }).Count -gt 0) { 'RUNNING' }
                     elseif ($wslServiceCandidates.Count -gt 0 -and @($wslServiceCandidates | Where-Object { $_.state -eq 'NOT_FOUND' }).Count -eq $wslServiceCandidates.Count) { 'NOT_FOUND' }
                     elseif (@($wslServiceCandidates | Where-Object { $_.state -eq 'Stopped' }).Count -gt 0) { 'STOPPED' }
                     else { 'UNKNOWN' }
$diagnosticCase = 'NONE'
$diagnosticReason = 'WSL_COMMANDS_AVAILABLE'
if ($case -eq 'UNKNOWN') {
    if ($wslServiceSummary -eq 'NOT_FOUND') {
        $diagnosticCase = 'UNKNOWN_WSL_SERVICE_MISSING'
        $diagnosticReason = 'WSL_SERVICE_MISSING'
    } elseif ($wslServiceSummary -eq 'STOPPED') {
        $diagnosticCase = 'UNKNOWN_WSL_SERVICE_STOPPED'
        $diagnosticReason = 'WSL_SERVICE_STOPPED'
    } elseif ($accessDenied -and $registryDistroState.readStatus -eq 'READ' -and $registryDistroState.distributions.Count -gt 0) {
        $diagnosticCase = 'UNKNOWN_WSL_COMMAND_ACCESS_DENIED_WITH_REGISTERED_DISTRO'
        $diagnosticReason = 'WSL_COMMAND_ACCESS_DENIED'
    } elseif ($accessDenied -and $registryDistroState.readStatus -eq 'READ' -and $registryDistroState.distributions.Count -eq 0) {
        $diagnosticCase = 'UNKNOWN_WSL_COMMAND_ACCESS_DENIED_NO_REGISTERED_DISTRO'
        $diagnosticReason = 'WSL_COMMAND_ACCESS_DENIED'
    } elseif ($pendingRestart.state -eq 'TRUE') {
        $diagnosticCase = 'UNKNOWN_PENDING_RESTART'
        $diagnosticReason = 'PENDING_RESTART'
    } else {
        $diagnosticCase = 'UNKNOWN_OTHER'
        $diagnosticReason = if ($accessDenied) { 'WSL_COMMAND_ACCESS_DENIED_REGISTRY_STATE_UNAVAILABLE' } else { 'WSL_COMMAND_FAILED' }
    }
}

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
    schemaVersion = 2
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
        pendingRestart = $pendingRestart
    }
    wsl = [ordered]@{
        installed = $runtimeInstalled
        appxQueryStatus = $appxQueryStatus
        appxQueryError = $appxQueryError
        appxPackages = $packageDetails
        executable = $wslExecutable
        versionCommand = $wslVersion
        statusCommand = $wslStatus
        listVerboseCommand = $wslList
        helpCommandExitCode = $wslHelp.exitCode
        defaultVersion = $defaultVersion
        registryDistributions = $registryDistroState
        distributions = $distros
        ubuntuDistributions = $ubuntu
        services = $serviceDiagnostics
        serviceSummary = $wslServiceSummary
        recentEventLogs = $recentEventLogs
        case = $case
        diagnosticCase = $diagnosticCase
        reason = $diagnosticReason
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
    pendingRestart = $pendingRestart.state
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null
$document | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $OutputPath -Encoding utf8
$summary = [ordered]@{
    status = 'DIAGNOSTIC_CAPTURED'
    wslCase = $case
    reason = $diagnosticReason
    diagnosticCase = $diagnosticCase
    registryDistroCount = @($registryDistroState.distributions).Count
    wslService = $wslServiceSummary
    virtualMachinePlatform = $featureStates.virtualMachinePlatform.state
    pendingRestart = $pendingRestart.state
    nextAction = if ($case -eq 'UNKNOWN') { 'DIAGNOSIS_REQUIRED' } else { 'REVIEW_PREFLIGHT' }
}
Write-Output ($summary | ConvertTo-Json -Compress)
