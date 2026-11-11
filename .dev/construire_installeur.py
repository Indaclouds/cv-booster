"""Builds "Installer CV Booster.exe": a real Windows installer, with no visible prerequisites.

Usage: python .dev/construire_installeur.py [--sans-compiler] [--sans-tests]
(The .dev/tester.py tests run first: if they fail, nothing is built.)

1. Assembles .dev/installeur/staging/ = the full application:
     python/        official "embeddable" Python (nothing installed on the PC)
     lib/           pywebview (the window) and its dependencies, ready to use
     *.py, *.pyw    the program; index.html, vendor/, icons
     projet/.claude the original agents and Skills (copied to Documents\\CV Booster on first launch)
     Guide CV Booster.pdf
2. Compiles .dev/installeur/cv-booster.iss with Inno Setup → .dev/dist/Installer CV Booster.exe
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

# Version number: bump it for every release shipped (the app compares the numbers).
VERSION = os.environ.get("CVB_VERSION", "1.5.0")  # (CVB_VERSION: update tests only)
# Automatic updates: online folder holding "version.json" and the installer. By default,
# the project's latest GitHub release. CVB_MAJ_DOSSIER="" (empty) = no update check.
MAJ_DOSSIER = os.environ.get("CVB_MAJ_DOSSIER", "https://github.com/Indaclouds/cv-booster/releases/latest/download")
NOM_PUBLIE = "Installer-CV-Booster.exe"  # online name: GitHub replaces spaces in file names with dots
CHANGELOG = RACINE / "CHANGELOG.md"


def verifier_changelog() -> None:
    """Stops everything if VERSION has no section in CHANGELOG.md (the app's Nouveautés tab)."""
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
    with zipfile.ZipFile(PYTHON_EMBED) as z:          # 1. embedded Python
        z.extractall(STAGING / "python")
    shutil.copytree(APP / "lib", STAGING / "lib",     # 2. the window (pywebview), already installed
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "bin"))
    for f in FICHIERS_APP:                            # 3. the program
        shutil.copy2(APP / f, STAGING / f)
    shutil.copytree(APP / "vendor", STAGING / "vendor")
    for d in ("agents", "skills"):                    # 4. original agents and Skills
        shutil.copytree(RACINE / ".claude" / d, STAGING / "projet" / ".claude" / d,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(CHANGELOG, STAGING / CHANGELOG.name)  # the "Nouveautés" tab
    shutil.copy2(RACINE / "LICENSE", STAGING / "LICENSE.txt")  # MIT: the license ships with the program
    guide = DEV / "guide" / "Guide CV Booster.pdf"    # 5. the guide
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
    if not (DEV / "installeur" / "panneau-164.bmp").is_file():  # wizard images (only once)
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(DEV / "installeur" / "images.ps1")], check=True)
    res = subprocess.run([str(iscc), "/Q", f"/DAppVersion={VERSION}", str(DEV / "installeur" / "cv-booster.iss")],
                         capture_output=True, text=True)
    if res.returncode:
        sys.exit(res.stdout[-2000:] + res.stderr[-2000:])
    exe = DIST / "Installer CV Booster.exe"
    print(f"{exe} ({exe.stat().st_size // (1024 * 1024)} Mo), version {VERSION}")
    if MAJ_DOSSIER:  # publish together (e.g. in a GitHub release): version.json + the installer
        shutil.copy2(exe, DIST / NOM_PUBLIE)
        (DIST / "version.json").write_text(json.dumps({
            "version": VERSION, "url": f"{MAJ_DOSSIER.rstrip('/')}/{NOM_PUBLIE}"},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"À publier dans {MAJ_DOSSIER} : {DIST / 'version.json'} et {DIST / NOM_PUBLIE}")


if __name__ == "__main__":
    verifier_changelog()  # checks right away that the version has its section in CHANGELOG.md
    if "--sans-tests" not in sys.argv:  # no version reaches her if a test fails
        if subprocess.run([sys.executable, str(DEV / "tester.py")]).returncode:
            sys.exit("Tests en échec : installeur non construit (voir ci-dessus).")
    assembler()
    if "--sans-compiler" not in sys.argv:
        compiler()
