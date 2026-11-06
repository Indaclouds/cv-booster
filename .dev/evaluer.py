"""Évaluation de la QUALITÉ des agents, à lancer à la main avant/après une modification de leurs consignes.

Usage : python .dev/evaluer.py [relire] [reformuler] [offre]     (par défaut : les trois)

Utilise de VRAIS appels à Claude (≈ 0,3 à 0,5 $ d'équivalent API pour les trois) : ce n'est pas un test
automatique. Tout se passe dans un dossier jetable avec un CV fictif piégé (.dev/tests/cv-piege.toml) :
  - relire     : combien des défauts connus sont signalés, puis corrigés après « Appliquez tout » ;
  - reformuler : aucune tournure « IA » dans les propositions, pas de rallongement ;
  - offre      : la compétence absente (SEO) est signalée et jamais ajoutée ; la correspondance progresse.
Mesures pour chacun : délai avant le premier mot affiché, durée, tokens, coût équivalent API.
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
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
TESTS = RACINE / ".dev" / "tests"
PORT = 0  # choisi au lancement (port_libre) : pas de conflit avec une autre appli

# Défauts du CV piège : (nom, motif à trouver dans la réponse de la relecture, motif qui doit DISPARAÎTRE du
# CV après « Appliquez tout » ou None si c'est une question à trancher). Motifs sensibles à la casse.
DEFAUTS = [
    ("faute « Dévellopement »", r"(?i)dévellopement", r"Dévellopement"),
    ("montant « 15000€ » sans espace", r"15000|15 000", r"15000€"),
    ("tiret cadratin", "\u2014|[Cc]adratin|tiret long", "\u2014"),
    ("casse « google analytics »", r"google analytics", r"google analytics"),
    ("casse « jira »", r"\bjira\b", r"dans jira"),
    ("« Ecole » sans accent", r"\bEcole\b", r"\bEcole\b"),
    ("accord « équipes technique »", r"équipes technique(?!s)", r"équipes technique(?!s)"),
    ("format de dates « 2017-2021 »", r"2017-2021|2015-2017", r"\d{4}-\d{4}"),
    ("apostrophes mélangées", r"(?i)apostrophe", None),
    ("« 5 ans » au lieu de 8", r"(?i)5 ans|8 ans|huit ans", None),
    ("tournure IA « forte de »", r"(?i)forte d", None),
    ("tournure IA « solide expérience »", r"(?i)solide", None),
]


def charger(chemin: Path, nom: str):
    sys.path.insert(0, str(chemin.parent))
    spec = importlib.util.spec_from_file_location(nom, chemin)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def preparer() -> Path:
    d = Path(tempfile.mkdtemp(prefix="cvbooster-eval-")) / "CV Booster"
    for sous in ("ressources/design", "CV", ".cv-booster"):
        (d / sous).mkdir(parents=True)
    for sous in ("agents", "skills"):
        shutil.copytree(RACINE / ".claude" / sous, d / ".claude" / sous, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(TESTS / "cv-piege.toml", d / ".cv-booster" / "cv.toml")
    return d


class Appli:
    def __init__(self, donnees: Path):
        global PORT
        with socket.socket() as s:  # un port libre, choisi par le système
            s.bind(("127.0.0.1", 0))
            PORT = s.getsockname()[1]
        env = dict(os.environ, CVB_DONNEES=str(donnees), CVB_PORT=str(PORT), CVB_SANS_FENETRE="1")
        self.p = subprocess.Popen([sys.executable, str(RACINE / ".app" / "lancer.pyw")], env=env,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(100):
            try:
                self.api("/api/etat")
                return
            except OSError:
                time.sleep(0.2)

    def api(self, chemin, donnees=None):
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}{chemin}", method="GET" if donnees is None else "POST",
                                     data=None if donnees is None else json.dumps(donnees).encode("utf-8"))
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))

    def tache(self, corps) -> tuple[str, dict, float, float]:
        t = self.api("/api/action", corps)["tache"]
        t0, premier = time.time(), None
        while (r := self.api(f"/api/tache/{t}"))["etat"] == "en_cours":
            if premier is None and r.get("partiel"):
                premier = time.time() - t0
            time.sleep(0.3)
        return t, r, premier or (time.time() - t0), time.time() - t0

    def fermer(self):
        try:
            self.api("/api/quitter", {})
        except OSError:
            pass
        self.p.wait(10)


def ligne_mesure(nom, r, premier, total):
    print(f"   {nom:<12} 1er mot {premier:4.0f} s · total {total:3.0f} s · {r.get('tokens', 0):>6} tokens · "
          f"écrits {r.get('ecrits', 0):>5} · {r.get('cout', 0):.3f} $")
    texte = r.get("reponse") or ""
    tu = re.findall(r"(?i)(?<![\w-])(?:tu|toi|ton|ta|tes|te)(?![\w'’-])|(?<![\w])t['’](?=[a-zà-ÿ])|-toi\b", texte)  # motif de contrôle
    vous = len(re.findall(r"(?i)\b(?:vous|votre|vos)\b", texte))
    print(f"   {'':<12} vouvoiement : {vous} « vous/votre/vos » · tutoiement : {len(tu)}{' ' + str(tu) if tu else ''}")  # motif de contrôle


def apres_colonne(reponse: str, index: int) -> list[str]:
    """Textes d'une colonne des tableaux Markdown de la réponse (lignes de données seulement)."""
    textes = []
    for l in reponse.splitlines():
        cols = [c.strip() for c in l.strip().strip("|").split("|")]
        if l.strip().startswith("|") and len(cols) > index and not re.fullmatch(r"[-: ]*", cols[index]) and cols[0] not in {"#", "Où"}:
            textes.append(cols[index])
    return textes


