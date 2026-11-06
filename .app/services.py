"""Fonctions de CV Booster qui n'utilisent PAS l'IA (zéro token), appelées par serveur.py :
historique du CV, suivi des candidatures, agents créés par la personne, journal des erreurs,
consommation, diagnostic (« Signaler un problème »), sauvegarde de ses données, mises à jour.

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
import zipfile
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
        n = 2
        while (HISTORIQUE / nom).exists():  # deux copies dans la même seconde : jamais d'écrasement
            nom = f"cv-{datetime.now():%Y%m%d-%H%M%S}-{n}.toml"
            n += 1
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
            quand = datetime.strptime(f.stem[3:18], "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        res.append({"fichier": f.name, "date": quand.isoformat(timespec="minutes"), "motif": motifs.get(f.name, "")})
    return res


def restaurer_cv(fichier: str) -> None:
    f = HISTORIQUE / Path(fichier).name
    if not (re.fullmatch(r"cv-\d{8}-\d{6}(-\d+)?\.toml", f.name) and f.is_file()):
        raise ValueError("Cette version n'existe plus.")
    contenu = f.read_bytes()                           # lue AVANT la copie de sécurité ci-dessous
    tomllib.loads(contenu.decode("utf-8-sig"))         # lisible, sinon erreur (et rien n'est touché)
    archiver_cv("Avant un retour en arrière")          # on peut toujours revenir sur le retour
    CV_TOML.write_bytes(contenu)


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
        raise ValueError("Donnez-lui un nom d'au moins 3 lettres.")
    if (AGENTS / f"{nom}.md").exists():
        raise ValueError(f"Un agent « {nom} » existe déjà : choisissez un autre nom.")
    description = _une_ligne(d.get("description"), 300)
    consignes = str(d.get("consignes") or "").strip()[:8000]
    if not description or not consignes:
        raise ValueError("Remplissez « À quoi il sert » et « Ses consignes ».")
    outils = ["Read"] + [o for cle in ("modifier", "web") if d.get(cle) for o in OUTILS[cle]]
    skills = [s for s in d.get("skills", []) if isinstance(s, str) and (SKILLS / s / "SKILL.md").is_file()]
    modele = d.get("modele") if d.get("modele") in MODELES else "sonnet"
    effort = d.get("effort") if d.get("effort") in ("low", "medium") else "medium"
    lignes = ["---", f"name: {nom}", f"description: {description}", f"tools: {', '.join(outils)}",
              f"model: {modele}", f"effort: {effort}"]
    if skills:
        lignes.append(f"skills: {', '.join(skills)}")
    droits = ("Vous pouvez modifier son CV, mais seulement après son accord." if d.get("modifier") else
              "Vous ne pouvez PAS modifier ses fichiers : vous proposez, elle recopie ce qu'elle garde. "
              "Ne promettez jamais de modifier son CV.")
    lignes += [f"libelle: {libelle}", "cree_par: vous", "---", "",
               f"Vous êtes **{libelle}**, un agent de CV Booster. Vous vouvoyez toujours la personne. {droits}",
               "", consignes, ""]
    AGENTS.mkdir(parents=True, exist_ok=True)
    (AGENTS / f"{nom}.md").write_text("\n".join(lignes), encoding="utf-8")
    return nom


def agent_perso(nom: str) -> bool:
    f = AGENTS / f"{Path(nom).name}.md"
    if not f.is_file():
        return False
    haut = f.read_text(encoding="utf-8-sig", errors="replace").split("---")
    # « toi » : agents créés avant la 1.3
    return len(haut) > 2 and re.search(r"^cree_par:\s*(?:vous|toi)\s*$", haut[1], re.M) is not None


def supprimer_agent(nom: str) -> None:
    if not agent_perso(nom):
        raise ValueError("Seuls les agents que vous avez créés peuvent être supprimés ici.")
    (AGENTS / f"{Path(nom).name}.md").unlink()


# =========================================================================== réglages (puissance)
# « Puissance » de l'assistant, choisie dans Améliorer. Moyen = les réglages de chaque agent (modèle et
# effort choisis agent par agent, après comparaison de la qualité) ; Faible et Fort les remplacent pour tous.
REGLAGES = TRAVAIL / "reglages.json"
PUISSANCES = {
    "faible": {"modele": "haiku", "effort": "low"},     # le plus économe
    "moyen": None,                                      # réglages propres à chaque agent (conseillé)
    "fort": {"modele": "sonnet", "effort": "high"},     # réflexion maximale
}


def reglages() -> dict:
    r = _lire_json(REGLAGES, {})
    return {"puissance": r.get("puissance") if r.get("puissance") in PUISSANCES else "moyen"}


def enregistrer_reglages(d: dict) -> dict:
    if d.get("puissance") not in PUISSANCES:
        raise ValueError("Puissance inconnue.")
    r = {**reglages(), "puissance": d["puissance"]}
    _ecrire_json(REGLAGES, r)
    return r


# =========================================================================== journal des erreurs
# Toujours actif, petit (200 Ko au plus) : c'est ce que contient « Signaler un problème ».
ERREURS = TRAVAIL / "erreurs.log"


def noter_erreur(texte: str) -> None:
    try:
        TRAVAIL.mkdir(parents=True, exist_ok=True)
        if ERREURS.is_file() and ERREURS.stat().st_size > 200_000:
            ERREURS.write_text(ERREURS.read_text(encoding="utf-8", errors="replace")[-100_000:], encoding="utf-8")
        with open(ERREURS, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {anonymiser(str(texte))}\n")
    except OSError:
        pass


def anonymiser(texte: str) -> str:
    """Retire ce qui identifie la personne : dossier personnel (nom de session) et adresses e-mail."""
    texte = texte.replace(str(Path.home()), "%USERPROFILE%").replace(str(Path.home()).replace("\\", "/"), "%USERPROFILE%")
    texte = texte.replace(str(Path.home()).replace("\\", "\\\\"), "%USERPROFILE%")
    return re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[e-mail]", texte)


# =========================================================================== consommation
# Chaque tâche d'agent : action, agent, modèle, tokens, durée. Pour « Votre consommation » (Coulisses).
CONSO = TRAVAIL / "consommation.json"


def noter_conso(action: str, agent: str, modele: str, tokens: int, duree: int, suite: bool, cout: float = 0,
                puissance: str = "moyen") -> None:
    liste = _lire_json(CONSO, [])
    liste = (liste if isinstance(liste, list) else [])[-999:]
    liste.append({"quand": datetime.now().isoformat(timespec="seconds"), "action": action, "agent": agent,
                  "modele": modele, "tokens": int(tokens or 0), "duree": duree, "suite": suite,
                  "cout_api": cout,  # équivalent en $ au tarif API (indicateur ; elle ne paie pas ça)
                  "puissance": puissance})
    _ecrire_json(CONSO, liste)


def consommation() -> dict:
    liste = _lire_json(CONSO, [])
    liste = liste if isinstance(liste, list) else []
    aujourd_hui = date.today().isoformat()
    semaine = (datetime.now().timestamp() - 7 * 86400)
    par_action: dict[str, dict] = {}
    for x in liste:
        a = par_action.setdefault(x.get("action", "?"), {"fois": 0, "tokens": 0})
        a["fois"] += 1
        a["tokens"] += x.get("tokens", 0)
    jours: dict[str, int] = {}
    for x in liste:
        jours[x["quand"][:10]] = jours.get(x["quand"][:10], 0) + x.get("tokens", 0)
    return {
        "aujourdhui": sum(x.get("tokens", 0) for x in liste if x["quand"].startswith(aujourd_hui)),
        "semaine": sum(x.get("tokens", 0) for x in liste if datetime.fromisoformat(x["quand"]).timestamp() >= semaine),
        "taches_aujourdhui": sum(1 for x in liste if x["quand"].startswith(aujourd_hui)),
        "par_action": {k: {"fois": v["fois"], "moyenne": round(v["tokens"] / v["fois"])} for k, v in par_action.items()},
        "jours": dict(sorted(jours.items())[-14:]),
        "dernieres": liste[-8:][::-1],
    }


# =========================================================================== signaler un problème
def diagnostic(infos: dict, dossier: Path | None = None) -> Path:
    """Un zip à envoyer à la personne qui s'occupe de CV Booster : état de l'appli, journaux, erreurs.
    Jamais son CV, ses documents, ses lettres ni ses candidatures ; nom de session et e-mails masqués."""
    dossier = dossier or Path.home() / "Desktop"
    if not dossier.is_dir():
        dossier = RACINE
    chemin = dossier / f"CV Booster - diagnostic {datetime.now():%Y-%m-%d %Hh%M}.zip"
    import platform  # noqa: PLC0415
    infos = {**infos, "windows": platform.platform(), "date": datetime.now().isoformat(timespec="seconds"),
             "conso_7_jours": consommation()["semaine"]}
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("infos.json", anonymiser(json.dumps(infos, ensure_ascii=False, indent=1)))
        for f in (ERREURS, RACINE / "journal-installation.txt", APP / "config.json", TRAVAIL / "journal-fenetre.txt"):
            if f.is_file():
                z.writestr(f.name, anonymiser(f.read_text(encoding="utf-8-sig", errors="replace")[-60_000:]))
    return chemin


# =========================================================================== sauvegarde de ses données
# Tout ce qui est à elle, dans un seul fichier : documents, CV et PDF, lettres, candidatures, versions
# précédentes, agents et Skills (y compris ceux qu'elle a modifiés ou créés). Pas les caches.
SAUVEGARDE_MARQUE = "cv-booster-sauvegarde.json"
_DOSSIERS_SAUVES = ("ressources", "CV", ".cv-booster", ".claude")
_EXCLUS = {"build", "apercus", "fenetre", "__pycache__"}
_FICHIERS_EXCLUS = {"erreurs.log", "journal-fenetre.txt", "cv.toml.sauvegarde"}


def sauvegarder(chemin: Path | None = None) -> Path:
    chemin = chemin or RACINE / f"Sauvegarde CV Booster {datetime.now():%Y-%m-%d}.zip"
    if chemin.suffix.lower() != ".zip":
        chemin = chemin.with_suffix(".zip")
    n = 0
    tmp = chemin.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for d in _DOSSIERS_SAUVES:
            for f in sorted((RACINE / d).rglob("*")) if (RACINE / d).is_dir() else []:
                rel = f.relative_to(RACINE)
                if f.is_file() and not (set(rel.parts) & _EXCLUS) and f.name not in _FICHIERS_EXCLUS:
                    z.write(f, rel.as_posix())
                    n += 1
        z.writestr(SAUVEGARDE_MARQUE, json.dumps({"date": datetime.now().isoformat(timespec="seconds"),
                                                   "version": version_locale()["version"], "fichiers": n}))
    os.replace(tmp, chemin)
    return chemin


def restaurer_sauvegarde(chemin: Path) -> int:
    """Remet une sauvegarde dans le dossier des données. Le CV actuel est d'abord mis de côté (historique).
    Seuls les dossiers prévus sont écrits : jamais de fichier en dehors (chemins « ../ » refusés)."""
    if not (chemin.is_file() and zipfile.is_zipfile(chemin)):
        raise ValueError("Ce fichier n'est pas une sauvegarde CV Booster.")
    with zipfile.ZipFile(chemin) as z:
        if SAUVEGARDE_MARQUE not in z.namelist():
            raise ValueError("Ce fichier n'est pas une sauvegarde CV Booster.")
        archiver_cv("Avant la restauration d'une sauvegarde")
        racine = RACINE.resolve()
        n = 0
        for nom in z.namelist():
            cible = (RACINE / nom).resolve()
            if nom == SAUVEGARDE_MARQUE or nom.endswith("/") or Path(nom).parts[0] not in _DOSSIERS_SAUVES \
                    or not cible.is_relative_to(racine):
                continue
            cible.parent.mkdir(parents=True, exist_ok=True)
            with z.open(nom) as src, open(cible, "wb") as dst:
                shutil.copyfileobj(src, dst)
            n += 1
    return n


# =========================================================================== mises à jour
# version.json (écrit par construire_installeur.py) : {"version": "1.2.0", "maj_url": "https://…/version.json"}.
# L'adresse maj_url renvoie {"version": "1.3.0", "url": "https://…/Installer CV Booster.exe"}.
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
    # Une lecture par lancement de l'appli ; sans réponse (hors ligne au démarrage), nouvel essai 10 min plus tard.
    if _MAJ["info"] is None and time.time() - _MAJ["verifie"] > 600:
        _MAJ["verifie"] = time.time()
        try:
            with urllib.request.urlopen(v["maj_url"], timeout=5) as r:
                _MAJ["info"] = json.loads(r.read().decode("utf-8-sig"))
        except Exception:  # noqa: BLE001 - hors ligne : on réessaiera plus tard
            pass
    info = _MAJ["info"] or {}
    if info.get("url") and _numeros(str(info.get("version", "0"))) > _numeros(v["version"]):
        res.update(disponible=True, nouvelle=str(info["version"]))
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
