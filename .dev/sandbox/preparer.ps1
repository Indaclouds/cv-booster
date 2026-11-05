# Lancé automatiquement à l'ouverture du Bac à sable Windows (voir test-installation.wsb).
# Le Bac à sable est un Windows vierge... sans winget : on l'installe (méthode documentée par Microsoft),
# puis on dépose le paquet CV Booster dézippé sur le Bureau, comme le ferait l'utilisatrice.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$host.UI.RawUI.WindowTitle = "Préparation du test CV Booster"
Write-Host "Préparation du Bac à sable (installation de winget, 2 à 5 minutes)..." -ForegroundColor Cyan
try {
    Install-PackageProvider -Name NuGet -Force -Scope CurrentUser | Out-Null
    Install-Module -Name Microsoft.WinGet.Client -Force -Scope CurrentUser -Repository PSGallery | Out-Null
    Repair-WinGetPackageManager -AllUsers -Force | Out-Null
    Write-Host "winget prêt." -ForegroundColor Green
} catch {
    Write-Host "winget n'a pas pu être installé : $($_.Exception.Message)" -ForegroundColor Red
}

$bureau = [Environment]::GetFolderPath("Desktop")
Expand-Archive -LiteralPath "$bureau\paquet\CV-Booster.zip" -DestinationPath $bureau -Force
Write-Host ""
Write-Host "Prêt. Sur le Bureau : dossier « CV Booster » > double-clic sur « Installer CV Booster »." -ForegroundColor Green
Start-Process explorer.exe "$bureau\CV Booster"
Read-Host "Appuie sur Entrée pour fermer cette fenêtre"
