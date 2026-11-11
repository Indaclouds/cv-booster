"""CV Booster: local server for the UI (standard Python, no dependencies).

Launch: double-click « CV Booster.bat » (or python .app/serveur.py).
Opens http://127.0.0.1:8765 in the browser. Stops on its own when the tab is closed.

"AI" actions call Claude Code in non-interactive mode (claude -p) with the user's
plan: no API. PDF generation doesn't call Claude (zero tokens).
"""

import importlib.util
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
import services  # noqa: E402  (history, applications, custom agents, updates: no AI)

PORT = 8765
APP = Path(__file__).resolve().parent  # the PROGRAM (installed in AppData\Local\Programs\CV Booster)
# The DATA (resources, CV, work, agents, Skills): passed by lancer.pyw; otherwise (development),
# the program's parent folder.
RACINE = Path(os.environ.get("CVB_DONNEES") or APP.parent)
TRAVAIL = RACINE / ".cv-booster"
CV_TOML = TRAVAIL / "cv.toml"
AGENTS = RACINE / ".claude" / "agents"   # 1 file = 1 agent (instructions, tools, model, Skills used)
SKILLS = RACINE / ".claude" / "skills"   # shared know-how, used by the agents that declare it
GENERER = SKILLS / "mise-en-page" / "scripts" / "generer_cv.py"
GENERER_LETTRE = SKILLS / "mise-en-page" / "scripts" / "generer_lettre.py"
GENERER_DOCX = SKILLS / "mise-en-page" / "scripts" / "generer_docx.py"
CV_EN = TRAVAIL / "cv-en.toml"   # the English translation (translator agent); cv.toml stays the reference
LETTRES = TRAVAIL / "lettres"
DESIGNS = TRAVAIL / "designs"  # one folder per design: design.toml, + gabarit/ for a custom design (layout agent)
MAX_DESIGNS = 3
OFFRES = TRAVAIL / "offres"
SCRIPTS = {"verifier_style.py": SKILLS / "regles-ecriture" / "scripts" / "verifier_style.py",
           "extraire_docx.py": SKILLS / "format-cv" / "scripts" / "extraire_docx.py",
           "correspondance.py": SKILLS / "format-cv" / "scripts" / "correspondance.py",
           "appliquer.py": SKILLS / "format-cv" / "scripts" / "appliquer.py"}
ZONES = {"infos": RACINE / "ressources", "design": RACINE / "ressources" / "design"}
SORTIE = RACINE / "CV"
INACTIVITE_MAX = 180  # seconds without a sign from the UI → server stops

# Child scripts: python.exe (console) + CREATE_NO_WINDOW → hidden console, inherited by what they launch
# (pdflatex…). With pythonw.exe, every launched program would open its own black window.
_console = Path(sys.executable).with_name("python.exe")
PYTHON = str(_console) if _console.is_file() else sys.executable

# --------------------------------------------------------------------------- external tools

def config() -> dict:
    """Paths recorded by the installer (.app/config.json): reliable even if PATH is out of date."""
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
    if ext.is_dir():  # binary shipped with the VS Code extension (the most recent one)
        candidats += sorted(ext.glob("anthropic.claude-code-*/resources/native-binary/claude.exe"), reverse=True)
    return next((str(c) for c in candidats if c.is_file()), None)


# --------------------------------------------------------------------------- Claude account login
# Everything happens in the app: « claude auth login » runs hidden, opens the login page in the
# browser and exits on its own once logged in. If the browser doesn't call back, it waits for a
# code to paste: the UI passes it on. The status (« claude auth status », ~1 s) is cached.
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
                           errors="replace", timeout=30, creationflags=SANS_FENETRE,
                           stdin=subprocess.DEVNULL)  # no open stdin: nothing can wait for input
        CONNEXION["connecte"] = bool(json.loads(r.stdout).get("loggedIn"))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass  # unknown status: keep the previous one
    CONNEXION["verifie"] = time.time()


def claude_connecte() -> bool | None:
    """True / False, or None if unknown (no Claude Code). Rechecked in the background when stale."""
    if CONNEXION["verifie"] == 0:  # very first call: wait for the answer (already started at launch)
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
    if p and p.poll() is None:  # already running: just reopen the page
        if CONNEXION["url"]:
            webbrowser.open(CONNEXION["url"])
        return
    claude = trouver_claude()
    if not claude:
        raise ValueError("Claude Code est introuvable : relancez l'installation de CV Booster.")
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
            CONNEXION["erreur"] = "La connexion n'a pas abouti. Réessayez."
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
        raise ValueError("Aucune connexion en cours : cliquez d'abord sur « Se connecter ».")
    p.stdin.write(code.strip() + "\n")
    p.stdin.flush()


def connexion_annuler() -> None:
    if (p := CONNEXION["proc"]) and p.poll() is None:
        CONNEXION["proc"] = None
        p.kill()


