$HOME_PATH = "C:\Users\chatu\YouTubeProject"
$OFFICE_PATH = "D:\New folder (6)"

if (Test-Path $HOME_PATH) {
    $PROJECT = $HOME_PATH
} else {
    $PROJECT = $OFFICE_PATH
}

$BOT_SCRIPT = "telegram_automation.py"

# Kill any existing bot instance to prevent 409 conflict
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    if ($p.CommandLine -and $p.CommandLine -like "*$BOT_SCRIPT*") {
        try { Stop-Process -Id $p.ProcessId -Force -Confirm:$false } catch {}
    }
}
Start-Sleep -Seconds 2

$env:BOT_TOKEN = "8543070916:AAHxBys1EJzAcXxrxk7Oh6Vi4iG5k-_DNBw"
$env:ADMIN_ID = "758358766"
$env:OLLAMA_API_KEY = "3e001e91f9fa4403abf056290f1ce981.eZrFn_aVYXaTR24EL4AHwjYF"
$env:OLLAMA_MODEL = "gemma4:31b-cloud"
$env:PYTHONUTF8 = "1"

$ffmpegBin = "$PROJECT\ffmpeg\ffmpeg-master-latest-win64-gpl\bin"
if (Test-Path $ffmpegBin) {
    $env:PATH = "$ffmpegBin;$env:PATH"
}

Start-Process python -ArgumentList "-X","utf8","-u","`"$PROJECT\scripts\$BOT_SCRIPT`"" -WorkingDirectory "$PROJECT" -RedirectStandardOutput "$PROJECT\data\bot_stdout.log" -RedirectStandardError "$PROJECT\data\bot_stderr.log" -WindowStyle Hidden
