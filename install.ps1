# ============================================================
# Multi-Clicker - Script d'installation complet
# Telecharge le depot GitHub, installe les dependances Python,
# et cree un raccourci sur le Bureau.
# ============================================================

$ErrorActionPreference = "Stop"

$RepoUser = "PolarAct"            # <-- ton pseudo GitHub
$RepoName = "multi-clicker"       # <-- le nom de ton depot
$Branch   = "main"

$InstallDir   = "$env:USERPROFILE\MultiClicker"
$ZipUrl       = "https://github.com/$RepoUser/$RepoName/archive/refs/heads/$Branch.zip"
$ZipPath      = "$env:TEMP\multiclicker_install.zip"
$ExtractPath  = "$env:TEMP\multiclicker_extract"

Write-Host "=== Installation de Multi-Clicker ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Telechargement depuis GitHub..."
Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath

if (Test-Path $ExtractPath) { Remove-Item $ExtractPath -Recurse -Force }
Expand-Archive -Path $ZipPath -DestinationPath $ExtractPath -Force

# Le zip GitHub extrait toujours dans un sous-dossier "NomDuDepot-branche"
$SourceFolder = Join-Path $ExtractPath "$RepoName-$Branch"

if (-not (Test-Path $SourceFolder)) {
    Write-Host "Erreur : dossier attendu introuvable ($SourceFolder)." -ForegroundColor Red
    Write-Host "Verifie que RepoUser / RepoName / Branch sont corrects dans ce script."
    Read-Host "Appuie sur Entree pour fermer"
    exit 1
}

if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }
New-Item -ItemType Directory -Path $InstallDir | Out-Null
Copy-Item "$SourceFolder\*" -Destination $InstallDir -Recurse -Force

Write-Host "Fichiers installes dans $InstallDir"
Write-Host ""
Write-Host "Verification de Python..."

$PythonCmd = $null
foreach ($cmd in @("python", "py")) {
    try {
        $v = & $cmd --version 2>&1
        if ($v -match "Python") {
            $PythonCmd = $cmd
            break
        }
    } catch {}
}

if (-not $PythonCmd) {
    Write-Host ""
    Write-Host "Python n'est pas installe. Tentative d'installation automatique via winget..." -ForegroundColor Yellow
    $wingetOk = $false
    try {
        winget --version | Out-Null
        winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
        $wingetOk = $true
    } catch {
        $wingetOk = $false
    }

    if ($wingetOk) {
        # Rafraichir le PATH de la session courante pour detecter le python fraichement installe
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        Start-Sleep -Seconds 3
        foreach ($cmd in @("python", "py")) {
            try {
                $v = & $cmd --version 2>&1
                if ($v -match "Python") {
                    $PythonCmd = $cmd
                    break
                }
            } catch {}
        }
    }

    if (-not $PythonCmd) {
        Write-Host ""
        Write-Host "Installation automatique impossible sur ce PC (winget indisponible ou echec)." -ForegroundColor Yellow
        Write-Host "Ouverture de la page de telechargement Python..."
        Start-Process "https://www.python.org/downloads/"
        Write-Host ""
        Write-Host "IMPORTANT : lors de l'installation, coche bien 'Add Python to PATH'." -ForegroundColor Yellow
        Write-Host "Une fois Python installe, relance ce script d'installation."
        Read-Host "Appuie sur Entree pour fermer"
        exit 0
    }
    Write-Host "Python installe automatiquement avec succes." -ForegroundColor Green
}

Write-Host "Python detecte : $PythonCmd"
Write-Host ""
Write-Host "Installation des dependances (pynput, ttkbootstrap, requests)..."
& $PythonCmd -m pip install --upgrade pip --quiet
& $PythonCmd -m pip install -r "$InstallDir\requirements.txt"

Write-Host ""
Write-Host "Creation du raccourci sur le Bureau..."
$WshShell = New-Object -ComObject WScript.Shell
$Desktop = $WshShell.SpecialFolders("Desktop")
$Shortcut = $WshShell.CreateShortcut("$Desktop\Wel's Toolbox.lnk")
$Shortcut.TargetPath = "$InstallDir\Lancer_MultiClicker.bat"
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.IconLocation = "$InstallDir\icon.ico"
$Shortcut.Description = "Lancer Wel's Toolbox"
$Shortcut.Save()

Write-Host ""
Write-Host "=== Installation terminee ! ===" -ForegroundColor Green
Write-Host "Un raccourci 'Multi-Clicker' a ete cree sur le Bureau."
Write-Host "Lancement de l'application..."
Start-Sleep -Seconds 2
Start-Process "$InstallDir\Lancer_MultiClicker.bat"
