# Creates the « CV Booster » shortcuts with the app icon. Target: .app\lancer.pyw (in the folder),
# which Windows can find again if the folder is moved; the app then rewrites its shortcuts.
# Usage: powershell -ExecutionPolicy Bypass -File .app\creer_raccourcis.ps1 [-Bureau | -MajBureau]
param(
    [switch]$Bureau,     # also creates the Desktop shortcut (installer)
    [switch]$MajBureau,  # updates the Desktop one only if it exists (repair after a move)
    [string]$Pythonw     # fallback if .pyw isn't associated with anything: path to pythonw.exe
)

$racine  = Split-Path -Parent $PSScriptRoot
$lanceur = Join-Path $PSScriptRoot "lancer.pyw"
$icone   = Join-Path $PSScriptRoot "icone.ico"

# .pyw associated with Python (normal case with the python.org installer) → target = the launcher itself.
$associe = [bool](Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\.pyw" -ErrorAction SilentlyContinue)
if (-not $associe) {
    if (-not $Pythonw) { $Pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source }
    if (-not $Pythonw -or -not (Test-Path $Pythonw)) { throw "pythonw.exe introuvable : installer Python depuis python.org." }
}

$dossierBureau = [Environment]::GetFolderPath("Desktop")   # (≠ $Bureau: PowerShell is case-insensitive)
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
