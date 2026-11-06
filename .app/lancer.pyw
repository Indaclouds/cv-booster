"""Point d'entrée de CV Booster (cible des raccourcis). Extension .pyw : lancé par pythonw, sans console.

Démarre DEUX programmes séparés (voir fenetre.py) :
  1. le serveur (serveur.py), s'il ne tourne pas déjà ;
  2. la fenêtre (fenetre.py), dans ce processus-ci.

Programme et données sont séparés, comme dans toute application installée :
  - le PROGRAMME : le dossier de ce fichier (installé dans AppData\\Local\\Programs\\CV Booster) ;
  - les DONNÉES : ressources, CV, fichiers de travail, agents et Skills (Documents\\CV Booster).
Le dossier des données est donné par config.json (écrit par l'installeur) ; à défaut (version de
développement), c'est le dossier parent du programme. Il est transmis aux deux programmes (CVB_DONNEES).
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
PORT = int(os.environ.get("CVB_PORT", 8765))  # autre port : tests uniquement
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
    return APP.parent  # version de développement : les données sont à côté du programme


def _empreinte(f: Path) -> str:
    return hashlib.sha256(f.read_bytes()).hexdigest()


def synchroniser_claude(modele: Path, dest: Path) -> None:
    """Agents et Skills d'origine (livrés avec le programme) → dossier des données, où Claude travaille.
    Un fichier est copié s'il manque, ou remplacé par la nouvelle version s'il n'a PAS été modifié par la
    personne depuis la dernière copie. Ses modifications (Coulisses : « modifiez un agent ») sont gardées.
    Le registre .origine.json note l'empreinte de chaque fichier tel qu'il a été copié."""
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
            continue  # rien de nouveau
        else:
            actuel = _empreinte(cible)
            if actuel != neuf and registre.get(rel) not in (None, actuel):
                continue  # modifié par la personne : on garde sa version
            if actuel != neuf and rel in registre:
                shutil.copy2(src, cible)  # pas touché depuis la dernière copie : nouvelle version
            elif rel not in registre and actuel != neuf:
                continue  # origine inconnue (ancienne installation) : prudence, on garde
        registre[rel] = neuf
        change = True
    if change:
        registre_f.write_text(json.dumps(registre, indent=1), encoding="utf-8")


def preparer_donnees(donnees: Path) -> None:
    """Lancement d'une version installée : crée le dossier des données et y met à jour les agents et les
    Skills d'origine (ils doivent être dans le dossier où travaille Claude, et restent modifiables)."""
    for d in ("ressources/design", "CV", ".cv-booster"):
        (donnees / d).mkdir(parents=True, exist_ok=True)
    modele = APP / "projet" / ".claude"
    if modele.is_dir():
        try:
            synchroniser_claude(modele, donnees / ".claude")
        except OSError:
            pass  # fichier verrouillé… : on réessaiera au prochain lancement
    for cache in (".claude", ".cv-booster"):  # dossiers techniques masqués dans l'Explorateur
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
os.environ["CVB_DONNEES"] = str(DONNEES)  # transmis au serveur et à la fenêtre
preparer_donnees(DONNEES)

if os.environ.get("CVB_SANS_FENETRE"):  # tests : le serveur seul, dans ce processus
    sys.argv = [str(APP / "serveur.py"), "--sans-navigateur"]
    runpy.run_path(str(APP / "serveur.py"), run_name="__main__")
    sys.exit()

if not serveur_pret():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pythonw if pythonw.is_file() else sys.executable), str(APP / "serveur.py"), "--sans-navigateur"],
                     cwd=DONNEES, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x00000200)  # + nouveau groupe
    for _ in range(100):  # jusqu'à 10 s
        if serveur_pret():
            break
        time.sleep(0.1)

sys.path.insert(0, str(APP))
import fenetre  # noqa: E402

fenetre.ouvrir(ADRESSE)
