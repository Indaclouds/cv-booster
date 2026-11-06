# =====================================================================
#  CV Booster: system components, installed SILENTLY by the installer (hidden window).
#  What the app can't bundle: Claude Code (+ Git, which it needs on Windows) and, for
#  now, the PDF engine (MiKTeX). Python and the window, on the other hand, are bundled with the app.
#  Never blocks the install: anything missing is reported in the app (Accueil).
#  Log: <data>\journal-installation.txt (hidden if all went well).
#  Works with Windows PowerShell 5.1. File is UTF-8 with BOM (accents).
# =====================================================================
param([string]$Donnees, [string]$App)
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$journal = Join-Path $Donnees "journal-installation.txt"
New-Item -ItemType Directory -Force $Donnees | Out-Null
function Note($t) { Add-Content -Path $journal -Value "$(Get-Date -Format 'HH:mm:ss')  $t" -Encoding UTF8 }
Note "Windows $([Environment]::OSVersion.Version) - PowerShell $($PSVersionTable.PSVersion)"

function Rafraichir-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") }
function Premier($chemins) { foreach ($c in $chemins) { if ($c -and (Test-Path $c)) { return (Resolve-Path $c).Path } }; return $null }
function Installer-Winget($id, $nom) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Note "winget absent : $nom non installé"; return }
    Note "installation de $nom…"
    $options = @("-e", "--id", $id, "--source", "winget", "--silent", "--disable-interactivity", "--accept-package-agreements", "--accept-source-agreements")
    # first "for this user" (no Windows permission prompt), otherwise a normal install
    $sortie = winget install @options --scope user 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { $sortie = winget install @options 2>&1 | Out-String }
    Note "winget $nom : code $LASTEXITCODE - $((($sortie -split "`r?`n") | Where-Object { $_ -match '\w' -and $_ -notmatch '[█▒]' } | Select-Object -Last 2) -join ' / ')"
    Rafraichir-Path
}
function Trouver-Claude {
    $liste = @((Get-Command claude -ErrorAction SilentlyContinue).Source, "$env:LOCALAPPDATA\Microsoft\WinGet\Links\claude.exe", "$env:USERPROFILE\.local\bin\claude.exe")
    $liste += Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Anthropic.ClaudeCode*\claude.exe" -Recurse -ErrorAction SilentlyContinue | ForEach-Object FullName
    $liste += Get-ChildItem "$env:USERPROFILE\.vscode\extensions\anthropic.claude-code-*\resources\native-binary\claude.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object FullName
    return Premier $liste
}
function Trouver-GitBash {
    $git = (Get-Command git -ErrorAction SilentlyContinue).Source
    return Premier @("$env:ProgramFiles\Git\bin\bash.exe", "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe", $(if ($git) { Join-Path (Split-Path (Split-Path $git)) "bin\bash.exe" }))
}
function Trouver-MiKTeX {
    $p = (Get-Command pdflatex -ErrorAction SilentlyContinue).Source
    return Premier @("$env:LOCALAPPDATA\Programs\MiKTeX\miktex\bin\x64", "$env:ProgramFiles\MiKTeX\miktex\bin\x64", $(if ($p) { Split-Path $p })) |
        Where-Object { Test-Path (Join-Path $_ "pdflatex.exe") } | Select-Object -First 1
}

# 1. Git (Claude Code needs it on Windows)
if (-not (Trouver-GitBash)) { Installer-Winget "Git.Git" "Git" } else { Note "Git déjà présent" }
# 2. Claude Code
$claude = Trouver-Claude
if (-not $claude) { Installer-Winget "Anthropic.ClaudeCode" "Claude Code"; $claude = Trouver-Claude } else { Note "Claude Code déjà présent" }
Note "Claude Code : $(if ($claude) { $claude } else { 'ABSENT' })"
# 3. PDF engine (MiKTeX, for now)
$miktex = Trouver-MiKTeX
if (-not $miktex) { Installer-Winget "MiKTeX.MiKTeX" "MiKTeX"; $miktex = Trouver-MiKTeX } else { Note "MiKTeX déjà présent" }
if ($miktex) {
    & "$miktex\initexmf.exe" --set-config-value="[MPM]AutoInstall=1" 2>$null | Out-Null   # missing packages: installed automatically
    & "$miktex\miktex.exe" packages update-package-database 2>$null | Out-Null
}
Note "MiKTeX : $(if ($miktex) { $miktex } else { 'ABSENT' })"

# 4. Exact paths for the app (reliable even if PATH isn't up to date)
$conf = @{}
$fconf = Join-Path $App "config.json"
if (Test-Path $fconf) { (Get-Content $fconf -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $conf[$_.Name] = $_.Value } }
if ($claude) { $conf.claude = $claude }
if ($miktex) { $conf.miktex = $miktex }
$conf | ConvertTo-Json | Set-Content $fconf -Encoding UTF8

# 5. PDF engine warm-up: it downloads its fonts now rather than on the first click
if ($miktex) {
    $env:Path = "$miktex;$env:Path"; $tmp = Join-Path $env:TEMP "cvbooster-prechauffe"; New-Item -ItemType Directory -Force $tmp | Out-Null
    $gen = Join-Path $App "projet\.claude\skills\mise-en-page\scripts\generer_cv.py"; $ex = Join-Path $App "projet\.claude\skills\format-cv\cv-exemple.toml"
    [IO.File]::WriteAllText("$tmp\design.toml", "[police]`nfamille = `"lato`"`n[page]`nmise_en_page = `"deux_colonnes`"`n[entete]`nicones = true`nqrcode = `"email`"`nphoto_provisoire = true`n[competences]`naffichage = `"barres`"`n")
    & "$App\python\python.exe" -I $gen --source $ex --variante principal --sortie "$tmp\a" --build "$tmp\ba" 2>&1 | Out-Null
    & "$App\python\python.exe" -I $gen --source $ex --design "$tmp\design.toml" --variante principal --sortie "$tmp\b" --build "$tmp\bb" 2>&1 | Out-Null
    Note "préchauffage : $((Get-ChildItem "$tmp\a\*.pdf", "$tmp\b\*.pdf" -ErrorAction SilentlyContinue).Count) PDF d'essai"
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
$ok = $claude -and $miktex
Note "terminé : $(if ($ok) { 'tout est prêt' } else { 'il manque des composants (voir ci-dessus)' })"
if ($ok) { (Get-Item $journal -Force).Attributes = "Hidden" }
exit 0