def eval_relire(appli, cv: Path):
    print("\n== Relecture")
    t, r, p, d = appli.tache({"action": "relire"})
    ligne_mesure("proposition", r, p, d)
    trouves = [n for n, motif, _ in DEFAUTS if re.search(motif, r["reponse"])]
    print(f"   défauts signalés : {len(trouves)}/{len(DEFAUTS)}" +
          (f"  · manqués : {', '.join(n for n, *_ in DEFAUTS if n not in trouves)}" if len(trouves) < len(DEFAUTS) else ""))
    _, r2, p2, d2 = appli.tache({"action": "repondre", "tache": t, "texte": "Appliquez tout."})
    ligne_mesure("application", r2, p2, d2)
    texte = cv.read_text(encoding="utf-8")
    corriges = [n for n, _, reste in DEFAUTS if reste and not re.search(reste, texte)]
    a_corriger = [n for n, _, reste in DEFAUTS if reste]
    print(f"   défauts corrigés dans le CV : {len(corriges)}/{len(a_corriger)}" +
          (f"  · restants : {', '.join(n for n in a_corriger if n not in corriges)}" if len(corriges) < len(a_corriger) else ""))
    return {"signales": len(trouves), "corriges": len(corriges), "cout": r.get("cout", 0) + r2.get("cout", 0)}


def eval_reformuler(appli, cv: Path):
    print("\n== Reformulation (accroche)")
    lexique = [re.compile(l.strip(), re.I) for l in (RACINE / ".claude/skills/regles-ecriture/lexique-ia.txt")
               .read_text(encoding="utf-8-sig").splitlines() if l.strip() and not l.startswith("#")]
    t, r, p, d = appli.tache({"action": "reformuler", "texte": "L'accroche"})
    ligne_mesure("proposition", r, p, d)
    avant, apres = apres_colonne(r["reponse"], 1), apres_colonne(r["reponse"], 2)
    tics = [(x, rx.pattern) for x in apres for rx in lexique if rx.search(x)]
    plus_long = sum(1 for a, b in zip(avant, apres) if len(b) > len(a) * 1.15)
    cadratins = sum("\u2014" in x for x in apres)
    print(f"   propositions : {len(apres)} · tournures IA : {len(tics)} · rallongées : {plus_long} · tirets cadratins : {cadratins}")
    for x, motif in tics[:3]:
        print(f"      « {x[:90]} » ({motif})")
    return {"propositions": len(apres), "tics": len(tics) + cadratins, "cout": r.get("cout", 0)}


