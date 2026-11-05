"""Crée .dev/dist/CV-Booster.zip : l'application à donner à l'utilisatrice.

Usage : python .dev/empaqueter_appli.py

Contenu : l'interface (.app), les agents (.claude/agents), les Skills (.claude/skills), l'installeur, et les dossiers vides ressources/ et CV/.
Exclus volontairement :
  - .claude/CLAUDE.md : notes de développement. Claude Code le lit à CHAQUE action : ce serait des
    tokens dépensés pour rien sur son forfait.
  - .cv-booster/ (données de test), .dev/, config.json (chemins propres à cette machine), caches Python.
"""

import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
ZIP = RACINE / ".dev" / "dist" / "CV-Booster.zip"
DOSSIER = "CV Booster"  # nom du dossier une fois dézippé

INCLURE = [".app", ".claude/agents", ".claude/skills", "Installer CV Booster.cmd"]
# lib : pywebview, installé par l'installeur sur SA machine (dépend de sa version de Python)
EXCLURE_NOMS = {"__pycache__", "config.json", "lib"}
DOSSIERS_VIDES = ["ressources/", "ressources/design/", "CV/"]

ZIP.parent.mkdir(parents=True, exist_ok=True)
n = 0
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for element in INCLURE:
        chemin = RACINE / element
        fichiers = [chemin] if chemin.is_file() else sorted(p for p in chemin.rglob("*") if p.is_file())
        for f in fichiers:
            if EXCLURE_NOMS & set(f.relative_to(RACINE).parts) or f.suffix == ".pyc":
                continue
            z.write(f, f"{DOSSIER}/{f.relative_to(RACINE).as_posix()}")
            n += 1
    for d in DOSSIERS_VIDES:
        z.writestr(f"{DOSSIER}/{d}", "")
    # Le guide d'utilisation, à la racine (visible dès le dézippage, et après l'installation)
    # Source : .dev/guide/guide.md → PDF via pandoc (voir CLAUDE.md)
    guide = RACINE / ".dev" / "guide" / "Guide CV Booster.pdf"
    if guide.is_file():
        z.write(guide, f"{DOSSIER}/Guide CV Booster.pdf")
        n += 1
    else:
        print("ATTENTION : guide PDF absent (.dev/guide/Guide CV Booster.pdf)")
print(f"{ZIP} : {n} fichiers, {ZIP.stat().st_size // 1024} Ko")
