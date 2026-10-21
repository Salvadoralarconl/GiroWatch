param([ValidateSet('run','restart','status')][string]$Action,[string]$AdapterPath,
    [string]$Executable,[string]$WorkingFolder,[string]$ProcessName,[string]$WindowTitle,
    [string]$MenuName,[string]$RunName,[int]$CloseTimeout=10)
$ErrorActionPreference = 'Stop'
$camExecutable = $Executable
$camDirectory = $WorkingFolder
function Find-Cam {
    @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -ieq $camExecutable
    })
}
try {
    $instances = @(Find-Cam)
    if ($Action -eq 'status') {
        $display = ''
        if ($instances.Count -eq 1 -and $instances[0].MainWindowTitle -eq $WindowTitle) {
            Add-Type -AssemblyName UIAutomationClient
            $root = [System.Windows.Automation.AutomationElement]::FromHandle($instances[0].MainWindowHandle)
            foreach ($element in $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)) {
                $text = $element.Current.Name
                if ($text -match '(?i)waiting\s+\d{2}:\d{2}:\d{2}|INTERFACE RUNNING!') { $display=$text; break }
            }
        }
        @{running=($instances.Count -gt 0);display=$display} | ConvertTo-Json -Compress
        exit 0
    }
    if ($instances.Count -gt 1) { throw 'Multiple local Cam instances are open. Close extras first.' }
    if ($Action -eq 'restart') {
        if ($instances.Count -eq 1) {
            $camProcess = $instances[0]
            if (-not $camProcess.CloseMainWindow()) { throw 'Cam did not accept a normal close request. No force-close was attempted.' }
            if (-not $camProcess.WaitForExit($CloseTimeout*1000)) { throw 'The application has not exited. No second copy was started.' }
        }
        if (-not (Test-Path -LiteralPath $camExecutable)) { throw 'The configured Cam executable is unavailable.' }
        Start-Process -FilePath $camExecutable -WorkingDirectory $camDirectory | Out-Null
        $deadline = [DateTime]::UtcNow.AddSeconds(8)
        do {
            Start-Sleep -Milliseconds 200
            $opened = @(Find-Cam | Where-Object { $_.MainWindowHandle -ne 0 })
        } while ($opened.Count -eq 0 -and [DateTime]::UtcNow -lt $deadline)
        if ($opened.Count -ne 1) { throw 'Cam was launched but its window could not be confirmed. Check it before retrying.' }
    } else {
        if ($instances.Count -ne 1) { throw 'Cam is closed. Open it or use Restart first.' }
        if ($instances[0].MainWindowTitle -ne $WindowTitle) { throw 'The window title does not match the saved control profile. No action was sent.' }
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes
        $window = [System.Windows.Automation.AutomationElement]::FromHandle($instances[0].MainWindowHandle)
        if (-not $window) { throw 'Cam does not expose a controllable window in this Windows session.' }
        $nameProperty = [System.Windows.Automation.AutomationElement]::NameProperty
        $actionsCondition = New-Object System.Windows.Automation.PropertyCondition($nameProperty,'menuStrip1')
        $menu = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$actionsCondition)
        if (-not $menu) { throw 'Cam menu bar could not be found. No action was sent.' }
        if (-not $menu.Current.IsEnabled) { throw 'Cam menu bar is disabled. No action was sent.' }
        Add-Type -AssemblyName Accessibility
        Add-Type -Path $AdapterPath -ReferencedAssemblies Accessibility
        [CamAccessibility]::Run($menu.Current.NativeWindowHandle,$MenuName,$RunName)
    }
    @{ok=$true} | ConvertTo-Json -Compress
} catch {
    @{error=$_.Exception.Message} | ConvertTo-Json -Compress
    exit 1
}
