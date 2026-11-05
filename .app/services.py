"""Fonctions de CV Booster qui n'utilisent PAS l'IA (zéro token), appelées par serveur.py :
historique du CV, suivi des candidatures, agents créés par la personne, mises à jour.

Mêmes dossiers que serveur.py : les données sont dans CVB_DONNEES (voir lancer.pyw).
"""

import json
import os
import re
import shutil
import subprocess
import threading
import time
import tomllib
import unicodedata
import urllib.request
import uuid
from datetime import date, datetime
from pathlib import Path

APP = Path(__file__).resolve().parent
RACINE = Path(os.environ.get("CVB_DONNEES") or APP.parent)
TRAVAIL = RACINE / ".cv-booster"
CV_TOML = TRAVAIL / "cv.toml"
AGENTS = RACINE / ".claude" / "agents"
SKILLS = RACINE / ".claude" / "skills"


def _ecrire_json(chemin: Path, donnees) -> None:
    """Écriture d'un coup (fichier temporaire puis remplacement) : jamais de fichier à moitié écrit."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, chemin)


def _lire_json(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return defaut


# =========================================================================== historique du CV
# Avant chaque tâche d'un agent (et avant un retour en arrière), une copie du CV est rangée ici.
# Les 30 dernières sont gardées ; une copie identique à la précédente n'est pas refaite.
HISTORIQUE = TRAVAIL / "historique"
MAX_ARCHIVES = 30
_VERROU_HIST = threading.Lock()


def archiver_cv(motif: str) -> None:
    if not CV_TOML.is_file():
        return
    with _VERROU_HIST:
        HISTORIQUE.mkdir(parents=True, exist_ok=True)
        archives = sorted(HISTORIQUE.glob("cv-*.toml"))
        contenu = CV_TOML.read_bytes()
        if archives and archives[-1].read_bytes() == contenu:
            return
        nom = f"cv-{datetime.now():%Y%m%d-%H%M%S}.toml"
        (HISTORIQUE / nom).write_bytes(contenu)
        motifs = _lire_json(HISTORIQUE / "motifs.json", {})
        motifs[nom] = motif
        for vieux in archives[:max(0, len(archives) + 1 - MAX_ARCHIVES)]:
            vieux.unlink(missing_ok=True)
            motifs.pop(vieux.name, None)
        _ecrire_json(HISTORIQUE / "motifs.json", motifs)


def historique() -> list[dict]:
    if not HISTORIQUE.is_dir():
        return []
    motifs = _lire_json(HISTORIQUE / "motifs.json", {})
    res = []
    for f in sorted(HISTORIQUE.glob("cv-*.toml"), reverse=True):
        try:
            quand = datetime.strptime(f.stem[3:], "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        res.append({"fichier": f.name, "date": quand.isoformat(timespec="minutes"), "motif": motifs.get(f.name, "")})
    return res


def restaurer_cv(fichier: str) -> None:
    f = HISTORIQUE / Path(fichier).name
    if not (re.fullmatch(r"cv-\d{8}-\d{6}\.toml", f.name) and f.is_file()):
        raise ValueError("Cette version n'existe plus.")
    tomllib.loads(f.read_text(encoding="utf-8-sig"))  # lisible, sinon erreur (et rien n'est touché)
    archiver_cv("Avant un retour en arrière")          # on peut toujours revenir sur le retour
    shutil.copy(f, CV_TOML)


# =========================================================================== suivi des candidatures
CANDIDATURES = TRAVAIL / "candidatures.json"
STATUTS = ["À envoyer", "Envoyée", "Relancée", "Entretien", "Offre reçue", "Refusée", "Abandonnée"]
_CHAMPS = {"id": 16, "entreprise": 120, "poste": 160, "version": 80, "lien": 500, "notes": 2000,
           "date": 10, "statut": 20}


def candidatures() -> list[dict]:
    liste = _lire_json(CANDIDATURES, [])
    return liste if isinstance(liste, list) else []


def enregistrer_candidatures(liste) -> list[dict]:
    """La liste complète, nettoyée (la page renvoie tout à chaque modification : une seule personne)."""
    if not isinstance(liste, list):
        raise ValueError("liste attendue")
    propres = []
    for c in liste[:500]:
        if not isinstance(c, dict):
            continue
        p = {k: str(c.get(k) or "").strip()[:n] for k, n in _CHAMPS.items()}
        if not p["entreprise"]:
            continue
        if p["statut"] not in STATUTS:
            p["statut"] = STATUTS[0]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", p["date"]):
            p["date"] = date.today().isoformat()
        if p["lien"] and not re.match(r"https?://", p["lien"]):
            p["lien"] = ""
        p["id"] = p["id"] or uuid.uuid4().hex[:8]
        propres.append(p)
    _ecrire_json(CANDIDATURES, propres)
    return propres


# =========================================================================== agents créés par la personne
# Coulisses › « Créer un agent » : un formulaire, et ce module écrit le fichier .md à sa place.
OUTILS = {"lire": ["Read"], "modifier": ["Edit"], "web": ["WebSearch", "WebFetch"]}
MODELES = ["sonnet", "haiku", "opus"]


def slug(texte: str) -> str:
    brut = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", brut).strip("-")[:40]


def _une_ligne(texte: str, maxi: int) -> str:
    return re.sub(r"\s+", " ", str(texte or "")).strip()[:maxi]


def creer_agent(d: dict) -> str:
    libelle = _une_ligne(d.get("libelle"), 60)
    nom = slug(libelle)
    if len(nom) < 3:
        raise ValueError("Donne-lui un nom d'au moins 3 lettres.")
    if (AGENTS / f"{nom}.md").exists():
        raise ValueError(f"Un agent « {nom} » existe déjà : choisis un autre nom.")
    description = _une_ligne(d.get("description"), 300)
    consignes = str(d.get("consignes") or "").strip()[:8000]
    if not description or not consignes:
        raise ValueError("Remplis « À quoi il sert » et « Ses consignes ».")
    outils = ["Read"] + [o for cle in ("modifier", "web") if d.get(cle) for o in OUTILS[cle]]
    skills = [s for s in d.get("skills", []) if isinstance(s, str) and (SKILLS / s / "SKILL.md").is_file()]
    modele = d.get("modele") if d.get("modele") in MODELES else "sonnet"
    lignes = ["---", f"name: {nom}", f"description: {description}", f"tools: {', '.join(outils)}",
              f"model: {modele}"]
    if skills:
        lignes.append(f"skills: {', '.join(skills)}")
    droits = ("Tu peux modifier son CV, mais seulement après son accord." if d.get("modifier") else
              "Tu ne peux PAS modifier ses fichiers : tu proposes, elle recopie ce qu'elle garde. "
              "Ne promets jamais de modifier son CV.")
    lignes += [f"libelle: {libelle}", "cree_par: toi", "---", "",
               f"Tu es **{libelle}**, un agent de CV Booster. {droits}", "", consignes, ""]
    AGENTS.mkdir(parents=True, exist_ok=True)
    (AGENTS / f"{nom}.md").write_text("\n".join(lignes), encoding="utf-8")
    return nom


def agent_perso(nom: str) -> bool:
    f = AGENTS / f"{Path(nom).name}.md"
    if not f.is_file():
        return False
    haut = f.read_text(encoding="utf-8-sig", errors="replace").split("---")
    return len(haut) > 2 and re.search(r"^cree_par:\s*toi\s*$", haut[1], re.M) is not None


def supprimer_agent(nom: str) -> None:
    if not agent_perso(nom):
        raise ValueError("Seuls les agents que tu as créés peuvent être supprimés ici.")
    (AGENTS / f"{Path(nom).name}.md").unlink()


# =========================================================================== mises à jour
# version.json (écrit par construire_installeur.py) : {"version": "1.2.0", "maj_url": "https://…/version.json"}.
# L'adresse maj_url renvoie {"version": "1.3.0", "url": "https://…/Installer CV Booster.exe", "notes": "…"}.
# Sans maj_url (ou en développement) : pas de vérification.
_MAJ = {"verifie": 0.0, "info": None}


def version_locale() -> dict:
    v = _lire_json(APP / "version.json", {})
    return {"version": str(v.get("version") or "dev"), "maj_url": str(v.get("maj_url") or "")}


def _numeros(version: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:4]) or (0,)


def verifier_maj() -> dict:
    v = version_locale()
    res = {"version": v["version"], "disponible": False}
    if not v["maj_url"] or v["version"] == "dev":
        return res
    if time.time() - _MAJ["verifie"] > 3600:  # au plus une fois par heure
        _MAJ["verifie"] = time.time()
        try:
            with urllib.request.urlopen(v["maj_url"], timeout=5) as r:
                _MAJ["info"] = json.loads(r.read().decode("utf-8-sig"))
        except Exception:  # noqa: BLE001 - hors ligne : on réessaiera plus tard
            pass
    info = _MAJ["info"] or {}
    if info.get("url") and _numeros(str(info.get("version", "0"))) > _numeros(v["version"]):
        res.update(disponible=True, nouvelle=str(info["version"]), notes=str(info.get("notes", ""))[:600])
    return res


def installer_maj() -> None:
    """Télécharge le nouvel installeur et le lance en mode discret : il ferme CV Booster, se met à jour
    (les données ne bougent pas) et rouvre l'appli (/RELANCER)."""
    if not verifier_maj().get("disponible"):
        raise ValueError("Aucune mise à jour disponible.")
    url = _MAJ["info"]["url"]
    if not re.match(r"https://|http://127\.0\.0\.1[:/]", url):
        raise ValueError("Adresse de mise à jour refusée (https obligatoire).")
    dest = Path(os.environ.get("TEMP", str(TRAVAIL))) / "CV Booster - mise a jour.exe"
    with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    journal = dest.with_suffix(".log")  # en cas de souci : %TEMP%\CV Booster - mise a jour.log
    subprocess.Popen([str(dest), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELANCER", f"/LOG={journal}"],
                     creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