def eval_offre(appli, cv: Path):
    print("\n== Adaptation à une offre")
    corr = charger(RACINE / ".claude/skills/format-cv/scripts/correspondance.py", "correspondance")
    offre = (TESTS / "offre-exemple.txt").read_text(encoding="utf-8")
    t, r, p, d = appli.tache({"action": "offre", "texte": offre})
    ligne_mesure("proposition", r, p, d)
    signale = bool(re.search(r"(?i)\bSEO\b", r["reponse"]))
    _, r2, p2, d2 = appli.tache({"action": "repondre", "tache": t, "texte": "Oui, créez la version. Je n'ai jamais fait de SEO."})
    ligne_mesure("application", r2, p2, d2)
    c = tomllib.loads(cv.read_text(encoding="utf-8"))
    nouvelles = [k for k in c["variantes"] if k != "principal"]
    if not nouvelles:
        print("   AUCUNE version créée")
        return {"version": False, "cout": r.get("cout", 0) + r2.get("cout", 0)}
    k = nouvelles[-1]
    invente = bool(re.search(r"(?i)\bSEO\b", json.dumps(c["variantes"][k], ensure_ascii=False)))
    avant, apres = corr.analyser(c, offre, "principal")["score"], corr.analyser(c, offre, k)["score"]
    print(f"   SEO signalé comme absent : {'oui' if signale else 'NON'} · SEO inventé dans la version : {'OUI' if invente else 'non'}"
          f" · correspondance {avant} % → {apres} %")
    return {"version": True, "signale": signale, "invente": invente, "gain": apres - avant,
            "cout": r.get("cout", 0) + r2.get("cout", 0)}


def eval_importer(appli, cv: Path):
    print("\n== Création du CV (importeur) à partir de notes en vrac")
    cv.unlink()  # on part de zéro : seulement les notes dans ressources/
    shutil.copy(TESTS / "notes-piege.txt", cv.parent.parent / "ressources" / "notes.txt")
    t, r, p, d = appli.tache({"action": "importer"})
    ligne_mesure("import", r, p, d)
    if not cv.is_file():
        print("   AUCUN CV créé :", r["reponse"][:200])
        return {"cree": False}
    texte = cv.read_text(encoding="utf-8")
    try:
        c = tomllib.loads(texte)
    except tomllib.TOMLDecodeError as e:
        print("   CV ILLISIBLE :", e)
        return {"cree": True, "lisible": False}
    controles = {
        "ligne barrée écartée (stage Dupain)": "Dupain" not in texte,
        "chiffres repris (15 000, 40 000, 6, 12 mois)": all(x in texte.replace(" ", " ") for x in ("15 000", "40 000", "6 personnes", "12 mois")),
        "2 expériences": len(c.get("experiences", [])) == 2,
        "nom et e-mail": c.get("identite", {}).get("nom") == "Camille Martin" and "exemple.fr" in texte,
        "doute sur 2016/2017 signalé": bool(re.search(r"2016", r["reponse"])),
        "au moins une version": bool(c.get("variantes")),
    }
    for nom, ok in controles.items():
        print(f"   {'ok ' if ok else 'NON'}  {nom}")
    for l in texte.splitlines():
        if "Dupain" in l:
            print(f"        ligne concernée : {l.strip()[:120]}")
    gen = subprocess.run([sys.executable, "-I", str(cv.parent.parent / ".claude/skills/mise-en-page/scripts/generer_cv.py"),
                          "--source", str(cv), "--variante", next(iter(c["variantes"])), "--sortie", str(cv.parent / "pdf")],
                         capture_output=True, text=True, encoding="utf-8")
    print(f"   PDF : {'ok' if gen.returncode == 0 else 'ÉCHEC'}" + (" (déborde)" if "ATTENTION" in gen.stdout else ""))
    return {"cree": True, "controles": sum(controles.values()), "sur": len(controles), "pdf": gen.returncode == 0,
            "cout": r.get("cout", 0)}


