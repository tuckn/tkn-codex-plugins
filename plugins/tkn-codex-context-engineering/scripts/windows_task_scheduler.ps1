[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Install", "Status", "Remove")]
    [string]$Action = "Status",

    [string]$ExecutablePath = "",

    [string]$CodexPath = "",

    [string]$TaskName = "Tkn Codex Session Notes"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-CommandPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [string]$ExplicitPath = ""
    )

    if ($ExplicitPath) {
        $item = Get-Item -LiteralPath $ExplicitPath -ErrorAction Stop
        return $item.FullName
    }

    $command = Get-Command $Name -CommandType Application -ErrorAction Stop | Select-Object -First 1
    return $command.Source
}

function Assert-StandaloneCodex {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ($Path -match "(?i)\\WindowsApps\\") {
        throw "The Codex App WindowsApps executable cannot be used for this scheduled task."
    }

    $version = & $Path --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Codex CLI validation failed: $version"
    }
    return ($version | Out-String).Trim()
}

switch ($Action) {
    "Status" {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $task) {
            [pscustomobject]@{
                TaskName = $TaskName
                Installed = $false
            }
            break
        }
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        [pscustomobject]@{
            TaskName = $TaskName
            Installed = $true
            State = $task.State
            LastRunTime = $info.LastRunTime
            LastTaskResult = $info.LastTaskResult
            NextRunTime = $info.NextRunTime
            Execute = $task.Actions.Execute
            Arguments = $task.Actions.Arguments
        }
        break
    }

    "Remove" {
        if ($PSCmdlet.ShouldProcess($TaskName, "Remove scheduled task")) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
        break
    }

    "Install" {
        $pipelineExecutable = Resolve-CommandPath -Name "tkn-codex-context" -ExplicitPath $ExecutablePath
        $codexExecutable = Resolve-CommandPath -Name "codex" -ExplicitPath $CodexPath
        $codexVersion = Assert-StandaloneCodex -Path $codexExecutable

        $taskAction = New-ScheduledTaskAction `
            -Execute $pipelineExecutable `
            -Argument "session-notes run"
        $trigger = New-ScheduledTaskTrigger -Daily -At 3:00AM
        $settings = New-ScheduledTaskSettingsSet `
            -StartWhenAvailable `
            -RunOnlyIfNetworkAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
            -MultipleInstances IgnoreNew `
            -RestartCount 2 `
            -RestartInterval (New-TimeSpan -Minutes 30)
        $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $principal = New-ScheduledTaskPrincipal `
            -UserId $currentUser `
            -LogonType Interactive `
            -RunLevel Limited
        $definition = New-ScheduledTask `
            -Action $taskAction `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal `
            -Description "Generate unreviewed Codex project session notes from local chat history."

        if ($PSCmdlet.ShouldProcess($TaskName, "Configure the pipeline and register the daily task")) {
            & $pipelineExecutable session-notes configure --codex-bin $codexExecutable
            if ($LASTEXITCODE -ne 0) {
                throw "Pipeline configuration failed with exit code $LASTEXITCODE."
            }
            Register-ScheduledTask -TaskName $TaskName -InputObject $definition -Force | Out-Null
        }

        [pscustomobject]@{
            TaskName = $TaskName
            PipelineExecutable = $pipelineExecutable
            CodexExecutable = $codexExecutable
            CodexVersion = $codexVersion
            Schedule = "Daily 03:00 local time"
            RunOnlyWhenLoggedOn = $true
            WakeToRun = $false
            ExecutionTimeLimit = "04:00:00"
        }
        break
    }
}