def ouvrir_fenetre(adresse: str) -> None:
    """Opens the UI in its own window (Edge app mode, no tabs or address bar).
    Fallback: the default browser."""
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    for edge in (Path(pf86) / "Microsoft/Edge/Application/msedge.exe", Path(pf) / "Microsoft/Edge/Application/msedge.exe"):
        if edge.is_file():
            subprocess.Popen([str(edge), f"--app={adresse}", "--window-size=1040,900"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return
    webbrowser.open(adresse)


def completer_path() -> None:
    """Adds MiKTeX to the server's PATH if missing (fresh install, session not restarted)."""
    miktex = Path(config().get("miktex") or
                  Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64")
    if not shutil.which("pdflatex") and miktex.is_dir():
        os.environ["PATH"] = f"{miktex}{os.pathsep}{os.environ['PATH']}"


# --------------------------------------------------------------------------- instructions for Claude

CONSIGNE_SYSTEME = (
    "Vous êtes piloté par l'interface graphique CV Booster, utilisée par une personne non technicienne. "
    "Répondez en français, en Markdown, court, en vouvoyant toujours la personne. Ne parlez jamais de "
    "commandes, de scripts, de chemins ni de fichiers techniques (cv.toml, .tex…) : dites « votre CV », « vos infos », « le design ». "
    "Vos consignes de rôle sont dans votre définition d'agent. Les Skills que vous utilisez et les fichiers utiles "
    "sont déjà dans le message : ne les relisez pas. "
    "Ici, le fichier de travail est .cv-booster/cv.toml (le dossier .cv-booster existe), les entrées sont "
    "dans ressources/, et la personne génère elle-même les PDF avec le bouton « Générer » : ne les générez pas. "
    "L'application enregistre tout : ne lui demandez jamais de télécharger ou remplacer un fichier. "
    # Saving: every tool used = a round trip that resends the whole context (≈ 20k tokens).
    "ÉCONOMIE (forfait limité) : ne listez pas les dossiers (tout est fourni) ; ne lancez PAS verifier_style.py "
    "ni aucune vérification du fichier : vérifiez vos propositions vous-même avec la Skill regles-ecriture et le lexique fournis ; "
    "l'application contrôle le fichier après vos modifications (et le restaure s'il est cassé). "
    "Pour MODIFIER son CV existant, n'utilisez aucun outil : terminez votre réponse par le bloc « modifications » "
    "décrit dans l'annexe modifications.md de format-cv (l'application l'applique). Pour tout autre fichier, une seule écriture."
)

# UI button → agent to run (file .claude/agents/<agent>.md) and its request.
# The agent brings the rest: instructions, tools, model, Skills (its definition is authoritative).
ACTIONS = {
    "importer": ("importeur", "Importez ses informations (ressources/, sauf ressources/design/) "
                 "dans .cv-booster/cv.toml."),
    "relire": ("relecteur", "Relisez son CV."),
    "reformuler": ("reformulateur", "Proposez des reformulations pour son CV."),
    "offre": ("adaptateur-offre", "Adaptez son CV à l'offre d'emploi ci-dessous (enregistrée dans {fichier})."),
    "version": ("adaptateur-offre", "Nouvelle version de son CV, sans annonce, pour ce type de poste : {texte}. "
                "Section « Sans annonce » de vos consignes."),
    "veille": ("veilleur-marche", "Faites la veille marché pour : {texte}."),
    "design": ("designer", "Inspirez-vous des exemples de ressources/design/ pour le design de son CV."),
    "sur_mesure": ("maquettiste", "Reproduisez la mise en page de son exemple (ressources/design/) dans "
                   "le dossier de son design (.cv-booster/designs/<design>/gabarit/gabarit.html)."),
    "lettre": ("redacteur-lettre", "Écrivez sa lettre de motivation pour l'offre ci-dessous (enregistrée dans {fichier})."),
    "entretien": ("preparateur-entretien", "Préparez son entretien d'embauche."),
    "anglais": ("traducteur", "Traduisez son CV en anglais dans .cv-booster/cv-en.toml (toutes les versions)."),
    "relance": ("redacteur-relance", "Rédigez un e-mail de relance pour la candidature ci-dessous."),
}
LIBELLES_ACTIONS = {"importer": "Créer mon CV", "relire": "Relire", "reformuler": "Reformuler",
                    "offre": "Adapter à une offre", "veille": "Veille marché", "design": "Design",
                    "sur_mesure": "Design sur mesure", "version": "Nouvelle version",
                    "lettre": "Lettre de motivation", "entretien": "Préparer un entretien", "perso": "Mon agent",
                    "anglais": "CV en anglais", "relance": "Message de relance", "repondre": "Réponse"}
AVEC_OFFRE = {"offre", "lettre", "entretien"}  # actions that receive the text of a job posting

# Permissions granted by the app (security): without asking, the agent can read, edit its files
# and search the web. The tools actually available are those declared in the agent's file.
AUTORISES = ["Read", "Edit", "Write", "Glob", "WebSearch", "WebFetch"]
EFFORTS = {"low", "medium", "high"}  # « effort: » field of an agent
# Saving options accepted by the installed Claude Code? (set to False if one is rejected: see
# lancer_claude). Claude Code's error message in that case: « error: unknown option '--xyz' », etc.
OPTIONS_ECO = {"ok": True}
OPTION_REFUSEE = re.compile(r"unknown option|unknown argument|unrecognized|invalid option|error: option|"
                            r"unknown flag|not a valid", re.I)
ETAPES = {  # tool used → progress label
    "Read": "Lecture…", "Glob": "Recherche des documents…", "Edit": "Modification de votre CV…",
    "Write": "Enregistrement…", "Bash": "Vérification…", "PowerShell": "Vérification…",
    "WebSearch": "Recherche sur le web…", "WebFetch": "Lecture d'une page web…",
}

# --------------------------------------------------------------------------- pre-chewed context
# Saving principle: everything predictable (reading the Skills, the CV, running the checks)
# is done here, in Python, and sent in one go. Otherwise Claude reads file by file, and each
# read is a round trip that resends the whole context (measured: 3 round trips ≈ 52k tokens
# for a proofread, versus just 1 this way).

EXTENSIONS_TEXTE = {".txt", ".md", ".csv", ".toml", ".json"}
EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8-sig", errors="replace")


def entete(chemin: Path) -> tuple[dict, str]:
    """.md file with a « --- key: value --- » header (format of Claude Code agents and Skills)."""
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
    # skills / annexes: custom fields (read by this server) saying what the agent must receive
    return {**meta, "skills": liste("skills"), "annexes": liste("annexes"), "outils": liste("tools")}


def script(nom: str, *args: str) -> str:
    res = subprocess.run([PYTHON, "-I", str(SCRIPTS[nom]), *args], cwd=RACINE,
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return (res.stdout or res.stderr).strip()


def texte_document(f: Path) -> str:
    """Text of a resource, extracted by script (without going through Claude)."""
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
    for skill in a["skills"]:          # tier 2: the SKILL.md of the Skills the agent declares it uses
        c += bloc(f"Skill {skill} (.claude/skills/{skill}/SKILL.md)", lire(SKILLS / skill / "SKILL.md"))
    for annexe in a["annexes"]:        # tier 3: only the annex files THIS agent needs
        c += bloc(f"Annexe de Skill : {annexe}", lire(SKILLS / annexe))
    if action not in {"importer", "relance"} and CV_TOML.is_file():  # the follow-up only needs the summary line
        c += bloc(f"{rel(CV_TOML)} (son CV)", lire(CV_TOML))
    if action in {"relire", "reformuler"} and CV_TOML.is_file():
        c += bloc("Résultat de verifier_style.py (déjà lancé)", script("verifier_style.py", str(CV_TOML)))
    if action == "offre" and offre and CV_TOML.is_file():  # job posting keywords already counted by script
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
                          f"mettez photo = \"{rel(f)}\".")
            elif texte := texte_document(f):
                c += bloc(f"{rel(f)} (texte extrait, barré = ~~écarté~~)", texte)
            else:
                c += bloc(rel(f), "Format non lu automatiquement : lisez-le vous-même si utile.")

    if action in {"design", "sur_mesure"}:
        designs = lister_designs()
        if action == "design":
            for d in designs:
                if (d / "design.toml").is_file():
                    c += bloc(f"{rel(d / 'design.toml')} (réglages actuels du design « {d.name} »)",
                              lire(d / "design.toml"))
        if action == "sur_mesure":
            polices = [rel(f) for f in sorted(ZONES["design"].iterdir())
                       if f.suffix.lower() in {".ttf", ".otf", ".woff", ".woff2"}]
            c += bloc("Polices fournies par elle (à citer par leur seul nom dans @font-face)",
                      "\n".join(polices) or "aucune : prenez la police Windows la plus proche")
            gabarits = [d / "gabarit" / "gabarit.html" for d in designs if (d / "gabarit" / "gabarit.html").is_file()]
            if len(gabarits) == 1:
                c += bloc(f"{rel(gabarits[0])} (design sur mesure actuel : pour une retouche, Edit ciblé)",
                          lire(gabarits[0]))
            elif gabarits:
                c += bloc("Designs sur mesure existants (pour une retouche, lisez seulement celui qu'elle vise)",
                          "\n".join(rel(g) for g in gabarits))
        exemples = [f for f in sorted(ZONES["design"].iterdir()) if f.suffix.lower() in EXTENSIONS_IMAGE | {".pdf"}]
        c += bloc(f"Dossier du design de chaque CV d'exemple ({MAX_DESIGNS} au plus)",
                  ("\n".join(f"{rel(f)} → {rel(DESIGNS / nom_design(f.name))}/" for f in exemples)
                   + "\nUne image sans aucun texte n'est PAS un exemple de plus et n'a pas de dossier : c'est le fond "
                     "du CV d'exemple qu'elle accompagne, à utiliser tel quel dans le design de cet exemple.")
                  if exemples else "aucun exemple")
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
        titre = "Exemples à regarder (une seule fois chacun, avec Read)"
        if action == "sur_mesure":
            titre += (". Une image SANS aucun texte (fond ou décor qu'elle a fourni) peut servir telle quelle ; "
                      "une image de CV complet sert seulement à regarder, jamais comme image du design")
        c += bloc(titre, "\n".join(images) or "aucun")

    if action == "veille":
        fiches = sorted((TRAVAIL / "tendances").glob("*.md")) if (TRAVAIL / "tendances").is_dir() else []
        c += bloc("Fiches de veille existantes", "\n".join(
            f"{rel(f)} (modifiée le {datetime.fromtimestamp(f.stat().st_mtime):%Y-%m-%d})" for f in fiches) or "aucune")
        c += bloc("Date du jour", f"{datetime.now():%Y-%m-%d}")

    return ("Tout le contexte utile est ci-dessous, déjà lu pour vous : ne relisez pas ces fichiers "
            "(sauf juste avant de les modifier). Votre tâche est à la fin." + c)


# --------------------------------------------------------------------------- Claude tasks

TACHES: dict[str, dict] = {}
VERROU = threading.Lock()
SAUVEGARDE = TRAVAIL / "cv.toml.sauvegarde"


def controler_cv() -> str:
    """After Claude's pass: the CV must always parse. Otherwise, restore the previous version.
    Done here in Python rather than by Claude (each check by Claude costs a round trip)."""
    if not CV_TOML.is_file():
        return ""
    try:
        tomllib.loads(CV_TOML.read_text(encoding="utf-8-sig"))
        return ""
    except tomllib.TOMLDecodeError:
        if SAUVEGARDE.is_file():
            shutil.copy(SAUVEGARDE, CV_TOML)
            return ("\n\n> Attention : une modification avait abîmé votre CV : j'ai remis la version d'avant. "
                    "Redemandez la modification, en une phrase.")
        return "\n\n> Attention : votre CV n'a pas pu être créé correctement : relancez « Importer mes infos »."


def appliquer_bloc(reponse: str) -> str:
    """An agent's « modifications » block (format-cv Skill) → applied to the CV by script, in one go.
    Without it, each edit made with the Edit tool cost a full round trip (12 for a
    proofread: 47,000 tokens). The block is removed from the displayed answer, replaced by a summary."""
    m = _module(SCRIPTS["appliquer.py"])
    if not m or not reponse:
        return reponse
    bloc, reste = m.extraire(reponse)
    if bloc is None:
        return reponse
    if not CV_TOML.is_file():
        return reste
    r = m.appliquer(CV_TOML, bloc)
    if r["erreur"]:
        services.noter_erreur(f"bloc modifications : {r['erreur']}")
        return reste + ("\n\n> Je n'ai pas pu appliquer les modifications : rien n'a changé dans votre CV. "
                        "Répondez « réessayez ».")
    n = r["appliquees"]
    fait = f"{n} modification{'s' if n > 1 else ''} appliquée{'s' if n > 1 else ''}" if n else ""
    if r["ajout"]:
        fait = (fait + " et " if fait else "") + "la nouvelle version ajoutée"
    msg = f"\n\n> C'est fait : {fait or 'rien à changer'} dans votre CV."
    if r["introuvables"]:
        k = len(r["introuvables"])
        msg += f" {k} modification{'s' if k > 1 else ''} n'{'ont' if k > 1 else 'a'} pas pu être appliquée{'s' if k > 1 else ''} (texte introuvable) : redemandez-la si besoin."
    return reste + msg


def lancer_claude(tache: dict, invite: str, nom_agent: str, reprise: str | None) -> None:
    claude = trouver_claude()
    if not claude:
        tache.update(etat="erreur", reponse="Claude Code est introuvable. Relancez l'installation de CV Booster.")
        return
    if CV_TOML.is_file():  # safety net: the version from before the task
        shutil.copy(CV_TOML, SAUVEGARDE)
        services.archiver_cv(f"Avant : {LIBELLES_ACTIONS.get(tache.get('titre'), tache.get('titre', ''))}")
    if nom_agent in {"designer", "maquettiste"}:  # which design the agent changes (snapshot kept for the review)
        tache.setdefault("empreinte", empreinte_designs())
    # The prompt goes through stdin: the Windows command line is limited to ~32,000 characters.
    a = agent(nom_agent)
    base = [claude, "-p", "--output-format", "stream-json", "--verbose",
            "--agent", nom_agent,  # instructions, tools, model: those of .claude/agents/<nom>.md
            "--permission-mode", "acceptEdits", "--allowedTools", *AUTORISES,
            "--append-system-prompt", CONSIGNE_SYSTEME]
    # Saving (measured 05/11): only the agent's tools are described to the model; neither the connectors
    # of the claude.ai account (Gmail, Drive… otherwise loaded in EVERY task), nor the commands, nor the
    # personal Claude Code settings.
    eco = ["--tools", ",".join(a["outils"]) or "", "--strict-mcp-config", "--disable-slash-commands",
           "--setting-sources", "project",
           # Responsiveness: text streams in (1st chunk in < 1 s) and is shown while being written,
           # instead of one block at the end. No extra tokens.
           "--include-partial-messages"]
    # Thinking effort (custom « effort: » field of the agent). What the model writes, thinking included,
    # costs ~5 times more than what it reads: « low » cuts the written tokens of a proofread by 4, at equal
    # quality (compared 05/11). Default « medium » (Claude Code uses « high »).
    # The « puissance » chosen in Améliorer can override everything: Faible (Haiku, low effort), Fort (Sonnet,
    # high effort). Moyen keeps each agent's setting.
    puissance = services.reglages()["puissance"]
    if puissance == "faible" and a.get("plancher") == "moyen":
        # Custom field « plancher: moyen » (designer, layout agent): Haiku does worse there AND uses more,
        # through round trips (measured 06/11 on a design: 58k tokens versus 37k in Moyen).
        puissance = "moyen"
    force = services.PUISSANCES[puissance]
    tache["puissance"] = puissance
    modele = ["--model", force["modele"]] if force else []
    eco += ["--effort", force["effort"] if force else (a.get("effort") if a.get("effort") in EFFORTS else "medium")]
    suite = ["--resume", reprise] if reprise else []
    # Safety net: Claude Code updates itself on her machine. If a saving option is renamed
    # or removed, it rejects it BEFORE any model call (so nothing is spent): we then rerun the
    # task without those options. The app keeps working, just a bit hungrier, and the incident is logged.
    tentatives = [base + modele + eco + suite, base + modele + suite] if OPTIONS_ECO["ok"] else [base + modele + suite]

    def executer(cmd: list[str]) -> tuple[str | None, str]:
        """Runs Claude Code, tracks its progress. Returns (« fini » / « erreur » / None, stderr tail)."""
        proc = subprocess.Popen(cmd, cwd=RACINE, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        tache["proc"] = proc
        try:
            proc.stdin.write(invite)
            proc.stdin.close()
        except OSError:  # immediate rejection (unknown option): Claude Code has already stopped
            pass
        res = None
        for ligne in proc.stdout:
            try:
                msg = json.loads(ligne)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "system" and msg.get("subtype") == "init":
                tache["etape"] = "Lecture de votre CV…"
                continue
            if msg.get("type") == "stream_event":  # text chunks being written
                ev = msg.get("event", {})
                if ev.get("type") == "message_start":
                    tache["partiel"] = ""
                elif ev.get("type") == "content_block_start" and ev.get("content_block", {}).get("type") in ("thinking", "redacted_thinking"):
                    tache["etape"] = "Réflexion…"
                elif ev.get("type") == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                    tache["partiel"] = tache.get("partiel", "") + ev["delta"].get("text", "")
                    tache["etape"] = "Rédaction de la réponse…"
                continue
            if msg.get("type") == "assistant":
                for bloc in msg.get("message", {}).get("content", []):
                    if bloc.get("type") == "tool_use":
                        tache["etape"] = ETAPES.get(bloc.get("name"), "Travail en cours…")
                    elif bloc.get("type") == "text" and bloc.get("text", "").strip():
                        tache["etape"] = "Rédaction de la réponse…"
            elif msg.get("type") == "result":
                u = msg.get("usage", {})
                res = "erreur" if msg.get("is_error") else "fini"
                tache.update(
                    partiel="",
                    session=msg.get("session_id"),
                    tours=msg.get("num_turns", 0),
                    reponse=msg.get("result") or "",
                    tokens=sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                     "cache_read_input_tokens", "output_tokens")),
                    # API-equivalent cost: weighs input, cache and output (close to what counts against the plan)
                    cout=round(msg.get("total_cost_usd") or 0, 4),
                    ecrits=u.get("output_tokens", 0),  # what the model writes (thinking included): the most expensive
                    modeles=sorted(msg.get("modelUsage", {})),  # model(s) actually used
                )
        proc.wait()
        return res, proc.stderr.read().strip()

    try:
        for i, cmd in enumerate(tentatives):
            resultat, erreur_brute = executer(cmd)
            if resultat or i == len(tentatives) - 1 or not OPTION_REFUSEE.search(erreur_brute):
                break
            OPTIONS_ECO["ok"] = False  # for the rest of the session: straight without those options
            services.noter_erreur(f"Claude Code refuse une option d'économie, tâche relancée sans : {erreur_brute[-300:]}")
            tache["etape"] = "Démarrage…"
        tache["reponse"] = appliquer_bloc(tache["reponse"])  # CV edits: applied by script
        tache["reponse"] += controler_cv()  # before announcing the end: the UI shows the full answer
        if nom_agent == "redacteur-lettre":
            tache["reponse"] += generer_lettres()  # the letter's PDF, right away (a script, not Claude)
        if nom_agent == "traducteur" and CV_EN.is_file():  # the translation must parse, otherwise it is discarded
            try:
                tomllib.loads(lire(CV_EN))
            except tomllib.TOMLDecodeError as e:
                CV_EN.replace(CV_EN.with_suffix(".toml.illisible"))
                services.noter_erreur(f"cv-en.toml illisible : {e}")
                tache["reponse"] += "\n\n> Attention : la traduction n'a pas pu être enregistrée correctement. Relancez « Anglais »."
        if nom_agent == "maquettiste":
            note = apres_maquettiste(tache)  # turns on the custom design, builds the PDF and its preview
            if not (tache.get("rendu") and not tache.get("ajuste")):
                tache["reponse"] += note  # otherwise: visual review below, the note will come after it
        elif nom_agent == "designer":
            for d in designs_modifies(tache.get("empreinte", {})):
                regler_sur_mesure(False, d)  # the Design « réglages » takes back control of that design
            generer_lettres(toutes=True)  # and the letters go back to the classic layout, in its colours
        if resultat:  # usage, for the « Votre consommation » screen (Coulisses)
            services.noter_conso(tache.get("titre", ""), nom_agent,
                                 ",".join(tache.get("modeles", [])) or agent(nom_agent).get("model", ""),
                                 tache.get("tokens", 0), round(time.time() - tache.get("debut", time.time())),
                                 bool(reprise), tache.get("cout", 0), tache.get("puissance", "moyen"))
        if (resultat and nom_agent == "maquettiste" and tache.get("rendu")
                and not tache.get("ajuste") and tache.get("session")):
            # Visual review, ONCE, in the same task (the UI keeps following): the agent writes
            # blind, now it looks at the preview of the real PDF (text on a background, repeated section,
            # overflow, gap from the example) and fixes. Measured: one more turn, ~$0.08.
            tache["ajuste"] = True
            avant = tache["reponse"].rstrip()
            tache["etape"] = "Vérification du rendu…"
            lancer_claude(tache, consigne_relecture(tache["rendu"], tache.get("design_revu", "")), nom_agent,
                          tache["session"])  # finalizes the task
            if tache["etat"] != "erreur":
                tache["reponse"] = avant + "\n\n" + tache["reponse"].lstrip()
            return
        if resultat:
            tache["etat"] = resultat
        else:
            erreur = erreur_brute[-600:]
            tache.update(etat="erreur", reponse=erreur or "Claude s'est arrêté sans réponse.")
        if tache["etat"] == "erreur":  # translate common errors into plain French
            brut = tache["reponse"]
            services.noter_erreur(f"tâche « {tache.get('titre')} » ({nom_agent}) : {brut[-400:]}")
            if re.search(r"/login|log ?in|not logged|authenticat|credential|api key|oauth", brut, re.I):
                tache.update(connexion=True, reponse="Claude n'est pas connecté à votre compte (ou la connexion a "
                             "expiré). Cliquez sur « Me connecter à Claude », connectez-vous dans la page qui "
                             "s'ouvre, puis réessayez.")
                CONNEXION.update(connecte=False, verifie=time.time())  # Accueil offers it too
            elif re.search(r"usage limit|rate limit|quota|limit reached", brut, re.I):
                tache["reponse"] = ("Limite d'utilisation de votre forfait atteinte. Elle se recharge au bout de "
                                    "quelques heures : réessayez plus tard.")
    except Exception as e:  # noqa: BLE001 - always hand control back to the UI
        services.noter_erreur(f"tâche « {tache.get('titre')} » ({nom_agent}) : exception {e!r}")
        tache.update(etat="erreur", reponse=f"Erreur inattendue : {e}")


def nom_design(texte: str) -> str:
    """Folder name of a design, from its example's file name (« DA-blue.png » → « DA-blue »)."""
    return re.sub(r"[^\w -]+", " ", Path(texte).stem).strip()[:40].strip() or "Mon design"


def migrer_design() -> None:
    """Up to 1.4 there was a single design (.cv-booster/design.toml + gabarit/): moved to designs/<example>/."""
    ancien, gabarit = TRAVAIL / "design.toml", TRAVAIL / "gabarit"
    if not (ancien.is_file() or gabarit.is_dir()) or (DESIGNS.is_dir() and any(DESIGNS.iterdir())):
        return
    exemples = [f.name for f in sorted(ZONES["design"].iterdir())
                if f.suffix.lower() in EXTENSIONS_IMAGE | {".pdf"}] if ZONES["design"].is_dir() else []
    cible = DESIGNS / nom_design(exemples[0] if exemples else "")
    cible.mkdir(parents=True, exist_ok=True)
    if ancien.is_file():
        ancien.replace(cible / "design.toml")
    if gabarit.is_dir():
        gabarit.replace(cible / "gabarit")


def lister_designs() -> list[Path]:
    """The designs, in name order (the first one also dresses the cover letters), 3 at most."""
    migrer_design()
    if not DESIGNS.is_dir():
        return []
    return sorted((d for d in DESIGNS.iterdir() if d.is_dir() and ((d / "design.toml").is_file()
                                                                 or (d / "gabarit" / "gabarit.html").is_file())),
                  key=lambda d: d.name.lower())[:MAX_DESIGNS]


def empreinte_designs() -> dict:
    return {str(f): f.stat().st_mtime_ns for f in DESIGNS.rglob("*") if f.is_file()} if DESIGNS.is_dir() else {}


def designs_modifies(avant: dict) -> list[Path]:
    """Designs whose files changed since the snapshot (taken when the agent started)."""
    noms = {Path(k).relative_to(DESIGNS).parts[0] for k, v in empreinte_designs().items() if avant.get(k) != v}
    return [d for d in lister_designs() if d.name in noms]


def supprimer_design(d: Path) -> None:
    """A design and its PDFs (every version, French and English)."""
    gen = _generateur()
    for source in (CV_TOML, CV_EN):
        if gen and source.is_file():
            try:
                cv = tomllib.loads(lire(source))
            except tomllib.TOMLDecodeError:
                continue
            for k in cv.get("variantes", {}):
                (SORTIE / gen.nom_pdf(cv, k, d.name)).unlink(missing_ok=True)
    shutil.rmtree(d, ignore_errors=True)


def regler_sur_mesure(actif: bool, dossier: Path) -> None:
    """[page] sur_mesure in the design's design.toml: custom template (gabarit/) or simple settings."""
    f = dossier / "design.toml"
    texte = lire(f) if f.is_file() else ""
    ligne = f"sur_mesure = {'true' if actif else 'false'}"
    if re.search(r"^\s*sur_mesure\s*=.*$", texte, re.M):
        texte = re.sub(r"^\s*sur_mesure\s*=.*$", ligne, texte, count=1, flags=re.M)
    elif not actif:
        return  # nothing to turn off
    elif re.search(r"^\[page\]\s*$", texte, re.M):
        texte = re.sub(r"^\[page\]\s*$", f"[page]\n{ligne}", texte, count=1, flags=re.M)
    else:
        texte = (texte.rstrip() + "\n\n" if texte.strip() else "") + f"[page]\n{ligne}\n"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(texte, encoding="utf-8")


RENDU_DEBORDE = "PDF produit, mais il dépasse une page, même avec le texte réduit de 20 %."
APERCU_SUR_MESURE = TRAVAIL / "build" / "apercu-sur-mesure.png"


def consigne_relecture(rendu: str, design: str = "") -> str:
    """Message for the visual review (layout agent's 2nd turn, sent by the app)."""
    exemples = [f for f in sorted(ZONES["design"].iterdir())
                if f.suffix.lower() in EXTENSIONS_IMAGE] if ZONES["design"].is_dir() else []
    exemples = [f.relative_to(RACINE).as_posix() for f in
                ([f for f in exemples if nom_design(f.name) == design] or exemples)]
    voir = (f"Regardez l'aperçu {APERCU_SUR_MESURE.relative_to(RACINE).as_posix()} une seule fois (Read) et "
            f"comparez-le côte à côte à l'exemple ({', '.join(exemples[:2]) or 'déjà vu'}, relisez-le si besoin) : "
            "positions et proportions des zones en pourcentage de la page, taille et place des formes, "
            "couleurs, police. " if APERCU_SUR_MESURE.is_file() else "")
    return (f"(Génération du PDF par l'application : {rendu}) {voir}Corrigez en un seul Edit ce qui ne va pas : "
            "texte posé sur un décor ou peu lisible, rubrique répétée ou absente, page qui dépasse (rubriques "
            "courtes dans la colonne la plus libre, espacements resserrés, texte courant pas sous 9 pt), écart "
            "visible avec l'exemple (forme et souplesse des décors, police, numérotation, alignements, air "
            "entre les rubriques, couleurs). "
            "Si tout va bien, ne modifiez rien. Répondez en une ou deux phrases simples sur ce "
            "que vous avez changé, sans répéter votre réponse précédente, sans détail technique (tailles, "
            "millimètres) et sans parler de vérification : l'application regénère le PDF juste après.")


def apres_maquettiste(tache: dict) -> str:
    """After the layout agent: custom design on, PDF of the 1st version built right away (script).
    The report is kept for its next answer (tache["rendu"]): the agent will know what to fix."""
    d = next((d for d in designs_modifies(tache.get("empreinte", {}))
              if (d / "gabarit" / "gabarit.html").is_file()), None)
    if not d:
        return ""
    if not CV_TOML.is_file():
        return "\n\n> Créez d'abord votre CV : le design sera rempli avec."
    regler_sur_mesure(True, d)
    tache["design_revu"] = d.name
    variantes = list(tomllib.loads(lire(CV_TOML)).get("variantes", {}))
    if not variantes:
        return ""
    r = generer(variantes[0], seulement=d)
    APERCU_SUR_MESURE.unlink(missing_ok=True)
    design = next((SORTIE / f for f in r.get("fichiers", []) if not f.endswith("_ATS.pdf")), None)
    if r["ok"] and design and design.is_file() and shutil.which("pdftoppm"):  # for the visual review
        # 80 dpi: sharp enough to judge the quality of curves and alignments (~800 image tokens)
        subprocess.run(["pdftoppm", "-png", "-r", "80", "-singlefile", str(design), str(APERCU_SUR_MESURE.with_suffix(""))],
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if not r["ok"]:
        tache["rendu"] = r["message"]
        services.noter_erreur(f"design sur mesure : {r['message']}")
        return ("\n\n> Le PDF n'a pas pu être produit avec ce design. Répondez « corrigez » : "
                "je reçois l'erreur et je reprends le design.")
    if not r["pages_ok"]:
        tache["rendu"] = f"Problème : {r['alerte'] or RENDU_DEBORDE}"
    elif r["lisibilite"]:  # measured by the engine: the visual review must fix it
        tache["rendu"] = f"Problème : {r['lisibilite']} (contraste trop faible : déplacez le texte ou le décor)."
    else:
        tache["rendu"] = "PDF produit, tout le texte lisible."
    designs = lister_designs()
    if len(designs) > 1:
        note = (f"\n\n**Votre design sur mesure « {d.name} » est prêt** dans Mes CV. "
                "Cliquez sur « Générer le PDF » pour l'appliquer à vos autres versions.")
    else:
        note = ("\n\n**Votre design sur mesure est prêt** dans Mes CV. "
                "La version ATS, sobre, pour les sites d'emploi, est faite aussi.")
    if (d == designs[0] and (d / "gabarit" / "lettre.html").is_file() and LETTRES.is_dir()
            and any(LETTRES.glob("*.toml"))):
        note += " Vos lettres de motivation suivent ce design." + generer_lettres(toutes=True)
    if r["pages_ok"] and r["lisibilite"] and tache.get("ajuste"):  # still there after the review: say so
        note += (f"\n\n> Un texte reste difficile à lire sur un décor ({r['lisibilite'].split(' : ', 1)[-1]}). "
                 "Répondez « corrigez la lisibilité » pour que je le reprenne.")
    if not r["pages_ok"] or r["echelle"] <= 90:
        # Her content is longer than the design allows: say so, and she chooses.
        etat_page = "Il dépasse la page" if not r["pages_ok"] else f"Le texte a été réduit à {r['echelle']} % pour tenir"
        note += (f"\n\n> {etat_page} : votre CV est plus long que ce que ce design prévoit, il est donc moins aéré "
                 "que l'exemple. Deux possibilités : l'alléger (Améliorer › Reformuler, en demandant « une version "
                 "plus courte »), ou répondre ici « sur deux pages ».")
    return note


def generer_lettres(toutes: bool = False) -> str:
    """Lays out the edited letters (or all of them): PDFs in CV/. Returns a warning, otherwise ""."""
    if not (LETTRES.is_dir() and CV_TOML.is_file() and shutil.which("pdflatex")):
        return ""
    designs = lister_designs()  # the letters follow the first design
    res = subprocess.run([PYTHON, "-I", str(GENERER_LETTRE), "--source", str(CV_TOML), "--sortie", str(SORTIE)]
                         + (["--toutes"] if toutes else [])
                         + (["--dossier-design", str(designs[0])] if designs else []),
                         cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         creationflags=SANS_FENETRE)
    sortie = res.stdout + res.stderr
    if "Échec" in sortie or "illisible" in sortie:
        return "\n\n> Attention : le PDF de la lettre n'a pas pu être créé. Demandez : « corrigez le fichier de la lettre »."
    if "ATTENTION" in sortie:
        return "\n\n> Attention : la lettre dépasse une page : demandez une version plus courte."
    return ""


def nouvelle_tache(invite: str, nom_agent: str, reprise: str | None, titre: str) -> str:
    with VERROU:
        if any(t["etat"] == "en_cours" for t in TACHES.values()):
            raise RuntimeError("Une tâche est déjà en cours : attendez qu'elle se termine.")
        tid = uuid.uuid4().hex[:8]
        TACHES[tid] = {"etat": "en_cours", "etape": "Démarrage…", "reponse": "", "titre": titre,
                       "session": reprise, "agent": nom_agent, "tokens": 0, "debut": time.time()}
    threading.Thread(target=lancer_claude, args=(TACHES[tid], invite, nom_agent, reprise), daemon=True).start()
    return tid


# --------------------------------------------------------------------------- file status

def lister(dossier: Path) -> list[str]:
    if not dossier.is_dir():
        return []
    return sorted(f.name for f in dossier.iterdir() if f.is_file() and not f.name.startswith("."))


def prenom_session() -> str:
    """First name of the Windows session (account display name, otherwise login): the tool isn't tied to anyone."""
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
    """A Skill script, imported to reuse its functions (PDF naming, matching…) without
    running it. Kept in memory as long as the file doesn't change."""
    try:
        cle = (str(chemin), chemin.stat().st_mtime)
        if cle not in _MODULES:
            import importlib.util  # noqa: PLC0415
            if str(chemin.parent) not in sys.path:
                sys.path.insert(0, str(chemin.parent))  # generer_lettre imports generer_cv
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
    variantes, nom, rubriques, libelles, cles = [], "", [], {}, {}  # cles: PDF name → version key
    designs = [d.name for d in lister_designs()]
    par_design = {}  # with several designs: PDF name → {base: PDF name without design, design: its name}

    def noter_designs(gen, cv: dict, k: str, libelle: str, cle: str = "") -> None:
        if len(designs) > 1:
            base = gen.nom_pdf(cv, k)
            for nd in designs:
                n = gen.nom_pdf(cv, k, nd)
                libelles[n], cles[n], par_design[n] = libelle, cle or k, {"base": base, "design": nd}
    if CV_TOML.is_file():
        try:
            cv = tomllib.loads(CV_TOML.read_text(encoding="utf-8-sig"))
            variantes = [{"cle": k, "titre": v.get("titre", k)} for k, v in cv.get("variantes", {}).items()]
            nom = cv.get("identite", {}).get("nom", "")
            # Sections offered in the « Quelle partie reformuler ? » menu
            rubriques = ["L'accroche"] + [f"Expérience : {e.get('poste', '')} – {e.get('entreprise', '')}"
                                          for e in cv.get("experiences", [])] + ["Les compétences"]
            # Readable label of each PDF (with accents), recovered through the generator's naming rule
            gen = _generateur()
            titres = [v["titre"] for v in variantes]
            for v in variantes:
                libelle = v["titre"] + (f" · {v['cle'].replace('_', ' ')}" if titres.count(v["titre"]) > 1 else "")
                v["libelle"] = libelle
                if gen:
                    libelles[gen.nom_pdf(cv, v["cle"])] = libelle
                    cles[gen.nom_pdf(cv, v["cle"])] = v["cle"]
                    noter_designs(gen, cv, v["cle"], libelle)
            # Cover letters: « Lettre · Entreprise »
            gl = _module(GENERER_LETTRE)
            for f in sorted(LETTRES.glob("*.toml")) if LETTRES.is_dir() and gl else []:
                try:
                    lettre = tomllib.loads(lire(f))
                    libelles[gl.nom_pdf(cv, lettre)] = f"Lettre · {lettre.get('entreprise', f.stem)}"
                except tomllib.TOMLDecodeError:
                    pass
        except tomllib.TOMLDecodeError:
            pass
    anglais = {}  # PDF name → "en": the UI shows a small flag
    if CV_EN.is_file():
        try:
            cv_en, gen = tomllib.loads(lire(CV_EN)), _generateur()
            titres_en = [v.get("titre", k) for k, v in cv_en.get("variantes", {}).items()]
            for k, v in cv_en.get("variantes", {}).items():
                titre = v.get("titre", k)
                if titres_en.count(titre) > 1:  # same title: specify the version (as in French)
                    titre += f" · {k.replace('_', ' ')}"
                variantes.append({"cle": f"en:{k}", "titre": titre, "libelle": f"{titre} (anglais)", "langue": "en"})
                if gen:
                    libelles[gen.nom_pdf(cv_en, k)] = titre
                    anglais[gen.nom_pdf(cv_en, k)] = "en"
                    cles[gen.nom_pdf(cv_en, k)] = f"en:{k}"
                    noter_designs(gen, cv_en, k, titre, f"en:{k}")
        except tomllib.TOMLDecodeError:
            pass
    for n in list(libelles):  # the Word export has the same name as the PDF
        if n.endswith(".pdf"):
            libelles[n[:-4] + ".docx"] = libelles[n]
    perso = [{"nom": f.stem, "libelle": agent(f.stem).get("libelle", f.stem),
              "description": agent(f.stem).get("description", "")}
             for f in sorted(AGENTS.glob("*.md")) if services.agent_perso(f.stem)] if AGENTS.is_dir() else []
    return {
        "agents_perso": perso, "version": services.version_locale()["version"], "anglais": anglais,
        "cv_anglais": CV_EN.is_file(), "cles": cles, "designs": designs, "par_design": par_design,
        "infos": lister(ZONES["infos"]), "design": lister(ZONES["design"]), "cv": lister(SORTIE),
        "cv_importe": CV_TOML.is_file(), "nom": nom, "variantes": variantes, "rubriques": rubriques,
        "prenom_session": prenom_session(), "libelles": libelles,
        # date of each PDF: the UI uses it to reload the preview when the PDF changes
        "cv_dates": {n: int((SORTIE / n).stat().st_mtime) for n in lister(SORTIE)},
        "cv_modifie": int(CV_TOML.stat().st_mtime) if CV_TOML.is_file() else 0,  # for « modifié le … »
        "claude": bool(trouver_claude()), "pdflatex": bool(shutil.which("pdflatex")),
        "claude_connecte": claude_connecte(),
    }


APERCUS = TRAVAIL / "apercus"
_VERROUS_APERCU: dict[str, threading.Lock] = {}
_VERROU_DICT = threading.Lock()
_CONVERSIONS = threading.Semaphore(2)  # at most 2 conversions at once (otherwise the machine crawls)


def apercu(nom_pdf: str, dossier: Path = SORTIE) -> Path | None:
    """1st page of the PDF as an image (pdftoppm, shipped with MiKTeX). Recomputed only if the PDF changed.
    Rapid clicks: one conversion per file at a time (other requests wait, then
    serve the result), written to a temp file swapped in at once (never a
    half-written image)."""
    pdf = dossier / nom_pdf
    if pdf.suffix.lower() != ".pdf" or not pdf.is_file() or not shutil.which("pdftoppm"):
        return None
    image = APERCUS / (f"{pdf.stem}.png" if dossier == SORTIE else f"exemple-{pdf.stem}.png")
    with _VERROU_DICT:
        verrou = _VERROUS_APERCU.setdefault(pdf.name, threading.Lock())
    with verrou:
        if not image.is_file() or image.stat().st_mtime < pdf.stat().st_mtime:
            APERCUS.mkdir(parents=True, exist_ok=True)
            temp = APERCUS / f"{pdf.stem}.en-cours"
            with _CONVERSIONS:
                subprocess.run(["pdftoppm", "-png", "-r", "110" if dossier == SORTIE else "40", "-f", "1", "-l", "1", "-singlefile", str(pdf),
                                str(temp)], capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if temp.with_suffix(".en-cours.png").is_file():
                os.replace(temp.with_suffix(".en-cours.png"), image)
    return image if image.is_file() else None


def prechauffer_apercus(fichiers: list[str]) -> None:
    """Right after « Générer »: builds the previews in the background, so a click shows them instantly."""
    def travail():
        for f in fichiers:
            apercu(f)
    threading.Thread(target=travail, daemon=True).start()


def coulisses() -> dict:
    """For learning: the agents and Skills, read straight from their files (always up to date)."""
    rel = lambda p: p.relative_to(RACINE).as_posix()  # noqa: E731
    boutons = {nom: action for action, (nom, _) in ACTIONS.items()}
    agents = []
    for f in sorted(AGENTS.glob("*.md")):
        a = agent(f.stem)
        agents.append({"nom": a.get("name", f.stem), "description": a.get("description", ""),
                       "modele": a.get("model", ""), "outils": a["outils"], "skills": a["skills"],
                       "annexes": a["annexes"], "fichier": rel(f), "bouton": boutons.get(f.stem),
                       "perso": services.agent_perso(f.stem), "libelle": a.get("libelle", ""),
                       "effort": a.get("effort") if a.get("effort") in EFFORTS else "medium"})
    skills = []
    for d in sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()):
        meta, _ = entete(d / "SKILL.md")
        fichiers = []
        for x in sorted(d.rglob("*")):
            if not x.is_file() or x.suffix == ".pyc":
                continue
            interne = x.relative_to(SKILLS).as_posix()  # e.g. format-cv/lecture-documents.md
            role = ("principal" if x.name == "SKILL.md" else "script" if x.parent.name == "scripts" else "annexe")
            fichiers.append({"nom": x.relative_to(d).as_posix(), "chemin": rel(x), "role": role,
                             "charge_par": [a["nom"] for a in agents if interne in a["annexes"]]})
        skills.append({"nom": meta.get("name", d.name), "description": meta.get("description", ""),
                       "fichier": rel(d / "SKILL.md"), "fichiers": fichiers,
                       "utilisee_par": [a["nom"] for a in agents if d.name in a["skills"]]})
    return {"agents": agents, "skills": skills}


def source_variante(variante: str) -> tuple[Path, str]:
    """« en:cle » = a version of the English CV (cv-en.toml); otherwise a version of the French CV."""
    return (CV_EN, variante[3:]) if variante.startswith("en:") else (CV_TOML, variante)


def retirer_variante(chemin: Path, cle: str) -> None:
    """Removes [variantes.<cle>] and its subtables (remplacements…) from the file, leaving the rest as is.
    The result is reparsed: if it no longer parses, or the version is still there, nothing is written."""
    garde, dedans = [], False
    for ligne in lire(chemin).splitlines(keepends=True):
        if m := re.match(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(#.*)?$", ligne):
            nom = m.group(1).replace('"', "").replace("'", "")
            dedans = nom == f"variantes.{cle}" or nom.startswith(f"variantes.{cle}.")
        if not dedans:
            garde.append(ligne)
    texte = "".join(garde)
    if cle in tomllib.loads(texte).get("variantes", {}):
        raise ValueError("La version n'a pas pu être retirée.")
    chemin.write_text(texte, encoding="utf-8")


def supprimer_version(variante: str) -> dict:
    """Deletes a CV version (and, for a French version, its English translation), with its PDFs and its
    Word file. The CV is first set aside (Mes CV › Versions précédentes). The last version is refused."""
    source, cle = source_variante(variante)
    if not source.is_file():
        raise ValueError("CV introuvable.")
    variantes = tomllib.loads(lire(source)).get("variantes", {})
    if cle not in variantes:
        raise ValueError("Version introuvable.")
    if source == CV_TOML and len(variantes) <= 1:
        raise ValueError("C'est la seule version de votre CV : il en faut au moins une.")
    spec = importlib.util.spec_from_file_location("generer_cv_noms", GENERER)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)  # same file names as generation (compute BEFORE removing)
    cibles = [(source, cle)] + ([(CV_EN, cle)] if source == CV_TOML and CV_EN.is_file() else [])
    supprimes = 0
    services.archiver_cv(f"Avant : suppression de la version « {variantes[cle].get('titre', cle)} »")
    for chemin, k in cibles:
        cv = tomllib.loads(lire(chemin))
        if k not in cv.get("variantes", {}):
            continue
        gen.choisir_langue(cv)
        pdf = SORTIE / gen.nom_pdf(cv, k)
        for f in (pdf, pdf.with_name(pdf.stem + "_ATS.pdf"), pdf.with_suffix(".docx")):
            if f.is_file():
                f.unlink()
                supprimes += 1
        retirer_variante(chemin, k)
    return {"ok": True, "fichiers": supprimes, "anglais": len(cibles) > 1}


def exporter_word(variante: str) -> dict:
    source, cle = source_variante(variante)
    res = subprocess.run([PYTHON, "-I", str(GENERER_DOCX), "--source", str(source), "--variante", cle,
                          "--sortie", str(SORTIE)], cwd=RACINE, capture_output=True, text=True, encoding="utf-8",
                         errors="replace", creationflags=SANS_FENETRE)
    fichier = re.search(r"Word généré : (.+?\.docx)", res.stdout)
    if res.returncode or not fichier:
        services.noter_erreur(f"export Word : {(res.stdout + res.stderr)[-300:]}")
        raise ValueError("L'export Word a échoué. Lancez une relecture : un caractère de votre CV pose sûrement problème.")
    return {"fichier": Path(fichier.group(1).strip()).name}


def generer(variante: str, seulement: Path | None = None) -> dict:
    """PDFs of a version: one per design (named after it when there are several), and the ATS version
    once, in the colours of the first design. seulement: that design only (layout agent's review)."""
    source, variante = source_variante(variante)
    designs = lister_designs()
    plusieurs = len(designs) > 1
    passes = [(d, i == 0) for i, d in enumerate(designs) if not seulement or d == seulement] or [(None, True)]
    gen = _generateur()
    if gen and designs and not seulement:  # PDFs of a deleted design, or named for another number of designs
        try:
            cv = tomllib.loads(lire(source))
            attendus = {gen.nom_pdf(cv, variante, d.name if plusieurs else "") for d in designs}
            anciens = {gen.nom_pdf(cv, variante)} | {gen.nom_pdf(cv, variante, d.name)
                                                     for d in DESIGNS.iterdir() if d.is_dir()}
            for n in anciens - attendus:
                (SORTIE / n).unlink(missing_ok=True)
        except (tomllib.TOMLDecodeError, KeyError):
            pass
    sorties, ok = [], True
    for d, ats in passes:
        cmd = [PYTHON, "-I", str(GENERER), "--source", str(source), "--variante", variante, "--sortie", str(SORTIE)]
        if d:
            cmd += ["--dossier-design", str(d)] + (["--nom-design", d.name] if plusieurs else [])
        if not ats:
            cmd.append("--sans-ats")
        res = subprocess.run(cmd, cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        sorties.append((res.stdout + res.stderr).strip())
        ok = ok and res.returncode == 0
    sortie = "\n".join(s for s in sorties if s)
    fichiers = [Path(p.strip()).name for p in re.findall(r"PDF généré : (.+?\.pdf)", sortie)]
    prechauffer_apercus(fichiers)
    reduit = [int(x) for x in re.findall(r"Texte réduit à (\d+) %", sortie)]  # custom design: content squeezed
    alerte = re.search(r"ATTENTION : (.+)", sortie)       # overflow, or content cut off (custom design)
    lisible = re.search(r"LISIBILITE : (.+)", sortie)     # text on a background colour that is too close
    return {"ok": ok, "message": sortie.splitlines()[-1] if sortie else "", "designs": len(designs),
            "pages_ok": "ATTENTION" not in sortie, "ats": "_ATS.pdf" in sortie,
            "echelle": min(reduit, default=100), "alerte": alerte.group(1).strip() if alerte else "",
            "lisibilite": lisible.group(1).strip() if lisible else "",
            "fichiers": fichiers, "photo_provisoire": "PHOTO PROVISOIRE" in sortie}


def infos_diagnostic() -> dict:
    """App state for « Signaler un problème »: counters and error messages, never the
    content of her CV or documents."""
    e = etat()
    taches = [{"action": t.get("titre"), "agent": t.get("agent"), "etat": t.get("etat"), "tokens": t.get("tokens"),
               "erreur": t.get("reponse", "")[:300] if t.get("etat") == "erreur" else ""} for t in TACHES.values()]
    return {"version": e["version"], "python": sys.version.split()[0], "programme": str(APP), "donnees": str(RACINE),
            "claude_trouve": e["claude"], "claude_connecte": e["claude_connecte"], "moteur_pdf": e["pdflatex"],
            "cv_cree": e["cv_importe"], "cv_anglais": e["cv_anglais"], "nb_documents": len(e["infos"]),
            "nb_exemples_design": len(e["design"]), "nb_fichiers_cv": len(e["cv"]), "nb_versions": len(e["variantes"]),
            "agents_perso": len(e["agents_perso"]), "taches_de_la_session": taches[-10:]}


# --------------------------------------------------------------------------- HTTP server

DERNIER_SIGNE = time.time()
FERMETURE = 0.0       # when the window reported closing (0 = never)
DELAI_FERMETURE = 5   # grace seconds: a mere page reload sends a sign in the meantime


class Gestionnaire(BaseHTTPRequestHandler):
    def log_message(self, *_):  # silent
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
        if url.path.startswith("/vendor/"):  # bundled libraries and font: nothing to download at launch
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
        if url.path == "/api/consommation":
            return self._json(services.consommation())
        if url.path == "/api/reglages":
            return self._json(services.reglages())
        if url.path == "/api/nouveautes":  # CHANGELOG.md: next to the program (installed) or at the root (dev)
            f = next((p for p in (APP / "CHANGELOG.md", APP.parent / "CHANGELOG.md") if p.is_file()), None)
            texte = lire(f) if f else ""
            texte = re.sub(r"<!--.*?-->", "", texte, flags=re.S)          # notes for developers
            texte = re.sub(r"^# .*\n", "", texte, count=1).strip()        # the title: the screen has its own
            return self._json({"texte": texte, "version": services.version_locale()["version"]})
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
        if url.path.startswith("/apercu/"):  # image of a PDF's 1st page, for the preview in « Mes CV »
            image = apercu(Path(unquote(url.path[8:])).name)
            if image:
                return self._fichier(image, "image/png")
        if url.path.startswith("/exemple/"):  # thumbnail of a design example (Mes documents › Exemples de design)
            f = ZONES["design"] / Path(unquote(url.path[9:])).name
            types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
                     ".gif": "image/gif"}
            if f.is_file() and f.suffix.lower() in types:
                return self._fichier(f, types[f.suffix.lower()])
            image = apercu(f.name, ZONES["design"]) if f.is_file() else None
            if image:
                return self._fichier(image, "image/png")
        self._json({"erreur": "introuvable"}, 404)

    def do_POST(self):
        global FERMETURE
        url = urlparse(self.path)
        if url.path == "/api/fermeture":  # sent by the window when it is closed (X button)
            FERMETURE = time.time()
            return self._json({"ok": True})
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/api/deposer":  # raw body = the file; name in ?nom=
                zone = ZONES[q["zone"]]
                zone.mkdir(parents=True, exist_ok=True)
                nom = Path(q["nom"]).name
                if not nom or nom.startswith("."):
                    raise ValueError("nom de fichier invalide")
                exemple = lambda f: f.suffix.lower() in EXTENSIONS_IMAGE | {".pdf"}  # noqa: E731 - fonts don't count
                if (q["zone"] == "design" and exemple(Path(nom)) and not (zone / nom).exists()
                        and sum(exemple(f) for f in zone.iterdir()) >= MAX_DESIGNS):
                    raise ValueError(f"{MAX_DESIGNS} exemples au maximum : retirez-en un pour en ajouter un autre.")
                (zone / nom).write_bytes(self._corps())
                return self._json({"ok": True})

            if url.path == "/api/supprimer":
                if q["zone"] == "cv":  # a generated CV: only PDF or Word files from the CV/ folder
                    f = SORTIE / Path(q["nom"]).name
                    if f.suffix.lower() not in {".pdf", ".docx"}:
                        raise ValueError("seuls les PDF et les fichiers Word peuvent être supprimés ici")
                else:
                    f = ZONES[q["zone"]] / Path(q["nom"]).name
                if f.is_file():
                    f.unlink()
                if q["zone"] == "design" and (DESIGNS / nom_design(f.name)).is_dir():
                    supprimer_design(DESIGNS / nom_design(f.name))  # an example gone: its design and PDFs too
                if q["zone"] == "cv" and f.name.startswith("Lettre_") and LETTRES.is_dir():
                    # the letter itself too (otherwise its PDF would come back at the next layout)
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
                    texte = d.get("texte", "")
                    if t.get("rendu"):  # layout agent: the generation result, which she doesn't have to copy
                        texte = f"(Génération du PDF par l'application : {t['rendu']})\n\n{texte}"
                    tid = nouvelle_tache(texte, t["agent"], t["session"], t["titre"])
                    return self._json({"tache": tid})
                texte = d.get("texte", "")
                if action == "perso":  # an agent created by the user (Coulisses › Créer un agent)
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
                if action == "sur_mesure" and texte.strip():
                    invite += f" Exemple ou retouche qu'elle indique : {texte.strip()}"
                if offre:
                    invite += bloc("Texte de l'offre", texte)
                if action == "entretien" and d.get("precision"):
                    invite += bloc("Ce qu'elle précise", d["precision"])
                if action == "relance":  # only the application and the summary line of the version sent
                    cand = next((x for x in services.candidatures() if x["id"] == d.get("candidature")), None)
                    if not cand:
                        raise ValueError("Candidature introuvable.")
                    cv = tomllib.loads(lire(CV_TOML)) if CV_TOML.is_file() else {}
                    versions = cv.get("variantes", {})
                    v = versions.get(cand.get("version")) or next(iter(versions.values()), {})
                    invite += bloc("La candidature", "\n".join([
                        f"Entreprise : {cand['entreprise']}", f"Poste : {cand['poste'] or '(non précisé)'}",
                        f"Candidature envoyée le : {cand['date']}", f"Date du jour : {datetime.now():%Y-%m-%d}",
                        f"Son nom : {cv.get('identite', {}).get('nom') or '(inconnu)'}",
                        f"Titre de sa version : {v.get('titre', '')}", f"Son accroche : {v.get('accroche', '')}"]))
                # Stable content (Skills, CV) first, the day's request at the end: two tasks close together
                # find the start in the cache (read ~10 times cheaper).
                invite = preparer_contexte(action, nom_agent, offre) + bloc("Votre tâche", invite)
                return self._json({"tache": nouvelle_tache(invite, nom_agent, None, action)})

            if url.path == "/api/correspondance":  # job posting keywords in the CV: a script, 0 tokens
                d = json.loads(self._corps() or b"{}")
                module = _module(SCRIPTS["correspondance.py"])
                if not (module and CV_TOML.is_file()):
                    raise ValueError("Créez d'abord votre CV.")
                if not isinstance(d.get("texte"), str):
                    raise ValueError("Collez le texte de l'annonce.")
                cv = tomllib.loads(lire(CV_TOML))
                return self._json(module.analyser(cv, d["texte"], d.get("variante") or None))

            if url.path == "/api/reglages":
                return self._json(services.enregistrer_reglages(json.loads(self._corps() or b"{}")))

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

            if url.path == "/api/lettres/generer":  # « Refaire le PDF » (e.g. after a design change)
                avert = generer_lettres(toutes=True)
                return self._json({"ok": not avert, "message": avert.strip("\n> ")})

            if url.path == "/api/maj/installer":
                services.installer_maj()
                return self._json({"ok": True})

            if url.path == "/api/generer":
                return self._json(generer(q["variante"]))
            if url.path == "/api/exporter-word":
                return self._json(exporter_word(q["variante"]))
            if url.path == "/api/supprimer-version":  # the version itself (cv.toml), not just its PDFs
                return self._json(supprimer_version(q["variante"]))
            if url.path == "/api/ouvrir-cv":  # a file from CV/ in its app (Word, PDF reader)
                f = SORTIE / Path(q["nom"]).name
                if not (f.is_file() and f.suffix.lower() in {".pdf", ".docx"}):
                    raise ValueError("fichier introuvable")
                os.startfile(f)  # type: ignore[attr-defined]
                return self._json({"ok": True})

            if url.path == "/api/diagnostic":  # « Signaler un problème »: a zip without her documents or CV
                chemin = services.diagnostic(infos_diagnostic(), Path(q["dossier"]) if q.get("dossier") else None)
                if not q.get("dossier"):
                    subprocess.Popen(["explorer", f"/select,{chemin}"])  # the file, selected in Explorer
                return self._json({"fichier": str(chemin), "nom": chemin.name})
            if url.path == "/api/sauvegarde":
                d = json.loads(self._corps() or b"{}")
                chemin = services.sauvegarder(Path(d["chemin"]) if d.get("chemin") else None)
                return self._json({"fichier": str(chemin), "nom": chemin.name})
            if url.path == "/api/repartir-de-zero":  # full backup (Desktop), then the whole CV wiped
                d = json.loads(self._corps() or b"{}")
                return self._json(services.repartir_de_zero(Path(d["dossier"]) if d.get("dossier") else None))
            if url.path == "/api/restaurer-sauvegarde":
                d = json.loads(self._corps() or b"{}")
                n = services.restaurer_sauvegarde(Path(d["chemin"]))
                return self._json({"ok": True, "fichiers": n})

            if url.path == "/api/ouvrir":  # opens a folder in Explorer
                dossier = {"cv": SORTIE, "infos": ZONES["infos"], "design": ZONES["design"],
                           "agents": AGENTS, "skills": SKILLS}[q["quoi"]]
                dossier.mkdir(parents=True, exist_ok=True)
                os.startfile(dossier)  # type: ignore[attr-defined]  (Windows)
                return self._json({"ok": True})

            if url.path == "/api/ouvrir-fichier":  # coulisses: an agent or Skill file, in Notepad
                f = (RACINE / q["chemin"]).resolve()
                if not (f.is_file() and f.is_relative_to((RACINE / ".claude").resolve())):
                    raise ValueError("fichier non autorisé")
                subprocess.Popen(["notepad.exe", str(f)])
                return self._json({"ok": True})

            if url.path == "/api/connexion":  # Claude account login, without leaving the app
                connexion_demarrer()
                return self._json(connexion_etat())
            if url.path == "/api/connexion/code":
                connexion_code(json.loads(self._corps() or b"{}").get("code", ""))
                return self._json(connexion_etat())
            if url.path == "/api/connexion/annuler":
                connexion_annuler()
                return self._json(connexion_etat())

            if url.path == "/api/journal":  # tests: the page logs a step in the journal
                journal("page : " + q.get("e", ""))
                if q.get("e", "").startswith("ERREUR"):  # page errors: kept for the diagnostic
                    services.noter_erreur(q["e"][:500])
                return self._json({"ok": True})

            if url.path == "/api/quitter":
                journal("/api/quitter reçu")
                self._json({"ok": True})
                threading.Thread(target=arreter, daemon=True).start()  # the window (fenetre.py) closes on its own
                return
        except (KeyError, ValueError, RuntimeError) as e:
            return self._json({"erreur": str(e)}, 400)
        except OSError as e:  # network (update), locked file…
            return self._json({"erreur": f"Opération impossible : {e}"}, 400)
        except Exception as e:  # noqa: BLE001 - never drop the connection: the page shows a message
            journal(f"erreur {url.path} : {e!r}")
            services.noter_erreur(f"{url.path} : {e!r}")
            return self._json({"erreur": "Erreur inattendue. Réessayez ; si ça recommence, relancez CV Booster."}, 500)
        self._json({"erreur": "introuvable"}, 404)


class ServeurExclusif(ThreadingHTTPServer):
    """On Windows, SO_REUSEADDR (on by default in http.server) lets TWO servers listen on the same
    port: an old version could answer instead of the new one. We require an exclusive port."""
    allow_reuse_address = False
    # Connection queue: 5 by default. Beyond that, Windows refuses and the browser retries
    # 1 s later → the app looks frozen when clicking fast (measured: spikes at ~1000 ms).
    request_queue_size = 128
    daemon_threads = True

    def server_bind(self):
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


SERVEUR: ThreadingHTTPServer | None = None
FIN = threading.Event()  # set when the server stops


def journal(evenement: str) -> None:
    """Timestamped log of the window's steps, only in tests (CVB_JOURNAL=1)."""
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
    """Stops the server when the window is closed (signal + 5 s without news), or as a last resort
    after 3 min without any sign. Never while a Claude task is running."""
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
    """The folder was moved since last time → rewrite the shortcuts (folder, and Desktop if it
    exists) so they point to the right place. Compared with the root noted in config.json."""
    conf = config()
    if conf.get("installe"):  # installed version: shortcuts belong to the installer (Start menu…)
        return
    if RACINE != APP.parent:  # tests with another data folder: the dev shortcuts don't move
        return
    if conf.get("racine") == str(RACINE):
        return
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(APP / "creer_raccourcis.ps1"), "-MajBureau"],
                   capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    conf["racine"] = str(RACINE)
    (APP / "config.json").write_text(json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    """The server alone. The window is a separate program (fenetre.py), started by lancer.pyw.
    Run directly without --sans-navigateur (development): opens the UI in Edge."""
    global SERVEUR
    completer_path()
    for z in ZONES.values():
        z.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("CVB_PORT", PORT))  # other port: tests only
    try:
        SERVEUR = ServeurExclusif(("127.0.0.1", port), Gestionnaire)
    except OSError:  # already running: nothing to do (the window talks to the existing server)
        return
    threading.Thread(target=surveiller_inactivite, daemon=True).start()
    threading.Thread(target=reparer_raccourcis, daemon=True).start()
    threading.Thread(target=claude_connecte, daemon=True).start()  # login status ready for the page
    if "--sans-navigateur" not in sys.argv and not os.environ.get("CVB_SANS_FENETRE"):
        ouvrir_fenetre(f"http://127.0.0.1:{port}")
    SERVEUR.serve_forever()


if __name__ == "__main__":
    main()
