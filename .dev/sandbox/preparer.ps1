# Runs automatically when Windows Sandbox opens (see tester-installation.ps1).
# The Sandbox is a clean Windows... without winget: we install it (method documented by Microsoft),
# then run the installer from .dev\dist, as the user would after downloading it.
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
Write-Host ""
Write-Host "Prêt. Lancement de l'installeur, comme après un téléchargement." -ForegroundColor Green
Start-Process "$bureau\paquet\Installer CV Booster.exe"
Read-Host "Appuie sur Entrée pour fermer cette fenêtre"
