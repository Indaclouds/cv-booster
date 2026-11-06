# Tests the installer on a clean, throwaway Windows (Windows Sandbox, everything is wiped on close).
# Writes test-installation.wsb with the paths of THIS project (wherever it is), then opens it.
# Requires: the Windows Sandbox feature turned on, installer built in .dev\dist.
# Usage: powershell -ExecutionPolicy Bypass -File .dev\sandbox\tester-installation.ps1
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
