$ErrorActionPreference = "Stop"
$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $env:LOCALAPPDATA "ytpick"
$script = "ytpick_gui.py"
$pkg    = "ytpick"

function Step($t)  { Write-Host ""; Write-Host "==> $t" -ForegroundColor Cyan }
function Ok($t)    { Write-Host "    OK: $t" -ForegroundColor Green }
function Have($c)  { [bool](Get-Command $c -ErrorAction SilentlyContinue) }

function Refresh-Path {
    $m = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $u = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$m;$u"
}

function Winget-Install($id) {
    winget install -e --id $id --accept-source-agreements --accept-package-agreements --silent
    $okCodes = @(0, -1978335189, -1978335135)
    if ($okCodes -notcontains $LASTEXITCODE) {
        throw "winget-Installation von $id fehlgeschlagen (Code $LASTEXITCODE)"
    }
    Refresh-Path
}

function Get-PythonExe {
    $candidates = @()
    if (Have "py") {
        try {
            $p = & py -3 -c "import sys;print(sys.executable)" 2>$null
            if ($p) { $candidates += $p }
        } catch {}
    }
    $candidates += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) {
            $okVer = & $c -c "import sys;print(int(sys.version_info >= (3,10)))" 2>$null
            if ($okVer -eq "1") { return $c }
        }
    }
    return $null
}

try {
    Write-Host "ytpick - Setup" -ForegroundColor White

    if (-not ((Test-Path (Join-Path $here $script)) -and (Test-Path (Join-Path $here $pkg)))) {
        throw "$script und der Ordner $pkg wurden nicht neben dem Installer gefunden. Bitte alle Dateien im selben Ordner lassen."
    }

    Step "Pruefe winget"
    if (-not (Have "winget")) {
        throw "winget fehlt. Installiere 'App-Installer' aus dem Microsoft Store und starte setup.bat erneut."
    }
    Ok "winget gefunden"

    Step "Python (3.10 oder neuer)"
    $py = Get-PythonExe
    if (-not $py) {
        Winget-Install "Python.Python.3.12"
        $py = Get-PythonExe
    }
    if (-not $py) { throw "Python wurde nicht gefunden. Bitte setup.bat nach einem Neustart erneut ausfuehren." }
    & $py -c "import tkinter" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Diese Python-Installation hat kein tkinter (Tcl/Tk). Bitte Python neu installieren und 'tcl/tk' mitinstallieren."
    }
    Ok "$py"

    Step "ffmpeg (Video und Ton zusammenfuegen)"
    if (-not (Have "ffmpeg")) { Winget-Install "Gyan.FFmpeg" }
    if (Have "ffmpeg") { Ok "ffmpeg gefunden" } else { Write-Host "    Hinweis: ffmpeg wird nach einem Neustart des PCs gefunden." -ForegroundColor Yellow }

    Step "deno (JavaScript-Laufzeit fuer YouTube)"
    if (-not (Have "deno")) { Winget-Install "DenoLand.Deno" }
    if (Have "deno") { Ok "deno gefunden" } else { Write-Host "    Hinweis: deno wird nach einem Neustart des PCs gefunden." -ForegroundColor Yellow }

    Step "yt-dlp (neueste Version) und Pillow (Vorschaubilder)"
    & $py -m pip install --upgrade "yt-dlp[default]" pillow
    if ($LASTEXITCODE -ne 0) { throw "pip-Installation von yt-dlp und Pillow fehlgeschlagen." }
    Ok "yt-dlp installiert"

    Step "Programm kopieren und Verknuepfungen anlegen"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item (Join-Path $here $script) (Join-Path $target $script) -Force
    $pkgTarget = Join-Path $target $pkg
    if (Test-Path $pkgTarget) { Remove-Item $pkgTarget -Recurse -Force }
    Copy-Item (Join-Path $here $pkg) $target -Recurse -Force
    $assets = Join-Path $here "assets"
    if (Test-Path $assets) { Copy-Item $assets $target -Recurse -Force }
    $icon = Join-Path $target "assets\icon.ico"
    $pyw = Join-Path (Split-Path $py) "pythonw.exe"
    if (-not (Test-Path $pyw)) { $pyw = $py }
    $ws = New-Object -ComObject WScript.Shell
    $dirs = @(
        [Environment]::GetFolderPath("Desktop"),
        (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs")
    )
    foreach ($d in $dirs) {
        $lnk = $ws.CreateShortcut((Join-Path $d "ytpick.lnk"))
        $lnk.TargetPath = $pyw
        $lnk.Arguments = '"' + (Join-Path $target $script) + '"'
        $lnk.WorkingDirectory = $target
        if (Test-Path $icon) { $lnk.IconLocation = $icon }
        $lnk.Save()
    }
    Ok "Installiert nach $target"
    Ok "Verknuepfung 'ytpick' auf dem Desktop und im Startmenue"

    Write-Host ""
    Write-Host "Fertig! Starte das Tool ueber die Desktop-Verknuepfung 'ytpick'." -ForegroundColor Green
    Write-Host "Tipp: Bei einem Bot-Check in der Oberflaeche unten einen Browser bei 'Cookies' waehlen."
    exit 0
}
catch {
    Write-Host ""
    Write-Host "FEHLER: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
