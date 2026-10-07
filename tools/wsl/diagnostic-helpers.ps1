function Get-PendingPathClassification([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return 'unknown' }
    if ($Path -match '(?i)(?:^|[\\/])WSL(?:[\\/]|$)|Lxss|Ubuntu|Canonical|MicrosoftCorporationII\.WindowsSubsystemForLinux|wslservice\.exe|wslhost\.exe|wslg\.exe') { return 'WSL' }
    if ($Path -match '(?i)VirtualMachinePlatform|vmcompute|vmwp|vmswitch|HvHost|Hyper-V|hypervisor') { return 'virtualization' }
    if ($Path -match '(?i)SoftwareDistribution|WindowsUpdate|UpdateOrchestrator|WUClient') { return 'Windows Update' }
    if ($Path -match '(?i)WinSxS|\\Windows\\servicing|TrustedInstaller|\\CBS\\|Pending\.xml') { return 'Windows servicing' }
    if ($Path -match '(?i)Microsoft\\Edge|EdgeUpdate|msedge') { return 'Microsoft Edge' }
    if ($Path -match '(?i)Google\\Chrome|chrome\.exe') { return 'Google Chrome' }
    if ($Path -match '(?i)ClickToRun|Microsoft Office|\\Office\d*\\|OFFSYM|OFFSY') { return 'Microsoft Office' }
    if ($Path -match '(?i)\\spool\\|\.(?:BUD|GPD)$') { return 'Windows printing' }
    if ($Path -match '(?i)Windows Defender|SecurityHealth|CrowdStrike|SentinelOne|Sophos|ESET|Norton|McAfee|Avast|Trend Micro') { return 'security software' }
    if ($Path -match '(?i)Visual Studio|\\VSCode?\\|Visual Studio Code|GitHub|OpenAI\\Codex|Node\.js|\\Python\d*\\|npm|pnpm|JetBrains|PyCharm') { return 'developer tools' }
    return 'other'
}

