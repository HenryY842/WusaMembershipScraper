$ErrorActionPreference = 'Stop'

$taskName = 'WusaMembershipScraperMonthly'
$scriptPath = [System.Security.SecurityElement]::Escape((Join-Path $PSScriptRoot 'monthly-scrape.ps1'))
$projectPath = [System.Security.SecurityElement]::Escape((Resolve-Path (Join-Path $PSScriptRoot '..')).Path)
$userId = [System.Security.SecurityElement]::Escape("$env:USERDOMAIN\$env:USERNAME")
$powerShellPath = [System.Security.SecurityElement]::Escape((Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'))
$firstRun = (Get-Date -Day 1 -Hour 9 -Minute 0 -Second 0).Date
if ($firstRun -le (Get-Date)) {
    $firstRun = $firstRun.AddMonths(1)
}
$startBoundary = $firstRun.ToString("yyyy-MM-dd'T'09:00:00")
$monthsXml = @('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December' |
    ForEach-Object { "<$($_)/>" }) -join ''

$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Scrape WUSA membership offers, classify with Gemini, geocode locations, and update scraper\offers.json.</Description>
    <URI>\$taskName</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$startBoundary</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonth>
        <DaysOfMonth><Day>1</Day></DaysOfMonth>
        <Months>$monthsXml</Months>
      </ScheduleByMonth>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$userId</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT6H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$powerShellPath</Command>
      <Arguments>-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File &quot;$scriptPath&quot;</Arguments>
      <WorkingDirectory>$projectPath</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

$xmlPath = Join-Path $PSScriptRoot '.monthly-task.xml'
try {
    Set-Content -LiteralPath $xmlPath -Value $taskXml -Encoding Unicode
    & schtasks.exe /Create /TN "\$taskName" /XML $xmlPath /F
    if ($LASTEXITCODE -ne 0) {
        throw "Task Scheduler returned exit code $LASTEXITCODE while registering the monthly task."
    }
}
finally {
    if (Test-Path -LiteralPath $xmlPath -PathType Leaf) {
        Remove-Item -LiteralPath $xmlPath -Force
    }
}

Write-Host "Registered task \$taskName. It runs at 9:00 AM on the first day of each month, as $env:USERNAME, starting $($firstRun.ToString('yyyy-MM-dd'))."
Write-Host 'It runs only in your signed-in Windows session and starts after a missed trigger when the computer is available.'
