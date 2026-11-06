"""Tests automatiques de CV Booster, à lancer avant chaque publication (construire_installeur.py le fait).

Usage : python .dev/tester.py [--rapide]      (--rapide : sans la génération des PDF)

Tout se passe dans un dossier jetable, avec le CV d'exemple : jamais les vraies données. Aucun appel à
Claude (zéro token) : on teste ce qui est mécanique ; les agents, eux, se testent à la main.
"""

import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import traceback
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
APP, CLAUDE, DEV = RACINE / ".app", RACINE / ".claude", RACINE / ".dev"
SCRIPTS = CLAUDE / "skills" / "mise-en-page" / "scripts"
EXEMPLE = CLAUDE / "skills" / "format-cv" / "cv-exemple.toml"
OFFRE = DEV / "tests" / "offre-exemple.txt"
RAPIDE = "--rapide" in sys.argv


def port_libre() -> int:
    """Un port choisi par le système : jamais en conflit avec une autre appli ou une autre série de tests
    lancée en même temps (ex. un autre projet construit sur le même modèle)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = port_libre()

RESULTATS: list[tuple[bool, str, str]] = []


def test(nom):
    def deco(f):
        def lancer():
            try:
                f()
                RESULTATS.append((True, nom, ""))
            except Exception as e:  # noqa: BLE001
                RESULTATS.append((False, nom, f"{e}\n{traceback.format_exc(limit=2)}" if not isinstance(e, AssertionError) else str(e)))
        lancer.nom = nom
        TESTS.append(lancer)
        return f
    return deco


TESTS = []


def charger(chemin: Path, nom: str):
    sys.path.insert(0, str(chemin.parent))
    spec = importlib.util.spec_from_file_location(nom, chemin)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------------------- dossier de test
TMP = Path(tempfile.mkdtemp(prefix="cvbooster-tests-"))
DONNEES = TMP / "donnees"
for d in ("ressources/design", "CV", ".cv-booster"):
    (DONNEES / d).mkdir(parents=True)
shutil.copytree(CLAUDE / "agents", DONNEES / ".claude" / "agents")
shutil.copytree(CLAUDE / "skills", DONNEES / ".claude" / "skills", ignore=shutil.ignore_patterns("__pycache__"))
shutil.copy(EXEMPLE, DONNEES / ".cv-booster" / "cv.toml")
os.environ["CVB_DONNEES"] = str(DONNEES)
miktex = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64"
if not shutil.which("pdflatex") and miktex.is_dir():
    os.environ["PATH"] = f"{miktex}{os.pathsep}{os.environ['PATH']}"
PYTHON = sys.executable


# ---------------------------------------------------------------------------- 1. structure
def entete(f: Path) -> dict:
    haut = f.read_text(encoding="utf-8-sig").split("---")[1]
    return {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in haut.strip().splitlines() if ":" in l)}


@test("agents : en-têtes complets, Skills et annexes existantes")
def _():
    for f in sorted((CLAUDE / "agents").glob("*.md")):
        brut = f.read_text(encoding="utf-8-sig")
        # Un retour chariot égaré dans l'en-tête suffit pour que Claude Code ignore l'agent (« not found »)
        assert brut.startswith("---\n") or brut.startswith("---\r\n"), f"{f.name} : l'en-tête doit commencer par ---"
        haut = brut.replace("\r\n", "\n").split("---")[1].strip("\n").split("\n")
        assert all(re.fullmatch(r"[a-z_]+:( [^\r]*)?", l) for l in haut), f"{f.name} : en-tête mal formé : {haut}"
        m = entete(f)
        for cle in ("name", "description", "tools", "model"):
            assert m.get(cle), f"{f.name} : champ « {cle} » manquant"
        assert m["name"] == f.stem, f"{f.name} : name = {m['name']} (doit être {f.stem})"
        assert m.get("effort", "medium") in {"low", "medium", "high"}, f"{f.name} : effort « {m.get('effort')} » invalide"
        for s in filter(None, (x.strip() for x in m.get("skills", "").split(","))):
            assert (CLAUDE / "skills" / s / "SKILL.md").is_file(), f"{f.name} : Skill inconnue « {s} »"
        for a in filter(None, (x.strip() for x in m.get("annexes", "").split(","))):
            assert (CLAUDE / "skills" / a).is_file(), f"{f.name} : annexe introuvable « {a} »"


@test("serveur : chaque action pointe vers un agent existant")
def _():
    texte = (APP / "serveur.py").read_text(encoding="utf-8")
    bloc = texte.split("ACTIONS = {", 1)[1].split("\n}", 1)[0]
    for action, agent in re.findall(r'"(\w+)": \("([\w-]+)"', bloc):
        assert (CLAUDE / "agents" / f"{agent}.md").is_file(), f"action « {action} » : agent « {agent} » introuvable"


@test("CHANGELOG : la version à publier a sa section")
def _():
    version = re.search(r'CVB_VERSION", "([\d.]+)"', (DEV / "construire_installeur.py").read_text(encoding="utf-8")).group(1)
    assert re.search(rf"^## {re.escape(version)}\b", (RACINE / "CHANGELOG.md").read_text(encoding="utf-8"), re.M), \
        f"pas de section « ## {version} » dans CHANGELOG.md"


# ---------------------------------------------------------------------------- 2. style (règles anti « IA »)
EMOJIS = re.compile("[\u2705\u274c\u26a0\u2728\u2b50\U0001f300-\U0001faff]")


def fichiers_du_projet():
    exclus = ("/vendor/", "/lib/", "/deps/", "/dist/", "/staging/", "/__pycache__/", "/.git/",
              "/polices/")  # licences de polices (textes de tiers, en anglais)
    for f in RACINE.rglob("*"):
        p = "/" + f.relative_to(RACINE).as_posix()
        if f.is_file() and f.suffix.lower() in {".md", ".py", ".pyw", ".html", ".toml", ".txt", ".tex", ".ps1", ".iss"} \
                and not any(x in p + "/" for x in exclus) and not p.startswith(("/ressources/", "/CV/", "/.cv-booster/")) \
                and f.name != "cv-piege.toml":  # CV d'évaluation : défauts VOULUS (voir evaluer.py)
            yield f


@test("style : aucun tiret cadratin ni émoji dans les fichiers du projet")
def _():
    trouves = []
    for f in fichiers_du_projet():
        for n, ligne in enumerate(f.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
            if "\u2014" in ligne or EMOJIS.search(ligne):
                trouves.append(f"{f.relative_to(RACINE)}:{n}")
    assert not trouves, "à corriger : " + ", ".join(trouves[:15])


# Vouvoiement partout : pronoms et possessifs de « tu », et impératifs tutoyés dans les textes lus par la personne.
TUTOIEMENT = re.compile(r"(?<![\w|])(?:tu|toi|tes|te|ta|t['’](?=[a-zà-ÿ]))(?![\w|])|(?<![\w])ton(?![\w])(?!\s+(?:simple|à elle))(?<!le ton)(?<!un ton)(?<!du ton)(?<!\(ton)", re.I)
IMPERATIFS = re.compile(r"(?<![\w])(?:Colle|Clique|Choisis|Dépose|Relis|Ajoute|Vérifie|Patiente|Envoie|Indique|Écris|Réessaie|Reviens|"
                        r"Essaie|Remplis|Sélectionne|Glisse|Connecte|Garde|Regarde|Fais|Dis|Prends|Mets|Attends|Tape|Utilise|Retrouve|"
                        r"Double-clique|Donne|Passe|Lis|Crée|Décris)(?![\w-])(?! le serveur)")
LUS_PAR_LA_PERSONNE = {"index.html", "CHANGELOG.md", "guide.md", "cv-booster.iss"}
SANS_CONTROLE_TU = {"correspondance.py": "liste de mots vides", "lexique-ia.txt": "expressions régulières",
                    "tester.py": "définit les motifs"}


@test("vouvoiement : aucun tutoiement dans les textes, les consignes des agents et la doc")
def _():
    trouves = []
    for f in fichiers_du_projet():
        if f.name in SANS_CONTROLE_TU:
            continue
        for n, ligne in enumerate(f.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
            if "avant la 1.3" in ligne or "motif de contrôle" in ligne:  # compatibilité « cree_par: toi », motifs de détection
                continue
            m = TUTOIEMENT.search(ligne) or (f.name in LUS_PAR_LA_PERSONNE and IMPERATIFS.search(ligne))
            if m:
                trouves.append(f"{f.relative_to(RACINE)}:{n} « {m.group(0)} »")
    assert not trouves, "à vouvoyer : " + ", ".join(trouves[:15])


# ---------------------------------------------------------------------------- 3. fonctions sans IA
@test("correspondance : mots-clés d'une annonce, score cohérent")
def _():
    m = charger(CLAUDE / "skills" / "format-cv" / "scripts" / "correspondance.py", "correspondance")
    r = m.analyser(tomllib.loads(EXEMPLE.read_text(encoding="utf-8-sig")), OFFRE.read_text(encoding="utf-8"))
    assert 5 <= r["total"] <= 20 and 0 <= r["score"] <= 100, r
    assert any("scrum" in k or "jira" in k or "projet" in k for k in r["trouves"] + r["manquants"]), r


@test("mises à jour : agents d'origine synchronisés, modifications de la personne gardées")
def _():
    code = (APP / "lancer.pyw").read_text(encoding="utf-8").split("\nDONNEES = dossier_donnees()")[0]
    m = {"__file__": str(APP / "lancer.pyw")}
    exec(compile(code, "lancer.pyw", "exec"), m)
    v, dest = TMP / "synchro-v", TMP / "synchro-d"
    (v / "agents").mkdir(parents=True)
    (v / "agents" / "a.md").write_text("a1", encoding="utf-8"); (v / "agents" / "b.md").write_text("b1", encoding="utf-8")
    m["synchroniser_claude"](v, dest)
    (dest / "agents" / "b.md").write_text("b modifié", encoding="utf-8")
    (v / "agents" / "a.md").write_text("a2", encoding="utf-8"); (v / "agents" / "b.md").write_text("b2", encoding="utf-8")
    m["synchroniser_claude"](v, dest)
    assert (dest / "agents" / "a.md").read_text(encoding="utf-8") == "a2"
    assert (dest / "agents" / "b.md").read_text(encoding="utf-8") == "b modifié"


@test("bloc « modifications » : remplacé partout, ajout de version, CV jamais cassé")
def _():
    m = charger(CLAUDE / "skills" / "format-cv" / "scripts" / "appliquer.py", "appliquer")
    cv = TMP / "appliquer-cv.toml"
    shutil.copy(EXEMPLE, cv)
    original = cv.read_text(encoding="utf-8-sig")
    rep = ("Je corrige.\n```modifications\n[[remplacer]]\navant = '''Prénom Nom'''\napres = '''Camille Martin'''\n"
           "[[remplacer]]\navant = '''texte absent du CV'''\napres = '''x'''\n"
           "[ajouter]\ntexte = '''\n[variantes.test_offre]\ntitre = \"Titre test\"\naccroche = \"Accroche test.\"\n'''\n```")
    bloc, reste = m.extraire(rep)
    assert bloc and reste == "Je corrige."
    r = m.appliquer(cv, bloc)
    cvd = tomllib.loads(cv.read_text(encoding="utf-8"))
    assert r["appliquees"] == 1 and len(r["introuvables"]) == 1 and r["ajout"] and not r["erreur"], r
    assert cvd["identite"]["nom"] == "Camille Martin" and "test_offre" in cvd["variantes"]
    avant = cv.read_text(encoding="utf-8")  # un guillemet droit qui casserait le fichier : rien n'est écrit
    r = m.appliquer(cv, "[[remplacer]]\navant = '''Camille Martin'''\napres = '''Camille \"Cam\" Martin'''\n")
    assert r["erreur"] and cv.read_text(encoding="utf-8") == avant, r
    assert m.appliquer(cv, "pas du toml [[")["erreur"] and cv.read_text(encoding="utf-8") == avant
    assert original != avant


services = charger(APP / "services.py", "services")


@test("candidatures : nettoyage (vide ignorée, statut inconnu, lien dangereux)")
def _():
    r = services.enregistrer_candidatures([{"entreprise": "A", "statut": "??", "lien": "javascript:x"}, {"entreprise": ""}])
    assert len(r) == 1 and r[0]["statut"] == services.STATUTS[0] and r[0]["lien"] == "" and r[0]["id"]


@test("agents créés : écriture, doublon refusé, agents d'origine protégés")
def _():
    nom = services.creer_agent({"libelle": "Agent Test", "description": "Test", "consignes": "Répondez OK.", "skills": ["regles-ecriture", "x"]})
    texte = (services.AGENTS / f"{nom}.md").read_text(encoding="utf-8")
    assert "cree_par: vous" in texte and "skills: regles-ecriture" in texte and "x" not in texte.split("skills:")[1].split("\n")[0]
    assert services.agent_perso(nom) is True and services.agent_perso("relecteur") is False
    (services.AGENTS / "ancien-agent.md").write_text(texte.replace("cree_par: vous", "cree_par: toi"), encoding="utf-8")
    assert services.agent_perso("ancien-agent") is True, "agent créé avant la 1.3 (« cree_par: toi ») non reconnu"
    services.supprimer_agent("ancien-agent")
    for mauvais in (lambda: services.creer_agent({"libelle": "Agent Test", "description": "a", "consignes": "b"}),
                    lambda: services.supprimer_agent("relecteur")):
        try:
            mauvais()
            raise AssertionError("aurait dû être refusé")
        except ValueError:
            pass
    services.supprimer_agent(nom)


@test("historique : copie avant tâche, pas de doublon, retour en arrière")
def _():
    cv = services.CV_TOML
    services.archiver_cv("test 1"); services.archiver_cv("test 1 bis")
    assert len(services.historique()) == 1
    original = cv.read_text(encoding="utf-8")
    cv.write_text(original.replace("Prénom Nom", "Autre Nom"), encoding="utf-8")
    services.restaurer_cv(services.historique()[-1]["fichier"])
    assert cv.read_text(encoding="utf-8") == original


@test("sauvegarde : aller-retour complet, chemins hors dossier refusés")
def _():
    (DONNEES / "ressources" / "note.txt").write_text("ma note", encoding="utf-8")
    z = services.sauvegarder(TMP / "sauvegarde.zip")
    (DONNEES / "ressources" / "note.txt").unlink()
    assert services.restaurer_sauvegarde(z) > 3 and (DONNEES / "ressources" / "note.txt").read_text(encoding="utf-8") == "ma note"
    piege = TMP / "piege.zip"
    with zipfile.ZipFile(piege, "w") as zz:
        zz.writestr(services.SAUVEGARDE_MARQUE, "{}"); zz.writestr("ressources/../../evade.txt", "x")
    services.restaurer_sauvegarde(piege)
    assert not (TMP / "evade.txt").exists(), "un fichier est sorti du dossier des données"


@test("diagnostic : ni nom de session ni e-mail dans le fichier")
def _():
    services.noter_erreur(f"erreur dans {Path.home()}\\x, contact prenom.nom@exemple.fr")
    z = services.diagnostic({"test": True}, TMP)
    with zipfile.ZipFile(z) as zz:
        tout = "".join(zz.read(n).decode("utf-8") for n in zz.namelist())
    assert str(Path.home()) not in tout and "@exemple.fr" not in tout and "%USERPROFILE%" in tout


@test("consommation : enregistrement et totaux")
def _():
    services.noter_conso("relire", "relecteur", "sonnet", 12000, 20, False)
    c = services.consommation()
    assert c["aujourdhui"] >= 12000 and c["par_action"]["relire"]["moyenne"] == 12000


# ---------------------------------------------------------------------------- 4. génération des documents
def pdftexte(pdf: Path) -> str:
    return subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"], capture_output=True).stdout.decode("utf-8")


def pages(pdf: Path) -> int:
    sortie = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    return int(re.search(r"Pages:\s+(\d+)", sortie).group(1))


def generer(source: Path, sortie: Path) -> list[Path]:
    r = subprocess.run([PYTHON, "-I", str(SCRIPTS / "generer_cv.py"), "--source", str(source), "--variante", "principal",
                        "--sortie", str(sortie), "--build", str(sortie / "build")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    return sorted(sortie.glob("*.pdf"))


@test("CV français : 2 PDF (design + ATS), 1 page, texte lisible")
def _():
    if RAPIDE or not shutil.which("pdflatex"):
        return
    pdfs = generer(EXEMPLE, TMP / "fr")
    assert len(pdfs) == 2 and any(p.name.endswith("_ATS.pdf") for p in pdfs), pdfs
    for p in pdfs:
        assert pages(p) == 1, f"{p.name} : {pages(p)} pages"
        t = pdftexte(p)
        assert "EXPÉRIENCES PROFESSIONNELLES" in t.upper() and "ﬁ" not in t, f"{p.name} : texte inattendu"
        assert "\u2014" not in t, f"{p.name} : tiret cadratin ajouté par la mise en page"


@test("design sur mesure : gabarit rempli (listes, absent, échappement), erreur claire s'il est mal fermé")
def _():
    sys.path.insert(0, str(SCRIPTS))
    import generer_html
    ctx = {"nom": "A & B", "points": ["un", "deux"], "vide": [], "identite": {"email": "a@exemple.fr"},
           "experiences": [{"poste": "P", "points": ["x"]}]}
    texte, inconnus = generer_html.rendre("{{nom}}|{{#points}}<{{.}}>{{/points}}|{{^vide}}rien{{/vide}}|"
                                          "{{identite.email}}|{{#experiences}}{{poste}}:{{#points}}{{.}}{{/points}}{{/experiences}}|{{fote}}", ctx)
    assert texte == "A &amp; B|<un><deux>|rien|a@exemple.fr|P:x|" and inconnus == ["fote"], (texte, inconnus)
    for mauvais in ("{{#a}}x", "x{{/a}}", "{{#a}}{{/b}}"):
        try:
            generer_html.analyser(mauvais)
            raise AssertionError(f"gabarit mal fermé accepté : {mauvais}")
        except ValueError:
            pass


@test("design sur mesure : PDF A4 d'une page imprimé par Edge, contenu du CV, version ATS en LaTeX à côté")
def _():
    if RAPIDE or not shutil.which("pdflatex"):
        return
    d = TMP / "sur-mesure"
    (d / "gabarit").mkdir(parents=True)
    shutil.copy(DEV / "tests" / "gabarit-test.html", d / "gabarit" / "gabarit.html")
    (d / "design.toml").write_text("[page]\nsur_mesure = true\n", encoding="utf-8")
    cv = EXEMPLE.read_text(encoding="utf-8-sig")
    (d / "cv.toml").write_text(cv, encoding="utf-8")
    pdfs = generer(d / "cv.toml", d / "sortie")
    design = next(p for p in pdfs if not p.name.endswith("_ATS.pdf"))
    ats = next(p for p in pdfs if p.name.endswith("_ATS.pdf"))
    infos = lambda p: subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True).stdout  # noqa: E731
    assert "Skia" in infos(design) and "pdfTeX" in infos(ats), "design par Edge, ATS par LaTeX attendus"
    assert pages(design) == 1 and "A4" in infos(design), infos(design)
    t = pdftexte(design)
    assert "Prénom" in t and "Expériences professionnelles" in t and "Intitulé" in t, t[:300]
    # CV anglais : même gabarit, titres de rubriques en anglais (lib.*), fichier en _EN
    (d / "cv-en.toml").write_text('langue = "en"\n' + cv, encoding="utf-8")
    en = generer(d / "cv-en.toml", d / "sortie-en")
    design_en = next(p for p in en if not p.name.endswith("_ATS.pdf"))
    t_en = pdftexte(design_en)
    assert "_EN" in design_en.name and "Skia" in infos(design_en), design_en.name
    assert "Professional experience" in t_en and "Education" in t_en and "Expériences" not in t_en, t_en[:300]
    # Lisibilité : aucun signalement sur le gabarit normal ; un titre rose clair posé sur la forme rose → signalé
    def sortie_generation(dossier: str) -> str:
        r = subprocess.run([PYTHON, "-I", str(SCRIPTS / "generer_cv.py"), "--source", str(d / "cv.toml"), "--variante",
                            "principal", "--sortie", str(d / dossier), "--build", str(d / dossier / "build")],
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stdout[-400:] + r.stderr[-400:]
        return r.stdout
    assert "LISIBILITE" not in sortie_generation("sortie-lisible"), "fausse alerte de lisibilité sur le gabarit de test"
    g1 = (d / "gabarit" / "gabarit.html").read_text(encoding="utf-8")
    (d / "gabarit" / "gabarit.html").write_text(g1.replace("</body>", '<div style="position:absolute; left:178mm; top:3mm; '
                                                'z-index:2; color:#e2b0c2; font-size:11pt">Titre fantôme</div></body>', 1), encoding="utf-8")
    sortie = sortie_generation("sortie-illisible")
    assert "LISIBILITE" in sortie and "Titre fantôme" in sortie, "texte illisible sur un décor non détecté : " + sortie[-300:]
    (d / "gabarit" / "gabarit.html").write_text(g1, encoding="utf-8")
    # Gabarit à hauteur fixe qui cache la fin : une page… mais du texte manquant → signalé, jamais livré en silence
    g0 = (d / "gabarit" / "gabarit.html").read_text(encoding="utf-8")
    (d / "gabarit" / "gabarit.html").write_text(g0.replace("min-height: 297mm;", "height: 297mm; overflow: hidden;", 1), encoding="utf-8")
    trop_long = re.sub(r"(\[\[experiences\]\].*?)(?=\n\[\[competences)", lambda m: (m.group(1) + "\n") * 30, cv, count=1, flags=re.S)
    (d / "cv.toml").write_text(trop_long, encoding="utf-8")
    r = subprocess.run([PYTHON, "-I", str(SCRIPTS / "generer_cv.py"), "--source", str(d / "cv.toml"), "--variante", "principal",
                        "--sortie", str(d / "sortie-coupe"), "--build", str(d / "sortie-coupe" / "build")],
                       capture_output=True, text=True, encoding="utf-8")
    assert "contenu coupé" in r.stdout, "texte caché par le gabarit non détecté : " + r.stdout[-400:]
    (d / "gabarit" / "gabarit.html").write_text(g0, encoding="utf-8")
    (d / "cv.toml").write_text(cv, encoding="utf-8")
    # Cambria demandée : remplacée (ses accents se copient mal depuis un PDF d'Edge : « Expé riences »)
    g = d / "gabarit" / "gabarit.html"
    g.write_text(g.read_text(encoding="utf-8").replace("Candara, Calibri, sans-serif", "Cambria, serif"), encoding="utf-8")
    t = pdftexte(next(p for p in generer(d / "cv.toml", d / "sortie-cambria") if not p.name.endswith("_ATS.pdf")))
    assert "Expériences professionnelles" in t and "Intitulé" in t, "accents mal copiés : " + t[:200]
    # Un CV trop long : le texte rétrécit (--echelle) jusqu'à tenir sur une page
    long = re.sub(r"(\[\[experiences\]\].*?)(?=\n\[\[competences)", lambda m: (m.group(1) + "\n") * 8, cv, count=1, flags=re.S)
    (d / "cv.toml").write_text(long, encoding="utf-8")
    pdfs = generer(d / "cv.toml", d / "sortie-long")
    assert pages(next(p for p in pdfs if not p.name.endswith("_ATS.pdf"))) == 1, "le design sur mesure déborde"


@test("design sur mesure : polices libres embarquées (licence OFL de chacune) et intégrées au PDF ; 2 pages si choisi")
def _():
    polices = CLAUDE / "skills" / "mise-en-page" / "polices"
    ttf = sorted(polices.glob("*.ttf"))
    assert len(ttf) >= 6, ttf
    for f in ttf:  # chaque famille a sa licence (OFL : obligatoire pour les redistribuer)
        famille = f.stem.split("-")[0]
        assert (polices / f"OFL-{famille}.txt").is_file(), f"licence manquante pour {f.name}"
        assert famille in (CLAUDE / "skills" / "mise-en-page" / "gabarit-html.md").read_text(encoding="utf-8"), \
            f"{f.name} absente de l'annexe : l'agent ne la connaît pas"
    if RAPIDE or not shutil.which("pdflatex"):
        return
    d = TMP / "sur-mesure-polices"
    (d / "gabarit").mkdir(parents=True)
    g = (DEV / "tests" / "gabarit-test.html").read_text(encoding="utf-8")
    g = g.replace("<style>", '<style>@font-face { font-family: "Lora"; src: url("Lora.ttf"); font-weight: 400 700; }', 1)
    g = g.replace("Candara, Calibri, sans-serif", '"Lora", serif')
    (d / "gabarit" / "gabarit.html").write_text(g, encoding="utf-8")
    (d / "design.toml").write_text("[page]\nsur_mesure = true\npages_sur_mesure = 2\n", encoding="utf-8")
    cv = EXEMPLE.read_text(encoding="utf-8-sig")  # assez long pour 2 pages, trop pour 1 même réduit
    long = re.sub(r"(\[\[experiences\]\].*?)(?=\n\[\[competences)", lambda m: (m.group(1) + "\n") * 14, cv, count=1, flags=re.S)
    (d / "cv.toml").write_text(long, encoding="utf-8")
    design = next(p for p in generer(d / "cv.toml", d / "sortie") if not p.name.endswith("_ATS.pdf"))
    assert pages(design) == 2, f"{pages(design)} pages au lieu de 2"
    polices_pdf = subprocess.run(["pdffonts", str(design)], capture_output=True, text=True).stdout
    assert "Lora" in polices_pdf, "police Lora non intégrée au PDF : " + polices_pdf[-300:]


@test("CV anglais : titres en anglais, fichiers en _EN")
def _():
    if RAPIDE or not shutil.which("pdflatex"):
        return
    en = TMP / "cv-en.toml"
    en.write_text('langue = "en"\n' + EXEMPLE.read_text(encoding="utf-8-sig"), encoding="utf-8")
    pdfs = generer(en, TMP / "en")
    assert all("_EN" in p.name for p in pdfs) and len(pdfs) == 2, pdfs
    t = pdftexte(next(p for p in pdfs if p.name.endswith("_ATS.pdf"))).upper()
    assert "PROFESSIONAL EXPERIENCE" in t and "SKILLS" in t and "COMPÉTENCES" not in t


@test("lettre de motivation : PDF d'une page")
def _():
    if RAPIDE or not shutil.which("pdflatex"):
        return
    (DONNEES / ".cv-booster" / "lettres").mkdir(exist_ok=True)
    shutil.copy(CLAUDE / "skills" / "lettre-motivation" / "lettre-exemple.toml", DONNEES / ".cv-booster" / "lettres" / "exemple.toml")
    r = subprocess.run([PYTHON, "-I", str(SCRIPTS / "generer_lettre.py"), "--source", str(DONNEES / ".cv-booster" / "cv.toml"),
                        "--sortie", str(TMP / "lettres")], capture_output=True, text=True, encoding="utf-8")
    pdfs = list((TMP / "lettres").glob("Lettre_*.pdf"))
    assert pdfs and pages(pdfs[0]) == 1, r.stdout[-600:]
    assert "\u2014" not in pdftexte(pdfs[0]), "tiret cadratin dans la lettre"


@test("lettre assortie au design sur mesure : même moteur que le CV, une page ; sans gabarit de lettre, LaTeX")
def _():
    if RAPIDE or not shutil.which("pdflatex"):
        return
    d = TMP / "lettre-sur-mesure"
    (d / "gabarit").mkdir(parents=True)
    (d / "lettres").mkdir()
    shutil.copy(EXEMPLE, d / "cv.toml")
    shutil.copy(DEV / "tests" / "gabarit-test.html", d / "gabarit" / "gabarit.html")
    shutil.copy(DEV / "tests" / "lettre-test.html", d / "gabarit" / "lettre.html")
    shutil.copy(CLAUDE / "skills" / "lettre-motivation" / "lettre-exemple.toml", d / "lettres" / "exemple.toml")
    (d / "design.toml").write_text("[page]\nsur_mesure = true\n", encoding="utf-8")

    def lettre(sortie: str) -> Path:
        r = subprocess.run([PYTHON, "-I", str(SCRIPTS / "generer_lettre.py"), "--source", str(d / "cv.toml"),
                            "--sortie", str(d / sortie), "--toutes"], capture_output=True, text=True, encoding="utf-8")
        pdfs = list((d / sortie).glob("Lettre_*.pdf"))
        assert pdfs, r.stdout[-600:] + r.stderr[-600:]
        return pdfs[0]
    producteur = lambda p: subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True).stdout  # noqa: E731
    assortie = lettre("assortie")
    t = " ".join(pdftexte(assortie).split())
    assert "Skia" in producteur(assortie) and pages(assortie) == 1, producteur(assortie)
    assert "Prénom Nom" in t and "Accroche : le poste" in t and "agréer" in t, t[:300]
    (d / "gabarit" / "lettre.html").unlink()  # design sur mesure créé avant la lettre assortie : lettre classique
    assert "pdfTeX" in producteur(lettre("classique")), "sans lettre.html, la lettre doit rester en LaTeX"


@test("guide PDF : ni tiret cadratin ni ancienne version")
def _():
    guide = DEV / "guide" / "Guide CV Booster.pdf"
    if RAPIDE or not shutil.which("pdftotext") or not guide.is_file():
        return
    assert guide.stat().st_mtime >= (DEV / "guide" / "guide.md").stat().st_mtime, "guide.md modifié : refaire le PDF"
    assert "\u2014" not in pdftexte(guide), "tiret cadratin dans le guide (babel : puces)"


@test("export Word : .docx valide, avec le contenu du CV")
def _():
    r = subprocess.run([PYTHON, "-I", str(SCRIPTS / "generer_docx.py"), "--source", str(EXEMPLE), "--variante", "principal",
                        "--sortie", str(TMP / "word")], capture_output=True, text=True, encoding="utf-8")
    docx = list((TMP / "word").glob("*.docx"))
    assert docx, r.stdout + r.stderr
    import xml.dom.minidom
    with zipfile.ZipFile(docx[0]) as z:
        for n in z.namelist():
            xml.dom.minidom.parseString(z.read(n))
        assert "Prénom Nom" in z.read("word/document.xml").decode("utf-8")


# ---------------------------------------------------------------------------- 5. serveur
def appel(chemin: str, donnees=None, methode=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{chemin}", method=methode or ("POST" if donnees is not None else "GET"),
                                 data=None if donnees is None else json.dumps(donnees).encode("utf-8"))
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


@test("serveur : démarrage et routes principales")
def _():
    env = dict(os.environ, CVB_PORT=str(PORT), CVB_SANS_FENETRE="1", CVB_DONNEES=str(DONNEES))
    p = subprocess.Popen([PYTHON, str(APP / "lancer.pyw")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        for _ in range(100):
            try:
                e = appel("/api/etat")
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise AssertionError("le serveur ne répond pas : " + p.stderr.read(2000).decode("utf-8", "replace"))
        for cle in ("variantes", "cles", "anglais", "agents_perso", "version", "claude_connecte"):
            assert cle in e, f"/api/etat : « {cle} » manquant"
        assert appel("/api/nouveautes")["texte"].startswith("## ")
        assert appel("/api/correspondance", {"texte": OFFRE.read_text(encoding="utf-8")})["total"] > 0
        assert len(appel("/api/candidatures", [{"entreprise": "Test"}], "POST")["liste"]) == 1
        assert appel("/api/exporter-word?variante=principal", {})["fichier"].endswith(".docx")
        assert appel(f"/api/diagnostic?dossier={urllib.request.quote(str(TMP))}", {})["nom"].endswith(".zip")
        assert appel("/api/sauvegarde", {"chemin": str(TMP / "s2.zip")})["nom"] == "s2.zip"
        assert "par_action" in appel("/api/consommation")
        perso = services.creer_agent({"libelle": "Agent Coulisses", "description": "Test", "consignes": "Répondez OK."})
        try:  # Coulisses doit se charger avec un agent créé par la personne
            assert any(a.get("perso") for a in appel("/api/coulisses")["agents"]), "agent créé absent de Coulisses"
        finally:
            services.supprimer_agent(perso)
        assert appel("/api/reglages")["puissance"] == "moyen"
        assert appel("/api/reglages", {"puissance": "faible"})["puissance"] == "faible"
        try:
            appel("/api/reglages", {"puissance": "turbo"})
            raise AssertionError("puissance inconnue acceptée")
        except urllib.error.HTTPError:
            pass
        appel("/api/reglages", {"puissance": "moyen"})
        # Supprimer une version : la version elle-même (cv.toml) et sa traduction anglaise, CV mis de côté avant ;
        # la dernière version restante est refusée.
        cvt, cven = DONNEES / ".cv-booster" / "cv.toml", DONNEES / ".cv-booster" / "cv-en.toml"
        avant = cvt.read_text(encoding="utf-8")
        essai = '\n[variantes.essai]\ntitre = "Version essai"\naccroche = "Accroche de la version essai."\n'
        cvt.write_text(avant + essai, encoding="utf-8")
        cven.write_text('langue = "en"\n' + avant + essai, encoding="utf-8")
        nb_hist = len(list((DONNEES / ".cv-booster" / "historique").glob("*"))) if (DONNEES / ".cv-booster" / "historique").is_dir() else 0
        r = appel("/api/supprimer-version?variante=essai", {})
        assert r["ok"] and r["anglais"], r
        for f in (cvt, cven):
            v = tomllib.loads(f.read_text(encoding="utf-8"))["variantes"]
            assert "essai" not in v and "principal" in v, f"{f.name} : {list(v)}"
        assert len(list((DONNEES / ".cv-booster" / "historique").glob("*"))) > nb_hist, "CV non mis de côté avant suppression"
        try:
            appel("/api/supprimer-version?variante=principal", {})
            raise AssertionError("la dernière version a pu être supprimée")
        except urllib.error.HTTPError:
            pass
        cvt.write_text(avant, encoding="utf-8")
        cven.unlink()
        if not RAPIDE and shutil.which("pdflatex"):
            assert appel("/api/generer?variante=principal", {})["ok"]
    finally:
        try:
            appel("/api/quitter", {})
        except OSError:
            pass
        p.wait(10)


FAUX_CLAUDE = r'''
import json, sys
journal = sys.argv[1]
args = sys.argv[2:]
open(journal, "a", encoding="utf-8").write(" ".join(a for a in args if a.startswith("--")) + "\n")
if "--effort" in args:  # une future version de Claude Code qui ne connaîtrait plus cette option
    sys.stderr.write("error: unknown option '--effort'\n")
    sys.exit(1)
if "--agent" in args:  # une tâche : la demande arrive par l'entrée standard
    sys.stdin.read()
print(json.dumps({"type": "result", "result": "Réponse sans les options d'économie.", "session_id": "s1",
                  "num_turns": 1, "usage": {"input_tokens": 10, "output_tokens": 5}, "total_cost_usd": 0}))
'''


@test("filet : option refusée par Claude Code → tâche relancée sans les options d'économie")
def _():
    global PORT
    journal = TMP / "faux-claude.log"
    (TMP / "faux_claude.py").write_text(FAUX_CLAUDE, encoding="utf-8")
    (TMP / "claude.cmd").write_text(f'@"{PYTHON}" "{TMP / "faux_claude.py"}" "{journal}" %*\n', encoding="utf-8")
    port_filet = port_libre()
    env = dict(os.environ, CVB_PORT=str(port_filet), CVB_SANS_FENETRE="1", CVB_DONNEES=str(DONNEES),
               CLAUDE_BIN=str(TMP / "claude.cmd"))
    p = subprocess.Popen([PYTHON, str(APP / "lancer.pyw")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    port_normal, PORT = PORT, port_filet
    try:
        for _ in range(100):
            try:
                appel("/api/etat"); break
            except OSError:
                time.sleep(0.2)
        for n in (1, 2):
            t = appel("/api/action", {"action": "relire"})["tache"]
            for _ in range(100):
                r = appel(f"/api/tache/{t}")
                if r["etat"] != "en_cours":
                    break
                time.sleep(0.2)
            assert r["etat"] == "fini" and "sans les options" in r["reponse"], f"tâche {n} : {r['etat']} {r['reponse'][:200]}"
        lignes = [l for l in journal.read_text(encoding="utf-8").splitlines() if "--agent" in l]  # pas « auth status »
        # 1re tâche : refus puis relance sans options ; 2e tâche : directement sans options
        assert len(lignes) == 3 and "--effort" in lignes[0] and "--effort" not in lignes[1] + lignes[2], lignes
        assert "option d'économie" in (DONNEES / ".cv-booster" / "erreurs.log").read_text(encoding="utf-8")
    finally:
        try:
            appel("/api/quitter", {})
        except OSError:
            pass
        PORT = port_normal
        p.wait(10)


# ---------------------------------------------------------------------------- lancement
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    debut = time.time()
    for t in TESTS:
        t()
        ok, nom, detail = RESULTATS[-1]
        print(f"{'OK    ' if ok else 'ÉCHEC '} {nom}" + ("" if ok else f"\n       {detail.strip()[:600]}"))
    shutil.rmtree(TMP, ignore_errors=True)
    echecs = sum(1 for ok, *_ in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} tests réussis en {time.time() - debut:.0f} s"
          + ("" if not RAPIDE else " (sans génération des PDF)"))
    sys.exit(1 if echecs else 0)
