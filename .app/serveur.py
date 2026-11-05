"""CV Booster : serveur local de l'interface (Python standard, aucune dépendance).

Lancement : double-clic sur « CV Booster.bat » (ou python .app/serveur.py).
Ouvre http://127.0.0.1:8765 dans le navigateur. S'arrête seul quand l'onglet est fermé.

Les actions « IA » appellent Claude Code en mode non interactif (claude -p) avec le forfait de
la personne : pas d'API. La génération du PDF n'appelle pas Claude (zéro token).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import services  # noqa: E402  (historique, candidatures, agents perso, mises à jour : sans IA)

PORT = 8765
APP = Path(__file__).resolve().parent  # le PROGRAMME (installé dans AppData\Local\Programs\CV Booster)
# Les DONNÉES (ressources, CV, travail, agents, Skills) : transmises par lancer.pyw ; à défaut (développement),
# le dossier parent du programme.
RACINE = Path(os.environ.get("CVB_DONNEES") or APP.parent)
TRAVAIL = RACINE / ".cv-booster"
CV_TOML = TRAVAIL / "cv.toml"
AGENTS = RACINE / ".claude" / "agents"   # 1 fichier = 1 agent (consignes, outils, modèle, Skills utilisées)
SKILLS = RACINE / ".claude" / "skills"   # savoir-faire partagé, utilisé par les agents qui le déclarent
GENERER = SKILLS / "mise-en-page" / "scripts" / "generer_cv.py"
GENERER_LETTRE = SKILLS / "mise-en-page" / "scripts" / "generer_lettre.py"
LETTRES = TRAVAIL / "lettres"
OFFRES = TRAVAIL / "offres"
SCRIPTS = {"verifier_style.py": SKILLS / "regles-ecriture" / "scripts" / "verifier_style.py",
           "extraire_docx.py": SKILLS / "format-cv" / "scripts" / "extraire_docx.py",
           "correspondance.py": SKILLS / "format-cv" / "scripts" / "correspondance.py"}
ZONES = {"infos": RACINE / "ressources", "design": RACINE / "ressources" / "design"}
SORTIE = RACINE / "CV"
INACTIVITE_MAX = 180  # secondes sans signe de l'interface → arrêt du serveur

# Scripts enfants : python.exe (console) + CREATE_NO_WINDOW → console cachée, héritée par ce qu'ils lancent
# (pdflatex…). Avec pythonw.exe, chaque programme lancé ouvrirait sa propre fenêtre noire.
_console = Path(sys.executable).with_name("python.exe")
PYTHON = str(_console) if _console.is_file() else sys.executable

# --------------------------------------------------------------------------- outils externes

def config() -> dict:
    """Chemins relevés par l'installeur (.app/config.json) : fiables même si le PATH n'est pas à jour."""
    try:
        return json.loads((APP / "config.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def trouver_claude() -> str | None:
    if (exe := config().get("claude")) and Path(exe).is_file():
        return exe
    if exe := os.environ.get("CLAUDE_BIN") or shutil.which("claude"):
        return exe
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidats = [local / "Microsoft" / "WinGet" / "Links" / "claude.exe", Path.home() / ".local" / "bin" / "claude.exe"]
    ext = Path.home() / ".vscode" / "extensions"
    if ext.is_dir():  # binaire fourni avec l'extension VS Code (le plus récent)
        candidats += sorted(ext.glob("anthropic.claude-code-*/resources/native-binary/claude.exe"), reverse=True)
    return next((str(c) for c in candidats if c.is_file()), None)


# --------------------------------------------------------------------------- connexion au compte Claude
# Tout se passe dans l'appli : « claude auth login » tourne caché, ouvre la page de connexion dans le
# navigateur et se termine seul une fois connecté. Si le navigateur ne revient pas vers lui, il attend un
# code à coller : l'interface le lui transmet. Le statut (« claude auth status », ~1 s) est mis en cache.
CONNEXION = {"connecte": None, "verifie": 0.0, "proc": None, "url": "", "erreur": ""}
VERROU_CONNEXION = threading.Lock()
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def verifier_connexion() -> None:
    claude = trouver_claude()
    if not claude:
        CONNEXION.update(connecte=None, verifie=time.time())
        return
    try:
        r = subprocess.run([claude, "auth", "status", "--json"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30, creationflags=SANS_FENETRE)
        CONNEXION["connecte"] = bool(json.loads(r.stdout).get("loggedIn"))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass  # statut inconnu : on garde le précédent
    CONNEXION["verifie"] = time.time()


def claude_connecte() -> bool | None:
    """True / False, ou None si inconnu (Claude Code absent). Revérifié en arrière-plan quand c'est ancien."""
    if CONNEXION["verifie"] == 0:  # tout premier appel : on attend la réponse (déjà lancée au démarrage)
        with VERROU_CONNEXION:
            if CONNEXION["verifie"] == 0:
                verifier_connexion()
    elif time.time() - CONNEXION["verifie"] > (600 if CONNEXION["connecte"] else 20) and not VERROU_CONNEXION.locked():
        def verifier():
            with VERROU_CONNEXION:
                verifier_connexion()
        threading.Thread(target=verifier, daemon=True).start()
    return CONNEXION["connecte"]


