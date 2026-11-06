"""CV Booster entry point (shortcut target). .pyw extension: run by pythonw, no console.

Starts TWO separate programs (see fenetre.py):
  1. the server (serveur.py), if it isn't already running;
  2. the window (fenetre.py), in this process.

Program and data are kept apart, as in any installed application:
  - the PROGRAM: this file's folder (installed in AppData\\Local\\Programs\\CV Booster);
  - the DATA: resources, CVs, working files, agents and Skills (Documents\\CV Booster).
The data folder comes from config.json (written by the installer); failing that (development
build), it is the program's parent folder. It is passed to both programs (CVB_DONNEES).
"""
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent
PORT = int(os.environ.get("CVB_PORT", 8765))  # another port: tests only
ADRESSE = f"http://127.0.0.1:{PORT}"


def dossier_donnees() -> Path:
    if os.environ.get("CVB_DONNEES"):
        return Path(os.environ["CVB_DONNEES"])
    try:
        conf = json.loads((APP / "config.json").read_text(encoding="utf-8-sig"))
        if conf.get("donnees"):
            return Path(conf["donnees"])
    except (OSError, ValueError):
        pass
    return APP.parent  # development build: data sits next to the program


def _empreinte(f: Path) -> str:
    return hashlib.sha256(f.read_bytes()).hexdigest()


def synchroniser_claude(modele: Path, dest: Path) -> None:
    """Original agents and Skills (shipped with the program) → data folder, where Claude works.
    A file is copied if missing, or replaced with the new version if the user has NOT modified it
    since the last copy. The user's edits (Coulisses: « modifiez un agent ») are kept.
    The .origine.json registry records the hash of each file as it was copied."""
    registre_f = dest / ".origine.json"
    try:
        registre = json.loads(registre_f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        registre = {}
    change = False
    for src in modele.rglob("*"):
        if not src.is_file() or "__pycache__" in src.parts:
            continue
        rel = src.relative_to(modele).as_posix()
        cible = dest / rel
        neuf = _empreinte(src)
        if not cible.is_file():
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, cible)
        elif registre.get(rel) == neuf:
            continue  # nothing new
        else:
            actuel = _empreinte(cible)
            if actuel != neuf and registre.get(rel) not in (None, actuel):
                continue  # modified by the user: keep their version
            if actuel != neuf and rel in registre:
                shutil.copy2(src, cible)  # untouched since the last copy: new version
            elif rel not in registre and actuel != neuf:
                continue  # unknown origin (older install): play safe, keep it
        registre[rel] = neuf
        change = True
    if change:
        registre_f.write_text(json.dumps(registre, indent=1), encoding="utf-8")


def preparer_donnees(donnees: Path) -> None:
    """Launch of an installed version: creates the data folder and updates the original agents and
    Skills there (they must be in the folder Claude works in, and stay editable)."""
    for d in ("ressources/design", "CV", ".cv-booster"):
        (donnees / d).mkdir(parents=True, exist_ok=True)
    modele = APP / "projet" / ".claude"
    if modele.is_dir():
        try:
            synchroniser_claude(modele, donnees / ".claude")
        except OSError:
            pass  # file locked…: retry on next launch
    for cache in (".claude", ".cv-booster"):  # technical folders hidden in Explorer
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(donnees / cache), 0x2)  # FILE_ATTRIBUTE_HIDDEN
        except Exception:  # noqa: BLE001
            pass


def serveur_pret() -> bool:
    try:
        urllib.request.urlopen(ADRESSE + "/api/etat", timeout=1)
        return True
    except Exception:  # noqa: BLE001
        return False


DONNEES = dossier_donnees()
os.environ["CVB_DONNEES"] = str(DONNEES)  # passed to the server and the window
preparer_donnees(DONNEES)

if os.environ.get("CVB_SANS_FENETRE"):  # tests: the server alone, in this process
    sys.argv = [str(APP / "serveur.py"), "--sans-navigateur"]
    runpy.run_path(str(APP / "serveur.py"), run_name="__main__")
    sys.exit()

if not serveur_pret():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pythonw if pythonw.is_file() else sys.executable), str(APP / "serveur.py"), "--sans-navigateur"],
                     cwd=DONNEES, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x00000200)  # + new process group
    for _ in range(100):  # up to 10 s
        if serveur_pret():
            break
        time.sleep(0.1)

sys.path.insert(0, str(APP))
import fenetre  # noqa: E402

fenetre.ouvrir(ADRESSE)
