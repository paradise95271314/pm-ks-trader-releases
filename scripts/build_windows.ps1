$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Install-BundledPrerequisite {
    param([string]$Name, [string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    Write-Host "Installing bundled $Name ..."
    if ($Name -eq "Python") {
        $p = Start-Process -FilePath $Path -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait -PassThru
    } else {
        $p = Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$Path`" /qn /norestart" -Wait -PassThru
    }
    if ($p.ExitCode -notin @(0, 3010)) { throw "$Name installer failed with exit code $($p.ExitCode)." }
    Refresh-Path
    return $true
}

Write-Host "[1/4] Preparing Python and Node.js build environment"
$Tools = Join-Path $Root "tools"
$null = Install-BundledPrerequisite "Python" (Join-Path $Tools "python-3.12.10-amd64.exe")
$null = Install-BundledPrerequisite "Node.js" (Join-Path $Tools "node-v20.19.3-x64.msi")
$WebViewExe = Join-Path $Tools "MicrosoftEdgeWebView2Setup.exe"
$WebViewInstalled = (Get-ChildItem "$env:ProgramFiles(x86)\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe", "$env:ProgramFiles\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe" -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $WebViewInstalled -and (Test-Path $WebViewExe)) {
    Write-Host "Installing bundled Microsoft Edge WebView2 runtime ..."
    $web = Start-Process -FilePath $WebViewExe -ArgumentList "/silent /install" -Wait -PassThru
    if ($web.ExitCode -notin @(0, 3010)) { throw "WebView2 installer failed with exit code $($web.ExitCode)." }
}
$PythonCommand = $null
$PythonArgs = @()

# Prefer the Windows launcher, but keep trying when a specific version is absent.
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($Version in @("3.12", "3.11", "3.10")) {
        & py "-$Version" -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $PythonCommand = "py"
            $PythonArgs = @("-$Version")
            break
        }
    }
}

if (-not $PythonCommand -and (Get-Command python -ErrorAction SilentlyContinue)) {
    & python -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $PythonCommand = "python"
    }
}

if (-not $PythonCommand) {
    throw "Python 3.10-3.12 was not found. Install Python 3.12 from https://www.python.org/downloads/windows/ and enable 'Add python.exe to PATH', then run this file again."
}

if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js and npm were not found. Install the Node.js 20 LTS Windows Installer from https://nodejs.org/en/download, then close and reopen this window before running the build again."
}

$NodeMajor = [int]((& node --version).TrimStart('v').Split('.')[0])
if ($NodeMajor -lt 18) {
    throw "Node.js 18 or newer is required. Node.js 20 LTS is recommended: https://nodejs.org/en/download"
}

Write-Host "Using Node.js $(& node --version) and npm $(& npm --version)"

$BuildPython = Join-Path $Root ".build-venv\Scripts\python.exe"
if (-not (Test-Path $BuildPython)) {
    if (Test-Path ".build-venv") {
        Remove-Item -Recurse -Force ".build-venv"
    }
    & $PythonCommand @PythonArgs -m venv .build-venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the Python build environment."
    }
}
& $BuildPython -c "import sys; print('Using Python ' + sys.version.split()[0])"
& $BuildPython -m pip install --upgrade pip
& $BuildPython -m pip install -r backend\requirements.txt pyinstaller

Write-Host "[2/4] Building desktop frontend"
Push-Location frontend
$env:DESKTOP_BUILD = "1"
$env:NEXT_PUBLIC_API_URL = ""
npm ci
npm run build
Pop-Location

Write-Host "[3/4] Packaging Windows application"
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $BuildPython -m PyInstaller --noconfirm windows_app.spec

Write-Host "[4/4] Creating installer when Inno Setup is available"
$Inno = @(
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($Inno) {
    & $Inno installer.iss
    Write-Host "Installer: output\PM-KS-Trader-Setup.exe"
} else {
    Write-Host "Inno Setup not found; portable app: dist\PM-KS交易桌面\PM-KS交易桌面.exe"
}
