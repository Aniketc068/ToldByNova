$HOME_PATH = "C:\Users\chatu\YouTubeProject"
$OFFICE_PATH = "D:\New folder (6)"

if (Test-Path $HOME_PATH) {
    $PROJECT = $HOME_PATH
} else {
    $PROJECT = $OFFICE_PATH
}

$DOC_ID = "1G0yen3WFAuZS1OqL1bFy0LTu6XH9-2JKol6j8Rx_zuQ"
$CHECK_INTERVAL = 30
$LOCK_FILE = "$PROJECT\data\watcher.lock"
$BOT_SCRIPT = "telegram_automation.py"

$SYSTEMS = @{
    "HOME"   = @("192.168.1.64", "192.168.1.72")
    "OFFICE" = @("192.168.1.10", "192.168.56.1")
}

# --- Prevent multiple watcher instances ---
if (Test-Path $LOCK_FILE) {
    $oldPid = (Get-Content $LOCK_FILE -ErrorAction SilentlyContinue).Trim()
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        exit 0
    }
}
$PID | Out-File -FilePath $LOCK_FILE -Force

function Get-MySystemName {
    $localIPs = @()
    try {
        $nets = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName())
        foreach ($n in $nets) {
            if ($n.AddressFamily -eq 'InterNetwork' -and $n.ToString() -ne '127.0.0.1') {
                $localIPs += $n.ToString()
            }
        }
    } catch {}
    foreach ($sysName in $SYSTEMS.Keys) {
        foreach ($ip in $SYSTEMS[$sysName]) {
            if ($localIPs -contains $ip) {
                return $sysName
            }
        }
    }
    return "UNKNOWN"
}

function Get-DocStatus {
    $url = "https://docs.google.com/document/d/$DOC_ID/export?format=txt"
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10 -UserAgent "Mozilla/5.0"
        $text = $response.Content -replace '﻿',''
        $text = $text.Trim()
        $status = @{}
        foreach ($line in $text -split "`n") {
            $line = $line.Trim()
            if ($line -match '^(\w+)\s*[=:]\s*(\w+)') {
                $status[$Matches[1].ToUpper()] = $Matches[2].ToUpper()
            }
        }
        return $status
    } catch {
        return $null
    }
}

function Get-BotProcess {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        if ($p.CommandLine -and $p.CommandLine -like "*$BOT_SCRIPT*") {
            return $p
        }
    }
    return $null
}

function Stop-ExistingBot {
    $found = $false
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        if ($p.CommandLine -and $p.CommandLine -like "*$BOT_SCRIPT*") {
            try { Stop-Process -Id $p.ProcessId -Force -Confirm:$false } catch {}
            $found = $true
        }
    }
    return $found
}

function Start-Bot {
    $scriptPath = "$PROJECT\start_bot.ps1"
    if (Test-Path $scriptPath) {
        Start-Process powershell.exe -ArgumentList "-ExecutionPolicy","Bypass","-WindowStyle","Hidden","-File",$scriptPath -WindowStyle Hidden
        return $true
    }
    return $false
}

$myName = Get-MySystemName
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$ts] Watcher started | System: $myName | Project: $PROJECT | PID: $PID"

while ($true) {
    Start-Sleep -Seconds $CHECK_INTERVAL
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    $status = Get-DocStatus
    if ($null -eq $status) {
        continue
    }

    $myStatus = $status[$myName]
    $botProc = Get-BotProcess

    if ($myStatus -eq "ON" -and $null -eq $botProc) {
        Start-Sleep -Seconds 5
        if ($null -ne (Get-BotProcess)) { continue }
        Write-Host "[$ts] $myName=ON but bot not running -> Starting bot..."
        $started = Start-Bot
        if ($started) {
            Write-Host "[$ts] Bot started. Waiting 60s before next check..."
            Start-Sleep -Seconds 60
        }
    }
    elseif ($myStatus -eq "OFF" -and $null -ne $botProc) {
        Write-Host "[$ts] $myName=OFF -> Stopping bot (PID $($botProc.ProcessId))..."
        Stop-ExistingBot
    }
}
