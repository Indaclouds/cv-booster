# =====================================================================
#  CV Booster : installation (lancée par « Installer CV Booster.cmd »)
#  Installe ce qui manque (Python, MiKTeX, Git, Claude Code), connecte le compte Claude,
#  prépare les modèles de CV, crée les raccourcis. Sans risque à relancer : saute ce qui est déjà là.
#  Compatible Windows PowerShell 5.1 (celui de Windows).
# =====================================================================
param(
    [switch]$SansBureau,   # tests : pas de raccourci sur le Bureau
    [switch]$SansPause     # tests : ne pas attendre Entrée à la fin
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$app = $PSScriptRoot
$racine = Split-Path -Parent $app
$total = 6

function Etape($n, $texte) { Write-Host ""; Write-Host "[$n/$total] $texte" -ForegroundColor Cyan }
function Ok($texte) { Write-Host "    OK  $texte" -ForegroundColor Green }
function Info($texte) { Write-Host "    $texte" -ForegroundColor Gray }
function Probleme($texte) { Write-Host "    !   $texte" -ForegroundColor Yellow }

function Rafraichir-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

function Installer-Winget($id, $nom) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget est introuvable. Mets Windows à jour (Microsoft Store > « App Installer »), puis relance."
    }
    Info "Installation de $nom (quelques minutes)..."
    $sortie = winget install -e --id $id --source winget --silent --disable-interactivity `
        --accept-package-agreements --accept-source-agreements 2>&1 | Out-String
    # Dernières lignes seulement (sans les barres de progression) : utiles dans le journal en cas de souci
    $utile = ($sortie -split "`r?`n" | Where-Object { $_ -match '\w' -and $_ -notmatch '[█▒]' } | Select-Object -Last 3) -join " / "
    Write-Host "    winget ($nom) : code $LASTEXITCODE - $utile" -ForegroundColor DarkGray
    Rafraichir-Path
}

function Premier($chemins) {
    foreach ($c in $chemins) { if ($c -and (Test-Path $c)) { return (Resolve-Path $c).Path } }
    return $null
}

function Trouver-Python {
    $candidats = @()
    $candidats += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object FullName
    $candidats += Get-ChildItem "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object FullName
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch "WindowsApps") { $candidats += $cmd.Source }   # pas l'alias du Store
    foreach ($p in $candidats) {
        $ok = & $p -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
        $w = Join-Path (Split-Path $p) "pythonw.exe"
        if ($ok -eq "True" -and (Test-Path $w)) { return @{ python = $p; pythonw = $w } }
    }
    return $null
}

function Trouver-MiKTeX {
    $cmd = Get-Command pdflatex -ErrorAction SilentlyContinue
    $depuisPath = $null
    if ($cmd) { $depuisPath = Split-Path $cmd.Source }
    return Premier @("$env:LOCALAPPDATA\Programs\MiKTeX\miktex\bin\x64", "$env:ProgramFiles\MiKTeX\miktex\bin\x64", $depuisPath) |
        Where-Object { Test-Path (Join-Path $_ "pdflatex.exe") } | Select-Object -First 1
}

function Trouver-Claude {
    $cmd = Get-Command claude -ErrorAction SilentlyContinue
    $liste = @()
    if ($cmd) { $liste += $cmd.Source }
    $liste += "$env:LOCALAPPDATA\Microsoft\WinGet\Links\claude.exe", "$env:USERPROFILE\.local\bin\claude.exe"
    $liste += Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Anthropic.ClaudeCode*\claude.exe" -Recurse -ErrorAction SilentlyContinue | ForEach-Object FullName
    $liste += Get-ChildItem "$env:USERPROFILE\.vscode\extensions\anthropic.claude-code-*\resources\native-binary\claude.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object FullName
    return Premier $liste
}

function Trouver-GitBash {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    $depuisGit = $null
    if ($cmd) { $depuisGit = Join-Path (Split-Path (Split-Path $cmd.Source)) "bin\bash.exe" }
    return Premier @("$env:ProgramFiles\Git\bin\bash.exe", "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe", $depuisGit)
}

# Journal de l'installation : en cas de problème, c'est ce fichier qu'on envoie pour le diagnostic.
$journal = Join-Path $racine "journal-installation.txt"
if (Test-Path $journal) { (Get-Item $journal -Force).Attributes = "Normal" }
Start-Transcript -Path $journal -Force | Out-Null
Write-Host "Windows $([Environment]::OSVersion.Version) - PowerShell $($PSVersionTable.PSVersion) - $(Get-Date -Format 'yyyy-MM-dd HH:mm')" -ForegroundColor DarkGray

try {
    Write-Host ""
    Write-Host "  CV Booster : installation" -ForegroundColor White
    Write-Host "  Ne ferme pas cette fenêtre. Ça peut prendre 5 à 15 minutes la première fois." -ForegroundColor Gray

    # Fichiers téléchargés depuis Internet : Windows les bloque, on les débloque.
    Get-ChildItem $racine -Recurse -Force -File | Unblock-File -ErrorAction SilentlyContinue

    # ------------------------------------------------------------------ 1. Python
    Etape 1 "Python"
    $py = Trouver-Python
    if (-not $py) { Installer-Winget "Python.Python.3.13" "Python"; $py = Trouver-Python }
    if (-not $py) { throw "Python n'a pas pu être installé." }
    Ok "Python prêt"
    # Fenêtre moderne (sans la barre de titre Windows) : pywebview, installé DANS l'appli (.app\lib),
    # sans toucher au Python du système. Non bloquant : sinon, l'appli s'ouvre dans une fenêtre Edge.
    $lib = Join-Path $app "lib"
    if (-not (Test-Path (Join-Path $lib "webview"))) {
        Info "Installation de la fenêtre moderne..."
        $ErrorActionPreference = "Continue"
        & $py.python -m pip install --quiet --disable-pip-version-check --target $lib pywebview 2>&1 | Out-Null
        $ErrorActionPreference = "Stop"
    }
    if (Test-Path (Join-Path $lib "webview")) { Ok "Fenêtre moderne prête" }
    else { Probleme "Fenêtre moderne non installée : CV Booster s'ouvrira dans une fenêtre classique." }

    # ------------------------------------------------------------------ 2. MiKTeX (fabrique les PDF)
    Etape 2 "MiKTeX (fabrique les PDF)"
    $miktex = Trouver-MiKTeX
    if (-not $miktex) { Installer-Winget "MiKTeX.MiKTeX" "MiKTeX"; $miktex = Trouver-MiKTeX }
    if (-not $miktex) { throw "MiKTeX n'a pas pu être installé." }
    & "$miktex\initexmf.exe" --set-config-value="[MPM]AutoInstall=1" 2>$null | Out-Null   # paquets manquants : installés seuls
    & "$miktex\miktex.exe" packages update-package-database 2>$null | Out-Null
    $env:Path = "$miktex;$env:Path"
    Ok "MiKTeX prêt"

    # ------------------------------------------------------------------ 3. Claude Code (+ Git, dont il a besoin)
    Etape 3 "Claude Code (l'assistant)"
    if (-not (Trouver-GitBash)) { Installer-Winget "Git.Git" "Git" }
    $claude = Trouver-Claude
    if (-not $claude) { Installer-Winget "Anthropic.ClaudeCode" "Claude Code"; $claude = Trouver-Claude }
    if (-not $claude) { throw "Claude Code n'a pas pu être installé." }
    Ok "Claude Code prêt"

    # ------------------------------------------------------------------ 4. Connexion au compte Claude
    Etape 4 "Connexion à ton compte Claude"
    $statut = (& $claude auth status --json 2>$null | Out-String | ConvertFrom-Json -ErrorAction SilentlyContinue)
    if (-not ($statut -and $statut.loggedIn)) {
        Info "Une page va s'ouvrir dans ton navigateur : connecte-toi avec ton compte Claude (forfait Pro),"
        Info "puis reviens ici."
        & $claude auth login --claudeai
        $statut = (& $claude auth status --json 2>$null | Out-String | ConvertFrom-Json -ErrorAction SilentlyContinue)
    }
    if ($statut -and $statut.loggedIn) {
        Ok "Compte connecté"   # (pas d'adresse e-mail dans le journal : il peut être envoyé pour un diagnostic)
        if ($statut.subscriptionType -and $statut.subscriptionType -notin @("pro", "max", "team", "enterprise")) {
            Probleme "Ton compte n'a pas de forfait Pro : les actions de l'assistant risquent de ne pas marcher."
        }
    } else {
        Probleme "Connexion non faite. Tu pourras la faire plus tard depuis CV Booster (bouton « Me connecter »)."
    }

    # ------------------------------------------------------------------ 5. Modèles de CV (téléchargement des polices, etc.)
    Etape 5 "Préparation des modèles de CV"
    Info "Téléchargement des éléments de mise en page (une seule fois)..."
    $tmp = Join-Path $env:TEMP "cvbooster-prechauffe"
    $gen = Join-Path $racine ".claude\skills\mise-en-page\scripts\generer_cv.py"
    $exemple = Join-Path $racine ".claude\skills\format-cv\cv-exemple.toml"
    New-Item -ItemType Directory -Force $tmp | Out-Null
    [IO.File]::WriteAllText("$tmp\design.toml", "[police]`nfamille = `"lato`"`n[page]`nmise_en_page = `"deux_colonnes`"`n[entete]`nicones = true`nqrcode = `"email`"`nphoto_provisoire = true`n[competences]`naffichage = `"barres`"`n")
    # Étape non bloquante : en cas d'échec, la première génération sera seulement plus lente.
    $ErrorActionPreference = "Continue"
    & $py.python -I $gen --source $exemple --variante principal --sortie "$tmp\a" --build "$tmp\ba" 2>&1 | Out-Null
    & $py.python -I $gen --source $exemple --design "$tmp\design.toml" --variante principal --sortie "$tmp\b" --build "$tmp\bb" 2>&1 | Out-Null
    $ErrorActionPreference = "Stop"
    if ((Get-ChildItem "$tmp\a\*.pdf", "$tmp\b\*.pdf" -ErrorAction SilentlyContinue).Count -ge 2) { Ok "Modèles prêts" }
    else { Probleme "La préparation n'a pas tout téléchargé : la première génération sera juste plus lente." }
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

    # ------------------------------------------------------------------ 6. Raccourcis et rangement
    Etape 6 "Raccourcis"
    @{ python = $py.python; pythonw = $py.pythonw; claude = $claude; miktex = $miktex; racine = $racine } |
        ConvertTo-Json | Set-Content (Join-Path $app "config.json") -Encoding UTF8
    $args6 = @{ Pythonw = $py.pythonw }
    if (-not $SansBureau) { $args6.Bureau = $true }
    & (Join-Path $app "creer_raccourcis.ps1") @args6 | Out-Null
    foreach ($d in "ressources", "ressources\design", "CV") { New-Item -ItemType Directory -Force (Join-Path $racine $d) | Out-Null }
    foreach ($cache in ".app", ".claude", ".cv-booster", "Installer CV Booster.cmd") {
        $p = Join-Path $racine $cache
        if (Test-Path $p) { (Get-Item $p -Force).Attributes = (Get-Item $p -Force).Attributes -bor [IO.FileAttributes]::Hidden }
    }
    Ok "Raccourci « CV Booster » créé$(if (-not $SansBureau) { ' (dans le dossier et sur le Bureau)' })"

    Write-Host ""
    Write-Host "  C'est prêt ! Double-clique sur « CV Booster » pour commencer." -ForegroundColor Green
    $code = 0
} catch {
    Write-Host ""
    Write-Host "  L'installation s'est arrêtée : $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  (détail : ligne $($_.InvocationInfo.ScriptLineNumber))" -ForegroundColor DarkGray
    Write-Host "  Vérifie ta connexion Internet et relance « Installer CV Booster »." -ForegroundColor Red
    Write-Host "  Si ça recommence, envoie le fichier « journal-installation.txt » (dans le dossier CV Booster)." -ForegroundColor Yellow
    $code = 1
}
Stop-Transcript | Out-Null
if ($code -eq 0) { (Get-Item $journal -Force).Attributes = "Hidden" }   # tout va bien : on le range
if (-not $SansPause) { Write-Host ""; Read-Host "  Appuie sur Entrée pour fermer" | Out-Null }
exit $code