def connexion_demarrer() -> None:
    p = CONNEXION["proc"]
    if p and p.poll() is None:  # déjà en cours : on rouvre simplement la page
        if CONNEXION["url"]:
            webbrowser.open(CONNEXION["url"])
        return
    claude = trouver_claude()
    if not claude:
        raise ValueError("Claude Code est introuvable : relance l'installation de CV Booster.")
    p = subprocess.Popen([claude, "auth", "login", "--claudeai"], cwd=RACINE, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", creationflags=SANS_FENETRE)
    CONNEXION.update(proc=p, url="", erreur="")

    def lire():
        sortie = []
        for ligne in p.stdout:
            sortie.append(ligne)
            if m := re.search(r"https://\S+", ligne):
                CONNEXION["url"] = m.group(0)
        p.wait()
        with VERROU_CONNEXION:
            verifier_connexion()
        if not CONNEXION["connecte"] and p.returncode not in (0, None) and CONNEXION["proc"] is p:
            CONNEXION["erreur"] = "La connexion n'a pas abouti. Réessaie."
            journal("connexion échouée : " + "".join(sortie)[-500:])
    threading.Thread(target=lire, daemon=True).start()


def connexion_etat() -> dict:
    p = CONNEXION["proc"]
    en_cours = bool(p and p.poll() is None)
    return {"en_cours": en_cours, "url": CONNEXION["url"] if en_cours else "", "erreur": CONNEXION["erreur"],
            "connecte": CONNEXION["connecte"] if not en_cours else False}


def connexion_code(code: str) -> None:
    p = CONNEXION["proc"]
    if not (p and p.poll() is None):
        raise ValueError("Aucune connexion en cours : clique d'abord sur « Se connecter ».")
    p.stdin.write(code.strip() + "\n")
    p.stdin.flush()


def connexion_annuler() -> None:
    if (p := CONNEXION["proc"]) and p.poll() is None:
        CONNEXION["proc"] = None
        p.kill()


def ouvrir_fenetre(adresse: str) -> None:
    """Ouvre l'interface dans sa propre fenêtre (mode application d'Edge, sans onglets ni barre d'adresse).
    Repli : le navigateur par défaut."""
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    for edge in (Path(pf86) / "Microsoft/Edge/Application/msedge.exe", Path(pf) / "Microsoft/Edge/Application/msedge.exe"):
        if edge.is_file():
            subprocess.Popen([str(edge), f"--app={adresse}", "--window-size=1040,900"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return
    webbrowser.open(adresse)


def completer_path() -> None:
    """Ajoute MiKTeX au PATH du serveur s'il n'y est pas (installation récente, session non relancée)."""
    miktex = Path(config().get("miktex") or
                  Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64")
    if not shutil.which("pdflatex") and miktex.is_dir():
        os.environ["PATH"] = f"{miktex}{os.pathsep}{os.environ['PATH']}"


# --------------------------------------------------------------------------- consignes pour Claude

CONSIGNE_SYSTEME = (
    "Tu es piloté par l'interface graphique CV Booster, utilisée par une personne non technicienne. "
    "Réponds en français, en Markdown, court. Ne parle jamais de commandes, de scripts, de chemins ni de "
    "fichiers techniques (cv.toml, .tex…) : dis « ton CV », « tes infos », « le design ». "
    "Tes consignes de rôle sont dans ta définition d'agent. Les Skills que tu utilises et les fichiers utiles "
    "sont déjà dans le message : ne les relis pas. "
    "Ici, le fichier de travail est .cv-booster/cv.toml (le dossier .cv-booster existe), les entrées sont "
    "dans ressources/, et la personne génère elle-même les PDF avec le bouton « Générer » : ne les génère pas. "
    "L'application enregistre tout : ne lui demande jamais de télécharger ou remplacer un fichier. "
    # Économie : chaque outil utilisé = un aller-retour qui renvoie tout le contexte (≈ 20k tokens).
    "ÉCONOMIE (forfait limité) : ne liste pas les dossiers (tout est fourni) ; ne lance PAS verifier_style.py "
    "ni aucune vérification du fichier : vérifie tes propositions toi-même avec la Skill regles-ecriture et le lexique fournis ; "
    "l'application contrôle le fichier après tes modifications (et le restaure s'il est cassé). "
    "Regroupe toutes tes modifications d'un fichier en une seule écriture quand c'est possible."
)

# Bouton de l'interface → agent à lancer (fichier .claude/agents/<agent>.md) et sa demande.
# L'agent apporte le reste : consignes, outils, modèle, Skills (c'est sa définition qui fait foi).
ACTIONS = {
    "importer": ("importeur", "Importe ses informations (ressources/, sauf ressources/design/) "
                 "dans .cv-booster/cv.toml."),
    "relire": ("relecteur", "Relis son CV."),
    "reformuler": ("reformulateur", "Propose des reformulations pour son CV."),
    "offre": ("adaptateur-offre", "Adapte son CV à l'offre d'emploi ci-dessous (enregistrée dans {fichier})."),
    "veille": ("veilleur-marche", "Fais la veille marché pour : {texte}."),
    "design": ("designer", "Inspire-toi des exemples de ressources/design/ pour le design de son CV."),
    "lettre": ("redacteur-lettre", "Écris sa lettre de motivation pour l'offre ci-dessous (enregistrée dans {fichier})."),
    "entretien": ("preparateur-entretien", "Prépare son entretien d'embauche."),
}
LIBELLES_ACTIONS = {"importer": "Créer mon CV", "relire": "Relire", "reformuler": "Reformuler",
                    "offre": "Adapter à une offre", "veille": "Veille marché", "design": "Design",
                    "lettre": "Lettre de motivation", "entretien": "Préparer un entretien", "perso": "Mon agent"}
AVEC_OFFRE = {"offre", "lettre", "entretien"}  # actions qui reçoivent le texte d'une annonce

# Permissions accordées par l'application (sécurité) : sans demander, l'agent peut lire, modifier ses fichiers
# et chercher sur le web. Les outils réellement disponibles sont ceux déclarés dans le fichier de l'agent.
AUTORISES = ["Read", "Edit", "Write", "Glob", "WebSearch", "WebFetch"]
ETAPES = {  # outil utilisé → libellé de progression
    "Read": "Lecture…", "Glob": "Recherche des documents…", "Edit": "Modification de ton CV…",
    "Write": "Enregistrement…", "Bash": "Vérification…", "PowerShell": "Vérification…",
    "WebSearch": "Recherche sur le web…", "WebFetch": "Lecture d'une page web…",
}

# --------------------------------------------------------------------------- contexte pré-mâché
# Principe d'économie : tout ce qui est prévisible (lire les Skills, le CV, lancer les vérifications)
# est fait ici, en Python, et envoyé d'un coup. Sinon Claude lit fichier par fichier, et chaque
# lecture est un aller-retour qui renvoie tout le contexte (mesuré : 3 allers-retours ≈ 52k tokens
# pour une relecture, contre 1 seul ainsi).

EXTENSIONS_TEXTE = {".txt", ".md", ".csv", ".toml", ".json"}
EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8-sig", errors="replace")


def entete(chemin: Path) -> tuple[dict, str]:
    """Fichier .md avec en-tête « --- clé: valeur --- » (format des agents et Skills de Claude Code)."""
    texte = lire(chemin)
    meta, corps = {}, texte
    if texte.startswith("---"):
        _, haut, corps = texte.split("---", 2)
        for ligne in haut.strip().splitlines():
            if ":" in ligne:
                cle, val = ligne.split(":", 1)
                meta[cle.strip()] = val.strip()
    return meta, corps.strip()


def agent(nom: str) -> dict:
    meta, _ = entete(AGENTS / f"{nom}.md")
    liste = lambda cle: [x.strip() for x in meta.get(cle, "").split(",") if x.strip()]  # noqa: E731
    # skills / annexes : champs maison (lus par ce serveur), qui disent ce que l'agent doit recevoir
    return {**meta, "skills": liste("skills"), "annexes": liste("annexes"), "outils": liste("tools")}


def script(nom: str, *args: str) -> str:
    res = subprocess.run([PYTHON, "-I", str(SCRIPTS[nom]), *args], cwd=RACINE,
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return (res.stdout or res.stderr).strip()


def texte_document(f: Path) -> str:
    """Texte d'une ressource, extrait par script (sans passer par Claude)."""
    ext = f.suffix.lower()
    if ext == ".docx":
        return script("extraire_docx.py", str(f))
    if ext == ".pdf" and shutil.which("pdftotext"):
        res = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(f), "-"], capture_output=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return res.stdout.decode("utf-8", errors="replace").strip()
    if ext in EXTENSIONS_TEXTE:
        return lire(f)
    return ""


def bloc(titre: str, contenu: str) -> str:
    return f"\n\n=== {titre} ===\n{contenu.strip()}"


def preparer_contexte(action: str, nom_agent: str, offre: Path | None = None) -> str:
    rel = lambda p: p.relative_to(RACINE).as_posix()  # noqa: E731
    c = ""
    a = agent(nom_agent)
    for skill in a["skills"]:          # étage 2 : le SKILL.md des Skills que l'agent déclare utiliser
        c += bloc(f"Skill {skill} (.claude/skills/{skill}/SKILL.md)", lire(SKILLS / skill / "SKILL.md"))
    for annexe in a["annexes"]:        # étage 3 : seulement les fichiers annexes dont CET agent a besoin
        c += bloc(f"Annexe de Skill : {annexe}", lire(SKILLS / annexe))
    if action != "importer" and CV_TOML.is_file():
        c += bloc(f"{rel(CV_TOML)} (son CV)", lire(CV_TOML))
    if action in {"relire", "reformuler"} and CV_TOML.is_file():
        c += bloc("Résultat de verifier_style.py (déjà lancé)", script("verifier_style.py", str(CV_TOML)))
    if action == "offre" and offre and CV_TOML.is_file():  # mots-clés de l'annonce déjà comptés par script
        c += bloc("Résultat de correspondance.py (mots-clés de l'offre présents ou non dans le CV, indicatif)",
                  script("correspondance.py", str(CV_TOML), str(offre)))
    if action == "lettre":
        existantes = sorted(LETTRES.glob("*.toml")) if LETTRES.is_dir() else []
        c += bloc("Lettres déjà écrites (modifier la bonne si c'est la même entreprise)",
                  "\n".join(rel(f) for f in existantes) or "aucune")

    if action == "importer":
        for f in sorted(ZONES["infos"].iterdir()):
            if not f.is_file():
                continue
            if f.suffix.lower() in EXTENSIONS_IMAGE:
                c += bloc(f"{rel(f)} (image : photo probable)", "Image, non lue. Si c'est une photo d'identité, "
                          f"mets photo = \"{rel(f)}\".")
            elif texte := texte_document(f):
                c += bloc(f"{rel(f)} (texte extrait, barré = ~~écarté~~)", texte)
            else:
                c += bloc(rel(f), "Format non lu automatiquement : lis-le toi-même si utile.")

    if action == "design":
        perso = TRAVAIL / "design.toml"
        if perso.is_file():
            c += bloc(f"{rel(perso)} (réglages actuels)", lire(perso))
        images = []
        for f in sorted(ZONES["design"].iterdir()):
            if f.suffix.lower() in EXTENSIONS_IMAGE:
                images.append(rel(f))
            elif f.suffix.lower() == ".pdf" and shutil.which("pdftoppm"):
                apercu = TRAVAIL / "build" / f"exemple-{f.stem}"
                apercu.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["pdftoppm", "-png", "-r", "60", "-f", "1", "-l", "1", "-singlefile", str(f),
                                str(apercu)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                images.append(rel(apercu.with_suffix(".png")))
        c += bloc("Exemples à regarder (une seule fois chacun, avec Read)", "\n".join(images) or "aucun")

    if action == "veille":
        fiches = sorted((TRAVAIL / "tendances").glob("*.md")) if (TRAVAIL / "tendances").is_dir() else []
        c += bloc("Fiches de veille existantes", "\n".join(
            f"{rel(f)} (modifiée le {datetime.fromtimestamp(f.stat().st_mtime):%Y-%m-%d})" for f in fiches) or "aucune")
        c += bloc("Date du jour", f"{datetime.now():%Y-%m-%d}")

    return ("Tout le contexte utile est ci-dessous, déjà lu pour toi : ne relis pas ces fichiers "
            "(sauf juste avant de les modifier)." + c)


# --------------------------------------------------------------------------- tâches Claude

TACHES: dict[str, dict] = {}
VERROU = threading.Lock()
SAUVEGARDE = TRAVAIL / "cv.toml.sauvegarde"


def controler_cv() -> str:
    """Après le passage de Claude : le CV doit toujours se lire. Sinon, on remet la version d'avant.
    Fait ici en Python plutôt que par Claude (chaque vérification par Claude coûte un aller-retour)."""
    if not CV_TOML.is_file():
        return ""
    try:
        tomllib.loads(CV_TOML.read_text(encoding="utf-8-sig"))
        return ""
    except tomllib.TOMLDecodeError:
        if SAUVEGARDE.is_file():
            shutil.copy(SAUVEGARDE, CV_TOML)
            return ("\n\n> ⚠️ Une modification avait abîmé ton CV : j'ai remis la version d'avant. "
                    "Redemande la modification, en une phrase.")
        return "\n\n> ⚠️ Ton CV n'a pas pu être créé correctement : relance « Importer mes infos »."


def lancer_claude(tache: dict, invite: str, nom_agent: str, reprise: str | None) -> None:
    claude = trouver_claude()
    if not claude:
        tache.update(etat="erreur", reponse="Claude Code est introuvable. Relance l'installation de CV Booster.")
        return
    if CV_TOML.is_file():  # filet de sécurité : version d'avant la tâche
        shutil.copy(CV_TOML, SAUVEGARDE)
        services.archiver_cv(f"Avant : {LIBELLES_ACTIONS.get(tache.get('titre'), tache.get('titre', ''))}")
    # L'invite passe par l'entrée standard : la ligne de commande Windows est limitée à ~32 000 caractères.
    cmd = [claude, "-p", "--output-format", "stream-json", "--verbose",
           "--agent", nom_agent,  # consignes, outils, modèle : ceux de .claude/agents/<nom>.md
           "--permission-mode", "acceptEdits", "--allowedTools", *AUTORISES,
           "--append-system-prompt", CONSIGNE_SYSTEME]
    if reprise:
        cmd += ["--resume", reprise]
    try:
        proc = subprocess.Popen(cmd, cwd=RACINE, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        tache["proc"] = proc
        proc.stdin.write(invite)
        proc.stdin.close()
        resultat = None
        for ligne in proc.stdout:
            try:
                msg = json.loads(ligne)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "assistant":
                for bloc in msg.get("message", {}).get("content", []):
                    if bloc.get("type") == "tool_use":
                        tache["etape"] = ETAPES.get(bloc.get("name"), "Travail en cours…")
                    elif bloc.get("type") == "text" and bloc.get("text", "").strip():
                        tache["etape"] = "Rédaction de la réponse…"
            elif msg.get("type") == "result":
                u = msg.get("usage", {})
                resultat = "erreur" if msg.get("is_error") else "fini"
                tache.update(
                    session=msg.get("session_id"),
                    tours=msg.get("num_turns", 0),
                    reponse=msg.get("result") or "",
                    tokens=sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                     "cache_read_input_tokens", "output_tokens")),
                )
        proc.wait()
        tache["reponse"] += controler_cv()  # avant d'annoncer la fin : l'interface affiche la réponse complète
        if nom_agent == "redacteur-lettre":
            tache["reponse"] += generer_lettres()  # le PDF de la lettre, tout de suite (un script, pas Claude)
        if resultat:
            tache["etat"] = resultat
        else:
            erreur = proc.stderr.read().strip()[-600:]
            tache.update(etat="erreur", reponse=erreur or "Claude s'est arrêté sans réponse.")
        if tache["etat"] == "erreur":  # traduire les erreurs courantes en français simple
            brut = tache["reponse"]
            if re.search(r"/login|log ?in|not logged|authenticat|credential|api key|oauth", brut, re.I):
                tache.update(connexion=True, reponse="Claude n'est pas connecté à ton compte (ou la connexion a "
                             "expiré). Clique sur « Me connecter à Claude », connecte-toi dans la page qui "
                             "s'ouvre, puis réessaie.")
                CONNEXION.update(connecte=False, verifie=time.time())  # l'Accueil le propose aussi
            elif re.search(r"usage limit|rate limit|quota|limit reached", brut, re.I):
                tache["reponse"] = ("Limite d'utilisation de ton forfait atteinte. Elle se recharge au bout de "
                                    "quelques heures : réessaie plus tard.")
    except Exception as e:  # noqa: BLE001 - on veut toujours rendre la main à l'interface
        tache.update(etat="erreur", reponse=f"Erreur inattendue : {e}")


def generer_lettres(toutes: bool = False) -> str:
    """Met en page les lettres modifiées (ou toutes) : PDF dans CV/. Renvoie un avertissement, sinon ""."""
    if not (LETTRES.is_dir() and CV_TOML.is_file() and shutil.which("pdflatex")):
        return ""
    res = subprocess.run([PYTHON, "-I", str(GENERER_LETTRE), "--source", str(CV_TOML), "--sortie", str(SORTIE)]
                         + (["--toutes"] if toutes else []),
                         cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         creationflags=SANS_FENETRE)
    sortie = res.stdout + res.stderr
    if "Échec" in sortie or "illisible" in sortie:
        return "\n\n> ⚠️ Le PDF de la lettre n'a pas pu être créé. Demande : « corrige le fichier de la lettre »."
    if "ATTENTION" in sortie:
        return "\n\n> ⚠️ La lettre dépasse une page : demande une version plus courte."
    return ""


def nouvelle_tache(invite: str, nom_agent: str, reprise: str | None, titre: str) -> str:
    with VERROU:
        if any(t["etat"] == "en_cours" for t in TACHES.values()):
            raise RuntimeError("Une tâche est déjà en cours : attends qu'elle se termine.")
        tid = uuid.uuid4().hex[:8]
        TACHES[tid] = {"etat": "en_cours", "etape": "Démarrage…", "reponse": "", "titre": titre,
                       "session": reprise, "agent": nom_agent, "tokens": 0}
    threading.Thread(target=lancer_claude, args=(TACHES[tid], invite, nom_agent, reprise), daemon=True).start()
    return tid


# --------------------------------------------------------------------------- état des fichiers

def lister(dossier: Path) -> list[str]:
    if not dossier.is_dir():
        return []
    return sorted(f.name for f in dossier.iterdir() if f.is_file() and not f.name.startswith("."))


def prenom_session() -> str:
    """Prénom de la session Windows (nom affiché du compte, sinon identifiant) : l'outil n'est lié à personne."""
    nom = ""
    try:
        import ctypes  # noqa: PLC0415
        taille = ctypes.c_ulong(256)
        tampon = ctypes.create_unicode_buffer(256)
        if ctypes.windll.secur32.GetUserNameExW(3, tampon, ctypes.byref(taille)):  # 3 = NameDisplay
            nom = tampon.value
    except Exception:  # noqa: BLE001
        pass
    nom = (nom or os.environ.get("USERNAME", "")).strip()
    premier = re.split(r"[\s._-]+", nom)[0] if nom else ""
    return premier[:1].upper() + premier[1:] if premier else ""


_MODULES: dict = {}


def _module(chemin: Path):
    """Un script de Skill, importé pour réutiliser ses fonctions (nommage des PDF, correspondance…) sans le
    lancer. Gardé en mémoire tant que le fichier ne change pas."""
    try:
        cle = (str(chemin), chemin.stat().st_mtime)
        if cle not in _MODULES:
            import importlib.util  # noqa: PLC0415
            if str(chemin.parent) not in sys.path:
                sys.path.insert(0, str(chemin.parent))  # generer_lettre importe generer_cv
            spec = importlib.util.spec_from_file_location(chemin.stem, chemin)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _MODULES[cle] = module
        return _MODULES[cle]
    except Exception:  # noqa: BLE001
        return None


def _generateur():
    return _module(GENERER)


def etat() -> dict:
    variantes, nom, rubriques, libelles = [], "", [], {}
    if CV_TOML.is_file():
        try:
            cv = tomllib.loads(CV_TOML.read_text(encoding="utf-8-sig"))
            variantes = [{"cle": k, "titre": v.get("titre", k)} for k, v in cv.get("variantes", {}).items()]
            nom = cv.get("identite", {}).get("nom", "")
            # Rubriques proposées dans le menu « Quelle partie reformuler ? »
            rubriques = ["L'accroche"] + [f"Expérience : {e.get('poste', '')} – {e.get('entreprise', '')}"
                                          for e in cv.get("experiences", [])] + ["Les compétences"]
            # Libellé lisible de chaque PDF (avec accents), retrouvé via la règle de nommage du générateur
            gen = _generateur()
            titres = [v["titre"] for v in variantes]
            for v in variantes:
                libelle = v["titre"] + (f" · {v['cle'].replace('_', ' ')}" if titres.count(v["titre"]) > 1 else "")
                v["libelle"] = libelle
                if gen:
                    libelles[gen.nom_pdf(cv, v["cle"])] = libelle
            # Lettres de motivation : « Lettre · Entreprise »
            gl = _module(GENERER_LETTRE)
            for f in sorted(LETTRES.glob("*.toml")) if LETTRES.is_dir() and gl else []:
                try:
                    lettre = tomllib.loads(lire(f))
                    libelles[gl.nom_pdf(cv, lettre)] = f"Lettre · {lettre.get('entreprise', f.stem)}"
                except tomllib.TOMLDecodeError:
                    pass
        except tomllib.TOMLDecodeError:
            pass
    perso = [{"nom": f.stem, "libelle": agent(f.stem).get("libelle", f.stem),
              "description": agent(f.stem).get("description", "")}
             for f in sorted(AGENTS.glob("*.md")) if services.agent_perso(f.stem)] if AGENTS.is_dir() else []
    return {
        "agents_perso": perso, "version": services.version_locale()["version"],
        "infos": lister(ZONES["infos"]), "design": lister(ZONES["design"]), "cv": lister(SORTIE),
        "cv_importe": CV_TOML.is_file(), "nom": nom, "variantes": variantes, "rubriques": rubriques,
        "prenom_session": prenom_session(), "libelles": libelles,
        # date de chaque PDF : l'interface s'en sert pour recharger l'aperçu quand le PDF change
        "cv_dates": {n: int((SORTIE / n).stat().st_mtime) for n in lister(SORTIE)},
        "cv_modifie": int(CV_TOML.stat().st_mtime) if CV_TOML.is_file() else 0,  # pour « modifié le … »
        "claude": bool(trouver_claude()), "pdflatex": bool(shutil.which("pdflatex")),
        "claude_connecte": claude_connecte(),
    }


APERCUS = TRAVAIL / "apercus"
_VERROUS_APERCU: dict[str, threading.Lock] = {}
_VERROU_DICT = threading.Lock()
_CONVERSIONS = threading.Semaphore(2)  # au plus 2 conversions en même temps (sinon la machine rame)


def apercu(nom_pdf: str) -> Path | None:
    """1re page du PDF en image (pdftoppm, livré avec MiKTeX). Recalculée seulement si le PDF a changé.
    Clics rapides : une seule conversion par fichier à la fois (les autres demandes attendent puis
    servent le résultat), et écriture dans un fichier temporaire remplacé d'un coup (jamais d'image
    à moitié écrite)."""
    pdf = SORTIE / nom_pdf
    if pdf.suffix.lower() != ".pdf" or not pdf.is_file() or not shutil.which("pdftoppm"):
        return None
    image = APERCUS / f"{pdf.stem}.png"
    with _VERROU_DICT:
        verrou = _VERROUS_APERCU.setdefault(pdf.name, threading.Lock())
    with verrou:
        if not image.is_file() or image.stat().st_mtime < pdf.stat().st_mtime:
            APERCUS.mkdir(parents=True, exist_ok=True)
            temp = APERCUS / f"{pdf.stem}.en-cours"
            with _CONVERSIONS:
                subprocess.run(["pdftoppm", "-png", "-r", "110", "-f", "1", "-l", "1", "-singlefile", str(pdf),
                                str(temp)], capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if temp.with_suffix(".en-cours.png").is_file():
                os.replace(temp.with_suffix(".en-cours.png"), image)
    return image if image.is_file() else None


def prechauffer_apercus(fichiers: list[str]) -> None:
    """Juste après « Générer » : prépare les aperçus en arrière-plan, pour qu'un clic les affiche aussitôt."""
    def travail():
        for f in fichiers:
            apercu(f)
    threading.Thread(target=travail, daemon=True).start()


def coulisses() -> dict:
    """Pour apprendre : les agents et les Skills, lus directement dans leurs fichiers (toujours à jour)."""
    rel = lambda p: p.relative_to(RACINE).as_posix()  # noqa: E731
    boutons = {nom: action for action, (nom, _) in ACTIONS.items()}
    agents = []
    for f in sorted(AGENTS.glob("*.md")):
        a = agent(f.stem)
        agents.append({"nom": a.get("name", f.stem), "description": a.get("description", ""),
                       "modele": a.get("model", ""), "outils": a["outils"], "skills": a["skills"],
                       "annexes": a["annexes"], "fichier": rel(f), "bouton": boutons.get(f.stem),
                       "perso": services.agent_perso(f.stem), "libelle": a.get("libelle", "")})
    skills = []
    for d in sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()):
        meta, _ = entete(d / "SKILL.md")
        fichiers = []
        for x in sorted(d.rglob("*")):
            if not x.is_file() or x.suffix == ".pyc":
                continue
            interne = x.relative_to(SKILLS).as_posix()  # ex. format-cv/lecture-documents.md
            role = ("principal" if x.name == "SKILL.md" else "script" if x.parent.name == "scripts" else "annexe")
            fichiers.append({"nom": x.relative_to(d).as_posix(), "chemin": rel(x), "role": role,
                             "charge_par": [a["nom"] for a in agents if interne in a["annexes"]]})
        skills.append({"nom": meta.get("name", d.name), "description": meta.get("description", ""),
                       "fichier": rel(d / "SKILL.md"), "fichiers": fichiers,
                       "utilisee_par": [a["nom"] for a in agents if d.name in a["skills"]]})
    return {"agents": agents, "skills": skills}


def generer(variante: str) -> dict:
    res = subprocess.run([PYTHON, "-I", str(GENERER), "--source", str(CV_TOML),
                          "--variante", variante, "--sortie", str(SORTIE)],
                         cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    sortie = (res.stdout + res.stderr).strip()
    fichiers = [Path(p.strip()).name for p in re.findall(r"PDF généré : (.+?\.pdf)", sortie)]
    prechauffer_apercus(fichiers)
    return {"ok": res.returncode == 0, "message": sortie.splitlines()[-1] if sortie else "",
            "pages_ok": "ATTENTION" not in sortie, "ats": "_ATS.pdf" in sortie,
            "fichiers": fichiers, "photo_provisoire": "PHOTO PROVISOIRE" in sortie}


# --------------------------------------------------------------------------- serveur HTTP

DERNIER_SIGNE = time.time()
FERMETURE = 0.0       # moment où la fenêtre a signalé sa fermeture (0 = jamais)
DELAI_FERMETURE = 5   # secondes de grâce : un simple rechargement de page renvoie un signe entre-temps


class Gestionnaire(BaseHTTPRequestHandler):
    def log_message(self, *_):  # silencieux
        pass

    def _json(self, data, code=200):
        corps = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _fichier(self, chemin: Path, type_mime: str):
        corps = chemin.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", type_mime)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _corps(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_GET(self):
        global DERNIER_SIGNE
        DERNIER_SIGNE = time.time()
        url = urlparse(self.path)
        if url.path == "/":
            return self._fichier(APP / "index.html", "text/html; charset=utf-8")
        if url.path in ("/icone.png", "/favicon.ico"):
            return self._fichier(APP / "icone.png", "image/png")
        if url.path.startswith("/vendor/"):  # bibliothèques et police embarquées : rien à télécharger au démarrage
            f = APP / "vendor" / Path(unquote(url.path[8:])).name
            types = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".woff2": "font/woff2"}
            if f.is_file() and f.suffix in types:
                return self._fichier(f, types[f.suffix])
        if url.path == "/api/etat":
            return self._json(etat())
        if url.path == "/api/connexion":
            return self._json(connexion_etat())
        if url.path == "/api/historique":
            return self._json(services.historique())
        if url.path == "/api/candidatures":
            return self._json({"liste": services.candidatures(), "statuts": services.STATUTS})
        if url.path == "/api/maj":
            return self._json(services.verifier_maj())
        if url.path == "/api/coulisses":
            return self._json(coulisses())
        if url.path.startswith("/api/tache/"):
            t = TACHES.get(url.path.rsplit("/", 1)[-1])
            if not t:
                return self._json({"erreur": "tâche inconnue"}, 404)
            return self._json({k: v for k, v in t.items() if k != "proc"})
        if url.path.startswith("/cv/"):
            f = SORTIE / Path(unquote(url.path[4:])).name
            if f.is_file() and f.suffix == ".pdf":
                return self._fichier(f, "application/pdf")
        if url.path.startswith("/apercu/"):  # image de la 1re page d'un PDF, pour l'aperçu dans « Mes CV »
            image = apercu(Path(unquote(url.path[8:])).name)
            if image:
                return self._fichier(image, "image/png")
        self._json({"erreur": "introuvable"}, 404)

    def do_POST(self):
        global FERMETURE
        url = urlparse(self.path)
        if url.path == "/api/fermeture":  # envoyé par la fenêtre quand on la ferme (croix)
            FERMETURE = time.time()
            return self._json({"ok": True})
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/api/deposer":  # corps brut = le fichier ; nom dans ?nom=
                zone = ZONES[q["zone"]]
                zone.mkdir(parents=True, exist_ok=True)
                nom = Path(q["nom"]).name
                if not nom or nom.startswith("."):
                    raise ValueError("nom de fichier invalide")
                (zone / nom).write_bytes(self._corps())
                return self._json({"ok": True})

            if url.path == "/api/supprimer":
                if q["zone"] == "cv":  # un CV généré : seulement des PDF du dossier CV/
                    f = SORTIE / Path(q["nom"]).name
                    if f.suffix.lower() != ".pdf":
                        raise ValueError("seuls les PDF peuvent être supprimés ici")
                else:
                    f = ZONES[q["zone"]] / Path(q["nom"]).name
                if f.is_file():
                    f.unlink()
                if q["zone"] == "cv" and f.name.startswith("Lettre_") and LETTRES.is_dir():
                    # la lettre elle-même aussi (sinon son PDF reviendrait à la prochaine mise en page)
                    gl, cv = _module(GENERER_LETTRE), tomllib.loads(lire(CV_TOML)) if CV_TOML.is_file() else {}
                    for t in LETTRES.glob("*.toml"):
                        try:
                            if gl and gl.nom_pdf(cv, tomllib.loads(lire(t))) == f.name:
                                t.unlink()
                        except ValueError:
                            pass
                return self._json({"ok": True})

            if url.path == "/api/action":
                d = json.loads(self._corps() or b"{}")
                action = d.get("action")
                if action == "repondre":
                    t = TACHES.get(d.get("tache", ""))
                    if not t or not t.get("session"):
                        raise ValueError("conversation introuvable")
                    tid = nouvelle_tache(d.get("texte", ""), t["agent"], t["session"], t["titre"])
                    return self._json({"tache": tid})
                texte = d.get("texte", "")
                if action == "perso":  # un agent créé par la personne (Coulisses › Créer un agent)
                    nom_agent = Path(d.get("agent", "")).name
                    if not services.agent_perso(nom_agent):
                        raise ValueError("Agent introuvable.")
                    consigne = "Sa demande : {texte}"
                else:
                    nom_agent, consigne = ACTIONS[action]
                fichier, offre = "", None
                if action in AVEC_OFFRE and texte.strip():
                    OFFRES.mkdir(parents=True, exist_ok=True)
                    offre = OFFRES / f"offre-{datetime.now():%Y%m%d-%H%M%S}.txt"
                    offre.write_text(texte, encoding="utf-8")
                    fichier = offre.relative_to(RACINE).as_posix()
                invite = consigne.format(fichier=fichier, texte=texte)
                if action == "reformuler" and texte:
                    invite += f" Sa demande : {texte}"
                if offre:
                    invite += bloc("Texte de l'offre", texte)
                if action == "entretien" and d.get("precision"):
                    invite += bloc("Ce qu'elle précise", d["precision"])
                invite += "\n\n" + preparer_contexte(action, nom_agent, offre)
                return self._json({"tache": nouvelle_tache(invite, nom_agent, None, action)})

            if url.path == "/api/correspondance":  # mots-clés d'une annonce dans le CV : un script, 0 token
                d = json.loads(self._corps() or b"{}")
                module = _module(SCRIPTS["correspondance.py"])
                if not (module and CV_TOML.is_file()):
                    raise ValueError("Crée d'abord ton CV.")
                if not isinstance(d.get("texte"), str):
                    raise ValueError("Colle le texte de l'annonce.")
                cv = tomllib.loads(lire(CV_TOML))
                return self._json(module.analyser(cv, d["texte"], d.get("variante") or None))

            if url.path == "/api/historique/restaurer":
                services.restaurer_cv(q["fichier"])
                return self._json({"ok": True})

            if url.path == "/api/candidatures":
                return self._json({"liste": services.enregistrer_candidatures(json.loads(self._corps() or b"[]"))})

            if url.path == "/api/agents/creer":
                return self._json({"nom": services.creer_agent(json.loads(self._corps() or b"{}"))})
            if url.path == "/api/agents/supprimer":
                services.supprimer_agent(q["nom"])
                return self._json({"ok": True})

            if url.path == "/api/lettres/generer":  # « Refaire le PDF » (ex. après un changement de design)
                avert = generer_lettres(toutes=True)
                return self._json({"ok": not avert, "message": avert.strip("\n> ")})

            if url.path == "/api/maj/installer":
                services.installer_maj()
                return self._json({"ok": True})

            if url.path == "/api/generer":
                return self._json(generer(q["variante"]))

            if url.path == "/api/ouvrir":  # ouvre un dossier dans l'Explorateur
                dossier = {"cv": SORTIE, "infos": ZONES["infos"], "design": ZONES["design"],
                           "agents": AGENTS, "skills": SKILLS}[q["quoi"]]
                dossier.mkdir(parents=True, exist_ok=True)
                os.startfile(dossier)  # type: ignore[attr-defined]  (Windows)
                return self._json({"ok": True})

            if url.path == "/api/ouvrir-fichier":  # coulisses : un fichier d'agent ou de Skill, dans le Bloc-notes
                f = (RACINE / q["chemin"]).resolve()
                if not (f.is_file() and f.is_relative_to((RACINE / ".claude").resolve())):
                    raise ValueError("fichier non autorisé")
                subprocess.Popen(["notepad.exe", str(f)])
                return self._json({"ok": True})

            if url.path == "/api/connexion":  # connexion au compte Claude, sans quitter l'appli
                connexion_demarrer()
                return self._json(connexion_etat())
            if url.path == "/api/connexion/code":
                connexion_code(json.loads(self._corps() or b"{}").get("code", ""))
                return self._json(connexion_etat())
            if url.path == "/api/connexion/annuler":
                connexion_annuler()
                return self._json(connexion_etat())

            if url.path == "/api/journal":  # tests : la page note une étape dans le journal
                journal("page : " + q.get("e", ""))
                return self._json({"ok": True})

            if url.path == "/api/quitter":
                journal("/api/quitter reçu")
                self._json({"ok": True})
                threading.Thread(target=arreter, daemon=True).start()  # la fenêtre (fenetre.py) se ferme seule
                return
        except (KeyError, ValueError, RuntimeError) as e:
            return self._json({"erreur": str(e)}, 400)
        except OSError as e:  # réseau (mise à jour), fichier verrouillé…
            return self._json({"erreur": f"Opération impossible : {e}"}, 400)
        except Exception as e:  # noqa: BLE001 - jamais de connexion coupée : la page affiche un message
            journal(f"erreur {url.path} : {e!r}")
            return self._json({"erreur": "Erreur inattendue. Réessaie ; si ça recommence, relance CV Booster."}, 500)
        self._json({"erreur": "introuvable"}, 404)


class ServeurExclusif(ThreadingHTTPServer):
    """Sous Windows, SO_REUSEADDR (activé par défaut par http.server) laisse DEUX serveurs écouter le même
    port : une ancienne version pourrait répondre à la place de la nouvelle. On exige un port exclusif."""
    allow_reuse_address = False
    # File d'attente des connexions : 5 par défaut. Au-delà, Windows refuse et le navigateur réessaie
    # 1 s plus tard → l'appli semble figée quand on clique vite (mesuré : pics à ~1000 ms).
    request_queue_size = 128
    daemon_threads = True

    def server_bind(self):
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


SERVEUR: ThreadingHTTPServer | None = None
FIN = threading.Event()  # signalé quand le serveur s'arrête


def journal(evenement: str) -> None:
    """Journal horodaté des étapes de la fenêtre, seulement en test (CVB_JOURNAL=1)."""
    if os.environ.get("CVB_JOURNAL"):
        with open(TRAVAIL / "journal-fenetre.txt", "a", encoding="utf-8") as f:
            f.write(f"{time.time():.2f} {threading.current_thread().name} {evenement}\n")


def arreter() -> None:
    connexion_annuler()
    for t in TACHES.values():
        if (p := t.get("proc")) and p.poll() is None:
            p.terminate()
    if SERVEUR:
        SERVEUR.shutdown()
    FIN.set()


def surveiller_inactivite() -> None:
    """Arrête le serveur quand la fenêtre est fermée (signal + 5 s sans nouvelles), ou en dernier recours
    après 3 min sans aucun signe. Jamais pendant qu'une tâche Claude est en cours."""
    while True:
        time.sleep(1)
        if any(t["etat"] == "en_cours" for t in TACHES.values()):
            continue
        maintenant = time.time()
        fenetre_fermee = FERMETURE > DERNIER_SIGNE and maintenant - FERMETURE > DELAI_FERMETURE
        if fenetre_fermee or maintenant - DERNIER_SIGNE > INACTIVITE_MAX:
            arreter()
            return


def reparer_raccourcis() -> None:
    """Le dossier a été déplacé depuis la dernière fois → réécrire les raccourcis (dossier, et Bureau s'il
    existe) pour qu'ils pointent au bon endroit. Comparaison avec la racine notée dans config.json."""
    conf = config()
    if conf.get("installe"):  # version installée : les raccourcis appartiennent à l'installeur (menu Démarrer…)
        return
    if RACINE != APP.parent:  # tests avec un autre dossier de données : les raccourcis de dev ne bougent pas
        return
    if conf.get("racine") == str(RACINE):
        return
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(APP / "creer_raccourcis.ps1"), "-MajBureau"],
                   capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    conf["racine"] = str(RACINE)
    (APP / "config.json").write_text(json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    """Le serveur seul. La fenêtre est un autre programme (fenetre.py), lancé par lancer.pyw.
    Lancé directement sans --sans-navigateur (développement) : ouvre l'interface dans Edge."""
    global SERVEUR
    completer_path()
    for z in ZONES.values():
        z.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("CVB_PORT", PORT))  # autre port : tests uniquement
    try:
        SERVEUR = ServeurExclusif(("127.0.0.1", port), Gestionnaire)
    except OSError:  # déjà lancé : rien à faire (la fenêtre parle au serveur existant)
        return
    threading.Thread(target=surveiller_inactivite, daemon=True).start()
    threading.Thread(target=reparer_raccourcis, daemon=True).start()
    threading.Thread(target=claude_connecte, daemon=True).start()  # statut de connexion prêt pour la page
    if "--sans-navigateur" not in sys.argv and not os.environ.get("CVB_SANS_FENETRE"):
        ouvrir_fenetre(f"http://127.0.0.1:{port}")
    SERVEUR.serve_forever()


if __name__ == "__main__":
    main()