def eval_sur_mesure(appli: Appli, cv: Path) -> dict:
    """Design sur mesure (maquettiste). L'exemple est NOTRE gabarit de test (design original, .dev/tests),
    rendu avec le CV d'exemple : aucun design de tiers dans le dépôt. Contrôles : tout le contenu du CV présent,
    aucun texte de l'exemple recopié dans le gabarit, une page imprimée par Edge."""
    print("\n== Design sur mesure (maquettiste)")
    d = cv.parent.parent
    sys.path.insert(0, str(RACINE / ".claude" / "skills" / "mise-en-page" / "scripts"))
    import generer_html
    ex = d / "exemple-rendu"
    (ex / ".cv-booster" / "gabarit").mkdir(parents=True)
    shutil.copy(TESTS / "gabarit-test.html", ex / ".cv-booster" / "gabarit" / "gabarit.html")
    src = ex / ".cv-booster" / "cv.toml"
    shutil.copy(RACINE / ".claude" / "skills" / "format-cv" / "cv-exemple.toml", src)
    pdf = generer_html.generer(tomllib.loads(src.read_text(encoding="utf-8-sig")), "principal",
                               ex / ".cv-booster" / "gabarit", src, ex / "CV", ex / "build")
    subprocess.run(["pdftoppm", "-png", "-r", "80", "-singlefile", str(pdf), str(d / "ressources" / "design" / "exemple")],
                   check=True)
    (cv.parent / "lettres").mkdir(exist_ok=True)  # une lettre déjà écrite : elle doit passer au nouveau design
    shutil.copy(RACINE / ".claude" / "skills" / "lettre-motivation" / "lettre-exemple.toml", cv.parent / "lettres" / "exemple.toml")
    t, r, premier, total = appli.tache({"action": "sur_mesure"})
    ligne_mesure("création", r, premier, total)
    gab = cv.parent / "gabarit" / "gabarit.html"
    pdfs = [p for p in (d / "CV").glob("*.pdf") if not p.name.endswith("_ATS.pdf")]
    if not gab.is_file() or not pdfs:
        print("   AUCUN design produit :", r["reponse"][-300:])
        return {"cree": False, "cout": r.get("cout", 0)}
    texte = " ".join(subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdfs[0]), "-"], capture_output=True)
                     .stdout.decode("utf-8").split())
    info = subprocess.run(["pdfinfo", str(pdfs[0])], capture_output=True, text=True).stdout
    c = tomllib.loads(cv.read_text(encoding="utf-8-sig"))
    attendus = [e["poste"] for e in c["experiences"]] + [p[:30] for e in c["experiences"] for p in e["points"]]
    manquants = [a for a in attendus if " ".join(a.split()) not in texte]
    copies = [m for m in ("Prénom", "Intitulé", "exemple.fr") if m in gab.read_text(encoding="utf-8")]
    lettres = list((d / "CV").glob("Lettre_*.pdf"))
    info_l = subprocess.run(["pdfinfo", str(lettres[0])], capture_output=True, text=True).stdout if lettres else ""
    texte_l = " ".join(subprocess.run(["pdftotext", "-enc", "UTF-8", str(lettres[0]), "-"], capture_output=True)
                       .stdout.decode("utf-8").split()) if lettres else ""
    controles = {"une page, imprimée par Edge": "Skia" in info and re.search(r"Pages:\s+1\b", info) is not None,
                 f"tout le contenu ({len(attendus) - len(manquants)}/{len(attendus)})": not manquants,
                 "aucun texte de l'exemple recopié": not copies,
                 "lettre assortie (même moteur, une page, texte complet)": (gab.with_name("lettre.html").is_file()
                     and "Skia" in info_l and re.search(r"Pages:\s+1\b", info_l) is not None
                     and "Accroche : le poste" in texte_l and "agréer" in texte_l)}
    for nom, ok in controles.items():
        print(f"   {'ok ' if ok else 'NON'}  {nom}")
    for m in manquants[:5]:
        print(f"        absent : {m}")
    print(f"   gabarit : {gab.stat().st_size} octets")
    return {"cree": True, "controles": sum(controles.values()), "sur": len(controles), "manquants": len(manquants),
            "cout": r.get("cout", 0)}