function Protect-PendingPath([string]$Path, [string]$UserProfile) {
    if ([string]::IsNullOrEmpty($Path)) { return $null }
    $safe = $Path.Trim()
    if (-not [string]::IsNullOrWhiteSpace($UserProfile)) {
        $safe = [regex]::Replace($safe, [regex]::Escape($UserProfile), '%USERPROFILE%', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    }
    $safe = [regex]::Replace($safe, '(?i)([\\/]Users[\\/])[^\\/]+', '$1<USER>')
    $safe = [regex]::Replace($safe, '(?i)([\\/]Profiles[\\/])[^\\/]+', '$1<USER>')
    return $safe
}

function Get-PendingRenameAnalysis([string[]]$Operations, [string]$UserProfile) {
    $values = @($Operations)
    $entries = New-Object System.Collections.Generic.List[object]
    $relevantCount = 0
    for ($index = 0; $index -lt $values.Count; $index += 2) {
        $source = [string]$values[$index]
        $destination = if (($index + 1) -lt $values.Count) { [string]$values[$index + 1] } else { '' }
        $sourceClass = Get-PendingPathClassification $source
        $destinationClass = if ([string]::IsNullOrWhiteSpace($destination)) { 'unknown' } else { Get-PendingPathClassification $destination }
        $classes = New-Object System.Collections.Generic.List[string]
        foreach ($className in @($sourceClass, $destinationClass)) {
            if ($className -ne 'unknown' -and -not $classes.Contains($className)) { $classes.Add($className) }
        }
        $entryClass = if ($classes.Count -eq 0) { 'unknown' } elseif ($classes.Count -eq 1) { $classes[0] } else { 'mixed' }
        $relevant = ($classes.Contains('WSL') -or $classes.Contains('virtualization'))
        if ($relevant) { $relevantCount++ }
        $entries.Add([ordered]@{
            index = [int]($entries.Count + 1)
            source = Protect-PendingPath $source $UserProfile
            destination = Protect-PendingPath $destination $UserProfile
            sourceClassification = $sourceClass
            destinationClassification = $destinationClass
            component = $entryClass
            relevantToWsl = [bool]$relevant
        })
    }
    $counts = [ordered]@{}
    foreach ($entry in $entries) {
        if (-not $counts.Contains($entry.component)) { $counts[$entry.component] = 0 }
        $counts[$entry.component]++
    }
    return [ordered]@{
        rawPathCount = [int]$values.Count
        entryCount = [int]$entries.Count
        malformedOddPathCount = [bool](($values.Count % 2) -ne 0)
        relevantEntryCount = [int]$relevantCount
        relevantToWsl = [bool]($relevantCount -gt 0)
        componentCounts = $counts
        entries = [object[]]$entries.ToArray()
    }
}

function Get-RebootGateState($CbsPending, $WindowsUpdatePending, $PendingRenameReadStatus, $PendingRenameAnalysis) {
    $reasons = New-Object System.Collections.Generic.List[string]
    if ($CbsPending -eq $true) { $reasons.Add('CBS_REBOOT_PENDING') }
    if ($WindowsUpdatePending -eq $true) { $reasons.Add('WINDOWS_UPDATE_REBOOT_REQUIRED') }
    if ($PendingRenameReadStatus -eq 'READ' -and $PendingRenameAnalysis.relevantToWsl) { $reasons.Add('WSL_RELATED_PENDING_RENAME') }
    $pendingRename = if ($PendingRenameReadStatus -ne 'READ') { $null } else { [bool]($PendingRenameAnalysis.entryCount -gt 0) }
    $relevant = if ($PendingRenameReadStatus -ne 'READ') { $null } else { [bool]$PendingRenameAnalysis.relevantToWsl }
    $hardBlocker = if ($reasons.Count -gt 0) { $true }
                   elseif ($CbsPending -eq $false -and $WindowsUpdatePending -eq $false -and $PendingRenameReadStatus -eq 'READ') { $false }
                   else { $null }
    $classification = if ($hardBlocker -eq $true) { 'BLOCKED' }
                      elseif ($hardBlocker -eq $false -and $pendingRename -eq $true) { 'REBOOT_ADVISORY_ONLY' }
                      elseif ($hardBlocker -eq $false) { 'CLEAR' }
                      else { 'UNKNOWN' }
    return [ordered]@{
        cbs = $CbsPending
        windowsUpdate = $WindowsUpdatePending
        pendingFileRenameOperations = $pendingRename
        pendingFileRenameEntryCount = if ($PendingRenameReadStatus -eq 'READ') { [int]$PendingRenameAnalysis.entryCount } else { $null }
        pendingFileRenameRelevantToWsl = $relevant
        pendingFileRename = $PendingRenameAnalysis
        hardBlocker = $hardBlocker
        classification = $classification
        reasons = [string[]]$reasons.ToArray()
    }
}

function Get-WslInstallCase([bool]$RuntimeInstalled, [string]$RegistryReadStatus, [int]$RegistryDistroCount, [int]$WslStatusExitCode, [int]$DefaultVersion, [int]$WslListExitCode, [bool]$ListConfirmsNoDistro, [int[]]$UbuntuVersions) {
    if (-not $RuntimeInstalled) { return 'A' }
    if ($RegistryReadStatus -eq 'READ' -and $RegistryDistroCount -eq 0 -and $WslStatusExitCode -eq 0 -and $DefaultVersion -in @(1, 2) -and $ListConfirmsNoDistro) { return 'B' }
    if ($WslListExitCode -ne 0) { return 'UNKNOWN' }
    if (@($UbuntuVersions | Where-Object { $_ -eq 2 }).Count -gt 0) { return 'C' }
    if (@($UbuntuVersions | Where-Object { $_ -eq 1 }).Count -gt 0) { return 'D' }
    return 'B'
}
