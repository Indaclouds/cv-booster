"""Fabrique « Installer CV Booster.exe » : une vraie installation Windows, sans prérequis visible.

Usage : python .dev/construire_installeur.py [--sans-compiler] [--sans-tests]
(Les tests de .dev/tester.py sont lancés d'abord : s'ils échouent, rien n'est construit.)

1. Assemble .dev/installeur/staging/ = l'application complète :
     python/        Python « embarquable » officiel (aucune installation sur le PC)
     lib/           pywebview (la fenêtre) et ses dépendances, déjà prêts
     *.py, *.pyw    le programme ; index.html, vendor/, icônes
     projet/.claude les agents et Skills d'origine (copiés dans Documents\\CV Booster au 1er lancement)
     Guide CV Booster.pdf
2. Compile .dev/installeur/cv-booster.iss avec Inno Setup → .dev/dist/Installer CV Booster.exe
"""

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
APP = RACINE / ".app"
DEV = RACINE / ".dev"
STAGING = DEV / "installeur" / "staging"
DIST = DEV / "dist"
PYTHON_EMBED = sorted((DEV / "deps").glob("python-3.13.*-embed-amd64.zip"))[-1]

# Numéro de version : l'augmenter à chaque nouvelle version livrée (l'appli compare les numéros).
VERSION = os.environ.get("CVB_VERSION", "1.4.0")  # (CVB_VERSION : tests de mise à jour uniquement)
# Mises à jour automatiques : dossier en ligne où sont déposés « version.json » et l'installeur. Par défaut,
# la dernière release GitHub du projet. CVB_MAJ_DOSSIER="" (vide) = pas de vérification des mises à jour.
MAJ_DOSSIER = os.environ.get("CVB_MAJ_DOSSIER", "https://github.com/Indaclouds/cv-booster/releases/latest/download")
NOM_PUBLIE = "Installer-CV-Booster.exe"  # nom en ligne : GitHub remplace les espaces des fichiers par des points
CHANGELOG = RACINE / "CHANGELOG.md"


def verifier_changelog() -> None:
    """Arrête tout si VERSION n'a pas sa section dans CHANGELOG.md (onglet Nouveautés de l'appli)."""
    texte = CHANGELOG.read_text(encoding="utf-8")
    section = re.search(rf"^## {re.escape(VERSION)}\b.*?\n(.*?)(?=^## |\Z)", texte, re.M | re.S)
    if not section:
        sys.exit(f"CHANGELOG.md : ajoutez d'abord une section « ## {VERSION} (<date>) » avec ses nouveautés.")
    if "préparation" in section.group(0).splitlines()[0]:
        print(f"Attention : la section {VERSION} de CHANGELOG.md est encore « en préparation » (mettre la date "
              "avant de publier).")

FICHIERS_APP = ["serveur.py", "services.py", "fenetre.py", "lancer.pyw", "index.html", "icone.ico", "icone.png",
                "prerequis.ps1"]


def assembler() -> None:
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir(parents=True)
    with zipfile.ZipFile(PYTHON_EMBED) as z:          # 1. Python embarqué
        z.extractall(STAGING / "python")
    shutil.copytree(APP / "lib", STAGING / "lib",     # 2. la fenêtre (pywebview), déjà installée
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "bin"))
    for f in FICHIERS_APP:                            # 3. le programme
        shutil.copy2(APP / f, STAGING / f)
    shutil.copytree(APP / "vendor", STAGING / "vendor")
    for d in ("agents", "skills"):                    # 4. agents et Skills d'origine
        shutil.copytree(RACINE / ".claude" / d, STAGING / "projet" / ".claude" / d,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(CHANGELOG, STAGING / CHANGELOG.name)  # l'onglet « Nouveautés »
    shutil.copy2(RACINE / "LICENSE", STAGING / "LICENSE.txt")  # MIT : la licence accompagne le programme
    guide = DEV / "guide" / "Guide CV Booster.pdf"    # 5. le guide
    if guide.is_file():
        shutil.copy2(guide, STAGING / guide.name)
    maj_url = f"{MAJ_DOSSIER.rstrip('/')}/version.json" if MAJ_DOSSIER else ""
    (STAGING / "version.json").write_text(json.dumps({"version": VERSION, "maj_url": maj_url}), encoding="utf-8")
    taille = sum(f.stat().st_size for f in STAGING.rglob("*") if f.is_file()) // (1024 * 1024)
    print(f"staging : {sum(1 for f in STAGING.rglob('*') if f.is_file())} fichiers, {taille} Mo")


def compiler() -> None:
    iscc = next((p for p in (Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
                             Path.home() / r"AppData\Local\Programs\Inno Setup 6\ISCC.exe") if p.is_file()), None)
    if not iscc:
        sys.exit("Inno Setup introuvable : winget install JRSoftware.InnoSetup")
    if not (DEV / "installeur" / "panneau-164.bmp").is_file():  # images de l'assistant (une seule fois)
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(DEV / "installeur" / "images.ps1")], check=True)
    res = subprocess.run([str(iscc), "/Q", f"/DAppVersion={VERSION}", str(DEV / "installeur" / "cv-booster.iss")],
                         capture_output=True, text=True)
    if res.returncode:
        sys.exit(res.stdout[-2000:] + res.stderr[-2000:])
    exe = DIST / "Installer CV Booster.exe"
    print(f"{exe} ({exe.stat().st_size // (1024 * 1024)} Mo), version {VERSION}")
    if MAJ_DOSSIER:  # à publier ensemble (ex. dans une release GitHub) : version.json + l'installeur
        shutil.copy2(exe, DIST / NOM_PUBLIE)
        (DIST / "version.json").write_text(json.dumps({
            "version": VERSION, "url": f"{MAJ_DOSSIER.rstrip('/')}/{NOM_PUBLIE}"},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"À publier dans {MAJ_DOSSIER} : {DIST / 'version.json'} et {DIST / NOM_PUBLIE}")


if __name__ == "__main__":
    verifier_changelog()  # vérifie dès le début que la version a sa section dans CHANGELOG.md
    if "--sans-tests" not in sys.argv:  # aucune version ne part chez elle si un test échoue
        if subprocess.run([sys.executable, str(DEV / "tester.py")]).returncode:
            sys.exit("Tests en échec : installeur non construit (voir ci-dessus).")
    assembler()
    if "--sans-compiler" not in sys.argv:
        compiler()