def eval_version(appli: Appli, cv: Path) -> dict:
    """« Nouvelle version » sans annonce (adaptateur-offre, section « Sans annonce »). Contrôles : une version de
    plus, les autres versions et le contenu commun intacts, titre adapté au poste, pas de tableau d'annonce."""
    print("\n== Nouvelle version (sans annonce)")
    avant = tomllib.loads(cv.read_text(encoding="utf-8-sig"))
    t, r1, p1, tot1 = appli.tache({"action": "version", "texte": "Product Owner, secteur e-commerce"})
    ligne_mesure("proposition", r1, p1, tot1)
    _, r2, p2, tot2 = appli.tache({"action": "repondre", "tache": t, "texte": "Oui, créez cette version."})
    ligne_mesure("création", r2, p2, tot2)
    apres = tomllib.loads(cv.read_text(encoding="utf-8-sig"))
    nouvelles = [k for k in apres.get("variantes", {}) if k not in avant.get("variantes", {})]
    titre = apres["variantes"][nouvelles[0]].get("titre", "") if nouvelles else ""
    controles = {f"une nouvelle version ({titre or 'aucune'})": len(nouvelles) == 1,
                 "autres versions intactes": all(apres["variantes"].get(k) == v for k, v in avant["variantes"].items()),
                 "contenu commun intact": all(apres.get(k) == avant.get(k) for k in ("experiences", "competences", "formations")),
                 "titre adapté au poste": bool(re.search(r"(?i)product|owner|produit", titre)),
                 "pas de tableau d'annonce": "exigences indispensables" not in r1["reponse"].lower()}
    for nom, ok in controles.items():
        print(f"   {'ok ' if ok else 'NON'}  {nom}")
    return {"controles": sum(controles.values()), "sur": len(controles), "cout": r1.get("cout", 0) + r2.get("cout", 0)}


def eval_design(appli: Appli, cv: Path) -> dict:
    """Agent Design (réglages simples). Exemple : NOTRE design de test .dev/tests/design-fond.html (bleu-vert,
    formes organiques). Contrôles : réglages valides et PDF produit, couleur reprise de l'exemple, réponse sans
    nom de réglage ni code couleur, renvoi vers le Design sur mesure pour les décors, sur mesure non activé."""
    print("\n== Design (réglages simples)")
    d = cv.parent.parent
    sys.path.insert(0, str(RACINE / ".claude" / "skills" / "mise-en-page" / "scripts"))
    import generer_html
    page = d / "exemple-cv.html"
    page.write_text((TESTS / "design-fond.html").read_text(encoding="utf-8"), encoding="utf-8")
    generer_html.imprimer(generer_html.trouver_edge(), page, d / "exemple-cv.pdf")
    subprocess.run(["pdftoppm", "-png", "-r", "80", "-singlefile", str(d / "exemple-cv.pdf"),
                    str(d / "ressources" / "design" / "exemple-cv")], check=True)
    t, r, premier, total = appli.tache({"action": "design"})
    ligne_mesure("design", r, premier, total)
    reglages = cv.parent / "design.toml"
    design = tomllib.loads(reglages.read_text(encoding="utf-8")) if reglages.is_file() else {}
    gen = subprocess.run([sys.executable, "-I", str(d / ".claude/skills/mise-en-page/scripts/generer_cv.py"), "--source", str(cv),
                          "--variante", next(iter(tomllib.loads(cv.read_text(encoding="utf-8-sig"))["variantes"])),
                          "--sortie", str(d / "CV")], capture_output=True, text=True, encoding="utf-8")
    accent = str(design.get("couleurs", {}).get("accent", "")).lstrip("#")
    rgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # noqa: E731
    proche = bool(re.fullmatch(r"[0-9A-Fa-f]{6}", accent)) and min(
        sum((a - b) ** 2 for a, b in zip(rgb(accent), rgb(c))) ** .5 for c in ("2e6f73", "e9c46a")) < 70
    rep = r["reponse"]
    controles = {"réglages valides, PDF produit": gen.returncode == 0,
                 f"couleur de l'exemple reprise ({accent or 'aucune'})": proche,
                 "réponse sans nom de réglage ni code couleur": not re.search(r"\b[a-z_]+ = |\b[0-9A-Fa-f]{6}\b", rep),
                 "renvoi vers le Design sur mesure (formes)": "sur mesure" in rep.lower(),
                 "design sur mesure non activé": not design.get("page", {}).get("sur_mesure", False)}
    for nom, ok in controles.items():
        print(f"   {'ok ' if ok else 'NON'}  {nom}")
    if gen.returncode:
        print("        génération :", (gen.stdout + gen.stderr)[-300:])
    return {"controles": sum(controles.values()), "sur": len(controles), "cout": r.get("cout", 0)}


