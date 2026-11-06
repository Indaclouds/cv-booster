# Crée les raccourcis « CV Booster » avec l'icône de l'appli. Cible : .app\lancer.pyw (dans le dossier),
# que Windows sait retrouver si le dossier est déplacé ; l'appli réécrit ensuite ses raccourcis.
# Usage : powershell -ExecutionPolicy Bypass -File .app\creer_raccourcis.ps1 [-Bureau | -MajBureau]
param(
    [switch]$Bureau,     # crée aussi le raccourci sur le Bureau (installeur)
    [switch]$MajBureau,  # met à jour celui du Bureau seulement s'il existe (réparation après déplacement)
    [string]$Pythonw     # repli si l'extension .pyw n'est associée à rien : chemin de pythonw.exe
)

$racine  = Split-Path -Parent $PSScriptRoot
$lanceur = Join-Path $PSScriptRoot "lancer.pyw"
$icone   = Join-Path $PSScriptRoot "icone.ico"

# .pyw associé à Python (cas normal avec l'installeur python.org) → cible = le lanceur lui-même.
$associe = [bool](Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\.pyw" -ErrorAction SilentlyContinue)
if (-not $associe) {
    if (-not $Pythonw) { $Pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source }
    if (-not $Pythonw -or -not (Test-Path $Pythonw)) { throw "pythonw.exe introuvable : installer Python depuis python.org." }
}

$dossierBureau = [Environment]::GetFolderPath("Desktop")   # (≠ $Bureau : PowerShell ignore la casse)
$dossiers = @($racine)
if ($Bureau -or ($MajBureau -and (Test-Path (Join-Path $dossierBureau "CV Booster.lnk")))) { $dossiers += $dossierBureau }

$shell = New-Object -ComObject WScript.Shell
foreach ($dossier in $dossiers) {
    $lnk = $shell.CreateShortcut((Join-Path $dossier "CV Booster.lnk"))
    if ($associe) { $lnk.TargetPath = $lanceur; $lnk.Arguments = "" }
    else { $lnk.TargetPath = $Pythonw; $lnk.Arguments = "`"$lanceur`"" }
    $lnk.WorkingDirectory = $racine
    $lnk.IconLocation     = "$icone,0"
    $lnk.Description      = "Votre assistant pour un CV au point"
    $lnk.Save()
    Write-Output "Raccourci : $dossier\CV Booster"
}
