# Test de l'installation sur un Windows vierge et jetable (Bac à sable Windows, tout est effacé à la fermeture).
# Écrit test-installation.wsb avec les chemins de CE projet (où qu'il soit), puis l'ouvre.
# Prérequis : fonctionnalité Windows « Bac à sable Windows » activée, installeur construit dans .dev\dist.
# Usage : powershell -ExecutionPolicy Bypass -File .dev\sandbox\tester-installation.ps1
$ErrorActionPreference = "Stop"
$ici = $PSScriptRoot
$dist = Join-Path (Split-Path $ici) "dist"
if (-not (Test-Path (Join-Path $dist "Installer CV Booster.exe"))) {
    throw "Installeur introuvable dans $dist : lancez d'abord python .dev\construire_installeur.py"
}
$wsb = @"
<Configuration>
  <MemoryInMB>6144</MemoryInMB>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$dist</HostFolder>
      <SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\paquet</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$ici</HostFolder>
      <SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\outils</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\WDAGUtilityAccount\Desktop\outils\preparer.ps1</Command>
  </LogonCommand>
</Configuration>
"@
$fichier = Join-Path $ici "test-installation.wsb"
[IO.File]::WriteAllText($fichier, $wsb, (New-Object Text.UTF8Encoding $false))
Start-Process $fichier