def eval_sur_mesure_fond(appli: Appli, cv: Path) -> dict:
    """Design sur mesure avec un fond SANS texte fourni (rendu identique). Exemple et fond viennent de NOTRE
    design de test (.dev/tests/design-fond.html) : le fond doit être repris tel quel, pas redessiné."""
    print("\n== Design sur mesure, fond fourni (rendu identique)")
    d = cv.parent.parent
    sys.path.insert(0, str(RACINE / ".claude" / "skills" / "mise-en-page" / "scripts"))
    import generer_html
    edge, source = generer_html.trouver_edge(), (TESTS / "design-fond.html").read_text(encoding="utf-8")
    for nom, html in (("exemple-cv", source), ("fond-sans-texte", source.replace("<body>", '<body class="sans-texte">'))):
        page = d / f"{nom}.html"
        page.write_text(html, encoding="utf-8")
        generer_html.imprimer(edge, page, d / f"{nom}.pdf")
        subprocess.run(["pdftoppm", "-png", "-r", "100", "-singlefile", str(d / f"{nom}.pdf"),
                        str(d / "ressources" / "design" / nom)], check=True)
    t, r, premier, total = appli.tache({"action": "sur_mesure"})
    ligne_mesure("création", r, premier, total)
    gab = cv.parent / "gabarit" / "gabarit.html"
    pdfs = [p for p in (d / "CV").glob("*.pdf") if not p.name.endswith("_ATS.pdf")]
    if not gab.is_file() or not pdfs:
        print("   AUCUN design produit :", r["reponse"][-300:])
        return {"cree": False, "cout": r.get("cout", 0)}
    texte = " ".join(subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdfs[0]), "-"], capture_output=True)
                     .stdout.decode("utf-8").split())
    images = subprocess.run(["pdfimages", "-list", str(pdfs[0])], capture_output=True, text=True).stdout.splitlines()[2:]
    largeurs = [int(l.split()[3]) for l in images if len(l.split()) > 4]
    c = tomllib.loads(cv.read_text(encoding="utf-8-sig"))
    attendus = [e["poste"] for e in c["experiences"]] + [p[:30] for e in c["experiences"] for p in e["points"]]
    manquants = [a for a in attendus if " ".join(a.split()) not in texte]
    g = gab.read_text(encoding="utf-8")
    controles = {"fond repris tel quel (image pleine page)": "fond-sans-texte" in g and any(w >= 700 for w in largeurs),
                 "aucun décor redessiné par-dessus": g.count("<path") == 0,
                 f"tout le contenu ({len(attendus) - len(manquants)}/{len(attendus)})": not manquants,
                 "aucun texte de l'exemple recopié": not any(m in g for m in ("Prénom", "Intitulé", "exemple.fr"))}
    for nom, ok in controles.items():
        print(f"   {'ok ' if ok else 'NON'}  {nom}")
    return {"cree": True, "controles": sum(controles.values()), "sur": len(controles), "cout": r.get("cout", 0)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    TOUTES = ["importer", "relire", "reformuler", "offre", "version", "design", "sur_mesure", "sur_mesure_fond"]
    choix = [a for a in sys.argv[1:] if a in TOUTES] or TOUTES
    bilan = {}
    for nom in choix:
        d = preparer()  # un CV piège neuf pour chaque évaluation
        appli = Appli(d)
        try:
            bilan[nom] = {"importer": eval_importer, "relire": eval_relire, "reformuler": eval_reformuler,
                          "offre": eval_offre, "version": eval_version, "design": eval_design, "sur_mesure": eval_sur_mesure,
                          "sur_mesure_fond": eval_sur_mesure_fond}[nom](
                appli, d / ".cv-booster" / "cv.toml")
        finally:
            appli.fermer()
            shutil.rmtree(d.parent, ignore_errors=True)
    print("\nBILAN :", json.dumps(bilan, ensure_ascii=False))
