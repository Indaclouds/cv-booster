"""Builds the CV as a PDF from a cv.toml, a design.toml and the assets/modele.tex template.

Usage:
    python scripts/generer_cv.py --variante cg
    python scripts/generer_cv.py --source .cv-booster/cv.toml --variante cg --sortie CV
    python scripts/generer_cv.py --variante cg --tex-seul      # no compile (Overleaf fallback)
    python scripts/generer_cv.py --variante cg --apercu        # + low-res PNG preview

The final PDF goes to --sortie (default: CV/), named "CV_Prenom_Nom_Titre.pdf".
An "…_ATS.pdf" version (one column, no decorations) is always produced as well.
Build files (.tex, .log…) go to --build (default: build/ next to cv.toml).
Optional photo: [identite] photo = "ressources/photo.jpg".

No external dependencies: tomllib ships with Python >= 3.11.
Compiling requires pdflatex (MiKTeX or TeX Live).
"""

import argparse
import copy
import re
import shutil
import subprocess
import sys
import tomllib
import unicodedata
from pathlib import Path

# Windows: without this flag, pdflatex opens a console window when the script is run by an app
# with no console (the CV Booster UI). No effect elsewhere.
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)

ASSETS = Path(__file__).resolve().parent.parent / "modeles"
MODELE = ASSETS / "modele.tex"
DESIGN_DEFAUT = ASSETS / "design-defaut.toml"

POLICES = {  # name → LaTeX lines (packages available in MiKTeX and TeX Live)
    "helvetica": r"\usepackage{tgheros}\renewcommand{\familydefault}{\sfdefault}",
    "lato": r"\usepackage[default]{lato}",
    "roboto": r"\usepackage[sfdefault]{roboto}",
    "fira": r"\usepackage[sfdefault]{FiraSans}",
    "opensans": r"\usepackage[default]{opensans}",
    "palatino": r"\usepackage{tgpagella}",
    "charter": r"\usepackage{XCharter}",
    "garamond": r"\usepackage[lining]{ebgaramond}",  # lining figures (readable dates and phone numbers)
}
RUBRIQUES = {"filet": "Filet", "simple": "Simple", "bandeau": "Bandeau", "barre": "Barre"}
PUCES = {"rond": r"\textbullet", "tiret": "–", "carre": r"{\color{accent}\rule[0.25ex]{0.7ex}{0.7ex}}"}

_ECHAPPEMENTS = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def tex(texte: str) -> str:
    """Escapes LaTeX special characters, then makes the space in "25 M€" non-breaking."""
    echappe = "".join(_ECHAPPEMENTS.get(c, c) for c in str(texte))
    return re.sub(r"(\d) ([MkK]?€)", r"\1~\2", echappe)


def nom_fichier(nom: str, titre: str, suffixe: str = "") -> str:
    """« Camille Martin », « Chargée de projet » → CV_Camille_Martin_Chargee_de_projet.pdf"""
    brut = unicodedata.normalize("NFKD", f"CV {nom} {titre} {suffixe}").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", brut).strip("_") + ".pdf"


# --------------------------------------------------------------------------- design

def charger_design(chemin: Path | None, source: Path) -> dict:
    """User design (--design, or design.toml next to cv.toml), filled in from the default design."""
    design = tomllib.loads(DESIGN_DEFAUT.read_text(encoding="utf-8-sig"))
    perso = chemin or source.parent / "design.toml"
    if perso.is_file():
        for section, valeurs in tomllib.loads(perso.read_text(encoding="utf-8-sig")).items():
            design.setdefault(section, {}).update(valeurs)
    return design


def valider_design(d: dict) -> dict:
    """Checks each setting; returns a flat dict of safe values. Short message on error."""
    def choix(section, cle, permis):
        val = d.get(section, {}).get(cle)
        if val not in permis:
            sys.exit(f"design : [{section}] {cle} = {val!r} invalide. Valeurs permises : {', '.join(map(str, permis))}")
        return val

    def nombre(section, cle, mini, maxi):
        val = d.get(section, {}).get(cle)
        if not isinstance(val, (int, float)) or isinstance(val, bool) or not mini <= val <= maxi:
            sys.exit(f"design : [{section}] {cle} = {val!r} invalide. Nombre entre {mini} et {maxi}.")
        return val

    def couleur(cle, vide_permis=False):
        val = str(d.get("couleurs", {}).get(cle, "")).lstrip("#")
        if vide_permis and val == "":
            return ""
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", val):
            sys.exit(f"design : [couleurs] {cle} = {val!r} invalide. Code hexadécimal à 6 caractères, ex. 1F4E79.")
        return val.upper()

    return {
        "accent": couleur("accent"), "secondaire": couleur("secondaire"),
        "entete_fond": couleur("entete_fond", vide_permis=True),
        "police": choix("police", "famille", list(POLICES)),
        "mise_en_page": choix("page", "mise_en_page", ["une_colonne", "deux_colonnes"]),
        "marges": nombre("page", "marges_cm", 1.0, 2.5),
        "puces": choix("page", "puces", list(PUCES)),
        "alignement": choix("entete", "alignement", ["centre", "gauche"]),
        "taille_nom": nombre("entete", "taille_nom", 16, 30),
        "nom_majuscules": choix("entete", "nom_majuscules", [True, False]),
        "bandeau": choix("entete", "bandeau", [True, False]),
        "photo": choix("entete", "photo", ["droite", "gauche"]),
        "photo_provisoire": choix("entete", "photo_provisoire", [True, False]),
        "icones": choix("entete", "icones", [True, False]),
        "qrcode": choix("entete", "qrcode", ["aucun", "linkedin", "email"]),
        "rubriques": choix("rubriques", "style", list(RUBRIQUES)),
        "rubriques_maj": choix("rubriques", "majuscules", [True, False]),
        "competences": choix("competences", "affichage", ["liste", "barres"]),
        "sur_mesure": choix("page", "sur_mesure", [True, False]),
        "pages_sur_mesure": choix("page", "pages_sur_mesure", [1, 2]),
    }


def construire_design(v: dict) -> str:
    """Validated settings → design.tex (read in the template preamble)."""
    marge_hv = f"{max(v['marges'] - 0.2, 0.8):.1f}"
    l = [
        POLICES[v["police"]],
        rf"\definecolor{{accent}}{{HTML}}{{{v['accent']}}}",
        rf"\definecolor{{discret}}{{HTML}}{{{v['secondaire']}}}",
        rf"\definecolor{{entetefond}}{{HTML}}{{{v['entete_fond'] or v['accent']}}}",
        rf"\geometry{{margin={v['marges']}cm,top={marge_hv}cm,bottom={marge_hv}cm}}",
        rf"\renewcommand{{\taillenom}}{{\fontsize{{{v['taille_nom']}}}{{{round(v['taille_nom'] * 1.15)}}}\selectfont}}",
        r"\renewcommand{\alignentete}{\centering}" if v["alignement"] == "centre"
        else r"\renewcommand{\alignentete}{\raggedright}",
        r"\renewcommand{\cassenom}[1]{\MakeUppercase{#1}}" if v["nom_majuscules"] else r"\renewcommand{\cassenom}[1]{#1}",
        r"\renewcommand{\casse}[1]{\MakeUppercase{#1}}" if v["rubriques_maj"] else r"\renewcommand{\casse}[1]{#1}",
        rf"\let\rubrique\rubrique{RUBRIQUES[v['rubriques']]}",
        rf"\renewcommand{{\puce}}{{{PUCES[v['puces']]}}}",
        r"\photogauchetrue" if v["photo"] == "gauche" else r"\photogauchefalse",
    ]
    if v["bandeau"]:
        l += [r"\let\entete\enteteBandeau", r"\renewcommand{\couleurnom}{\color{white}}",
              r"\renewcommand{\couleurtexteentete}{\color{white}}", r"\renewcommand{\couleurcontact}{\color{white}}"]
    return "\n".join(l) + "\n"


# --------------------------------------------------------------------------- content

# Fixed CV text, per language. The language comes from the CV: `langue = "en"` at the top of cv-en.toml (default: fr).
LIBELLES = {
    "fr": {"profil": "Profil", "experiences": "Expériences professionnelles", "competences": "Compétences",
           "formations": "Formations", "langues": "Langues", "qualites": "Qualités", "interets": "Centres d’intérêt",
           "qualites_court": "qualités", "interets_court": "intérêts",
           "contact": "Contact", "et": r"\&", "telephone": "Téléphone", "email": "E-mail", "linkedin": "LinkedIn",
           "ville": "Adresse", "permis": "Permis", "babel": r"\usepackage[french]{babel}\frenchsetup{StandardLists=true}"},
    "en": {"profil": "Profile", "experiences": "Professional experience", "competences": "Skills",
           "formations": "Education", "langues": "Languages", "qualites": "Strengths", "interets": "Interests",
           "qualites_court": "strengths", "interets_court": "interests",
           "contact": "Contact", "et": r"\&", "telephone": "Phone", "email": "Email", "linkedin": "LinkedIn",
           "ville": "Address", "permis": "Driving licence", "babel": r"\usepackage[british]{babel}"},
}
L = LIBELLES["fr"]  # language of the current CV (set in main)


def choisir_langue(cv: dict) -> str:
    global L
    langue = cv.get("langue", "fr")
    if langue not in LIBELLES:
        sys.exit(f"cv : langue = {langue!r} inconnue. Langues prises en charge : {', '.join(LIBELLES)}")
    L = LIBELLES[langue]
    return langue


CONTACTS = [  # key (= label in LIBELLES, text read by ATS), icon (decorative)
    ("telephone", r"\faPhone"), ("email", r"\faEnvelope"), ("linkedin", r"\faLinkedin"), ("ville", r"\faMapMarker*"),
    ("permis", r"\faCar"),
]


def code_photo(photo: str | None, v: dict, lateral: bool) -> str | None:
    """LaTeX code for the photo: real photo, placeholder silhouette, or nothing."""
    if photo:
        return rf"\photoLaterale{{{photo}}}" if lateral else rf"\imagePhotoEntete{{{photo}}}"
    if v["photo_provisoire"]:
        return r"\silhouetteLaterale" if lateral else r"\silhouetteEntete"
    return None


def texte_qr(ident: dict, v: dict) -> str | None:
    """Text encoded in the QR code (a real link), or None."""
    if v["qrcode"] == "linkedin" and ident.get("linkedin"):
        lien = ident["linkedin"] if ident["linkedin"].startswith("http") else "https://" + ident["linkedin"]
    elif v["qrcode"] == "email" and ident.get("email"):
        lien = "mailto:" + ident["email"]
    else:
        if v["qrcode"] != "aucun":
            print(f"QR code {v['qrcode']} demandé, mais l'information manque dans le CV : pas de QR code.")
        return None
    if not re.fullmatch(r"[A-Za-z0-9:/.@_\-?=]+", lien):
        print("QR code : lien contenant des caractères non pris en charge, ignoré.")
        return None
    return lien.replace("_", r"\_")


def blocs_communs(cv: dict) -> dict:
    """Content pieces shared by both layouts."""
    ident = cv["identite"]
    divers = cv.get("divers", {})
    return {
        "ident": ident,
        "contacts": [(L[k], tex(ident[k]), ico) for k, ico in CONTACTS if ident.get(k)],
        "langues": " · ".join(f"{tex(l['langue'])} ({tex(l['niveau'])})" for l in cv.get("langues", [])),
        "forces": " · ".join(tex(x) for x in divers.get("forces", [])),
        "interets": " · ".join(tex(x) for x in divers.get("interets", [])),
    }


def lignes_experiences(cv: dict, macro: str) -> list[str]:
    lignes = []
    for e in cv["experiences"]:
        lignes.append(rf"\{macro}{{{tex(e['poste'])}}}{{{tex(e['entreprise'])}}}{{{tex(e['dates'])}}}{{{tex(e['lieu'])}}}")
        lignes.append(r"\begin{points}")
        lignes += [rf"  \item {tex(p)}" for p in e["points"]]
        lignes.append(r"\end{points}")
    return lignes


def contenu_une_colonne(cv: dict, v: dict, variante: dict, photo: str | None) -> list[str]:
    b = blocs_communs(cv)
    if v["icones"]:
        contact = r"\quad ".join(rf"{ico}~{val}" for _, val, ico in b["contacts"])
    else:
        contact = r" \textperiodcentered{} ".join(val for _, val, _ in b["contacts"])
    entete = f"{{{tex(b['ident']['nom'])}}}{{{tex(variante['titre'])}}}{{{contact}}}"
    image = code_photo(photo, v, lateral=False)
    l = [rf"\entetephoto{entete}{{{image}}}" if image else rf"\entete{entete}"]
    if v["qrcode"] != "aucun":
        print("QR code : disponible seulement en mise en page deux colonnes.")
    l += [rf"\rubrique{{{L['profil']}}}", tex(variante["accroche"]) + r"\par"]
    l.append(rf"\rubrique{{{L['experiences']}}}")
    l += lignes_experiences(cv, "experience")
    l.append(rf"\rubrique{{{L['competences']}}}")
    for c in cv["competences"]:
        outils = " · ".join(tex(o) for o in c["outils"])
        l.append(rf"\competence{{{tex(c['domaine'])}}}{{{tex(c['detail'])}}}{{{outils}}}")
    l.append(rf"\rubrique{{{L['formations']}}}")
    for f in cv["formations"]:
        l.append(rf"\formation{{{tex(f['diplome'])}}}{{{tex(f['ecole'])}}}{{{tex(f['annees'])}}}")
    titre = [L["langues"]] + [L[court] for court, cle in (("qualites_court", "forces"), ("interets_court", "interets"))
                              if b[cle]]
    l.append(rf"\rubrique{{{', '.join(titre[:-1]) + ' ' + L['et'] + ' ' + titre[-1] if len(titre) > 1 else titre[0]}}}")
    l.append(rf"\ligne{{{L['langues']}}}{{{b['langues']}}}")
    if b["forces"]:
        l.append(rf"\ligne{{{L['qualites']}}}{{{b['forces']}}}")
    if b["interets"]:
        l.append(rf"\ligne{{{L['interets']}}}{{{b['interets']}}}")
    return l


def contenu_deux_colonnes(cv: dict, v: dict, variante: dict, photo: str | None) -> list[str]:
    b = blocs_communs(cv)
    l = [r"\begin{paracol}{2}"]
    # ---- left column: photo, skills, languages, contact, interests, QR code
    if image := code_photo(photo, v, lateral=True):
        l.append(image)
    l.append(rf"\rubriqueLaterale{{{L['competences']}}}")
    niveaux = cv.get("niveaux", [])
    if v["competences"] == "barres" and niveaux:
        for n in niveaux:
            niv = n.get("niveau")
            if not isinstance(niv, int) or not 1 <= niv <= 5:
                sys.exit(f"cv : [[niveaux]] « {n.get('nom')} » : niveau = {niv!r} invalide (entier de 1 à 5).")
            l.append(rf"\niveau{{{tex(n['nom'])}}}{{{niv}}}{{{tex(n.get('mention', ''))}}}")
    else:
        if v["competences"] == "barres":
            print("Barres de niveau demandées mais aucun [[niveaux]] dans le CV : compétences affichées en liste.")
        for c in cv["competences"]:
            outils = " · ".join(tex(o) for o in c["outils"])
            l.append(rf"\competenceEtroite{{{tex(c['domaine'])}}}{{{tex(c['detail'])}}}{{{outils}}}")
    l.append(rf"\rubriqueLaterale{{{L['langues']}}}")
    l += [rf"{{\small {tex(x['langue'])}}}\hfill{{\small\color{{discret}}{tex(x['niveau'])}}}\par"
          for x in cv.get("langues", [])]
    l.append(rf"\rubriqueLaterale{{{L['contact']}}}")
    if v["icones"]:
        l += [rf"\contactIcone{{{ico}}}{{{val}}}" for _, val, ico in b["contacts"]]
    else:
        l += [rf"\contact{{{lib}}}{{{val}}}" for lib, val, _ in b["contacts"]]
    if b["forces"]:
        l += [rf"\rubriqueLaterale{{{L['qualites']}}}", rf"{{\small {b['forces']}}}\par"]
    if b["interets"]:
        l += [rf"\rubriqueLaterale{{{L['interets']}}}", rf"{{\small {b['interets']}}}\par"]
    if qr := texte_qr(b["ident"], v):
        l.append(rf"\qrLateral{{{qr}}}")
    # ---- right column: name, profile, experience, education
    l.append(r"\switchcolumn")
    l.append(rf"\enteteColonne{{{tex(b['ident']['nom'])}}}{{{tex(variante['titre'])}}}")
    l.append(r"\small")  # narrower column: text one size smaller (like two-column templates)
    l += [rf"\rubrique{{{L['profil']}}}", tex(variante["accroche"]) + r"\par"]
    l.append(rf"\rubrique{{{L['experiences']}}}")
    l += lignes_experiences(cv, "experienceColonne")
    l.append(rf"\rubrique{{{L['formations']}}}")
    for f in cv["formations"]:
        l.append(rf"\formationColonne{{{tex(f['diplome'])}}}{{{tex(f['ecole'])}}}{{{tex(f['annees'])}}}")
    l.append(r"\end{paracol}")
    return l


def appliquer_variante(cv: dict, variante: dict) -> dict:
    """Copy of the CV adapted to a variant, leaving the shared content alone:
    - remplacements = { "original text" = "adapted text" }: experience bullets and skill details;
    - ordre_competences = ["Domain 1", …]: domains moved to the top (the rest keep their original order).
    Used for versions tailored to a job offer."""
    cv = copy.deepcopy(cv)
    remplacements = variante.get("remplacements", {})
    utilises = set()
    for e in cv.get("experiences", []):
        for i, p in enumerate(e["points"]):
            if p in remplacements:
                e["points"][i] = remplacements[p]
                utilises.add(p)
    for c in cv.get("competences", []):
        if c["detail"] in remplacements:
            c["detail"] = remplacements[c["detail"]]
            utilises.add(c["detail"])
    for oublie in set(remplacements) - utilises:
        print(f"Remplacement ignoré (texte d'origine introuvable) : « {oublie[:60]}… »")
    if ordre := variante.get("ordre_competences"):
        rang = {d: i for i, d in enumerate(ordre)}
        cv["competences"] = sorted(cv.get("competences", []), key=lambda c: rang.get(c["domaine"], len(rang)))
    return cv


def construire_contenu(cv: dict, v: dict, variante: str, photo: str | None) -> str:
    if variante not in cv["variantes"]:
        sys.exit(f"Variante inconnue « {variante} ». Disponibles : {', '.join(cv['variantes'])}")
    faire = contenu_deux_colonnes if v["mise_en_page"] == "deux_colonnes" else contenu_une_colonne
    choisie = cv["variantes"][variante]
    return "\n".join(faire(appliquer_variante(cv, choisie), v, choisie, photo)) + "\n"


def nom_pdf(cv: dict, variante: str, suffixe: str = "") -> str:
    """PDF name. If an earlier variant has the same title (e.g. a version tailored to a job offer),
    the variant name is appended: otherwise the two PDFs would overwrite each other."""
    variantes = list(cv["variantes"])
    titre = cv["variantes"][variante]["titre"]
    doublon = any(cv["variantes"][k]["titre"] == titre for k in variantes[:variantes.index(variante)])
    precision = variante.replace("_", " ") if doublon else ""
    if cv.get("langue", "fr") != "fr":  # translated CV: "…_EN.pdf", never mixed up with the French version
        precision += f" {cv['langue'].upper()}"
    return nom_fichier(cv["identite"].get("nom", ""), f"{titre} {precision}", suffixe)


IMAGES = {".jpg", ".jpeg", ".png"}


def trouver_photo(cv: dict, source: Path) -> Path | None:
    """Photo set in the CV, otherwise an image dropped into ressources/ (outside design/).
    So dropping a photo in and clicking "Générer" is enough: no call to Claude."""
    if chemin := cv["identite"].get("photo"):
        if Path(chemin).is_file():
            return Path(chemin)
        print(f"Photo introuvable ({chemin}).")
    ressources = source.resolve().parent.parent / "ressources"
    images = sorted(f for f in ressources.glob("*") if f.suffix.lower() in IMAGES) if ressources.is_dir() else []
    if not images:
        return None
    choisie = next((f for f in images if "photo" in f.stem.lower()), images[0])
    if len(images) > 1:
        print(f"Plusieurs images dans ressources/ : « {choisie.name} » utilisée comme photo.")
    return choisie


def preparer_photo(cv: dict, source: Path, build: Path) -> str | None:
    """Copies the photo into build/; returns its name, or None if there is none."""
    src = trouver_photo(cv, source)
    if not src:
        return None
    dest = f"photo{src.suffix.lower()}"
    shutil.copy(src, build / dest)
    return dest


# --------------------------------------------------------------------------- compilation

def compiler(cv: dict, v: dict, args, build: Path, photo: str | None, suffixe: str = "") -> Path | None:
    """Writes contenu.tex + design.tex, compiles, copies the PDF to --sortie. Returns its path."""
    (build / "contenu.tex").write_text(construire_contenu(cv, v, args.variante, photo), encoding="utf-8")
    (build / "design.tex").write_text(construire_design(v), encoding="utf-8")
    # French: babel "french" (+ our bullets, not babel's dashes); English: "british"
    (build / "langue.tex").write_text(L["babel"] + "\n", encoding="utf-8")
    shutil.copy(MODELE, build / "modele.tex")
    if args.tex_seul:
        print(f"LaTeX généré dans {build}")
        return None

    job = f"CV_{args.variante}{suffixe}"
    cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"-jobname={job}", "modele.tex"]

    def compiler_une_fois():
        r = subprocess.run(cmd, cwd=build, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=SANS_FENETRE)
        if r.returncode != 0:
            # Only show the end of the log: that's where the error is (and it saves tokens)
            print("\n".join(r.stdout.splitlines()[-25:]))
            sys.exit(f"Échec de la compilation (log complet : {build / (job + '.log')})")
        n = re.search(r"Output written on .*?\((\d+) pages?", r.stdout)
        return r, int(n.group(1)) if n else 1

    res, nb_pages = compiler_une_fois()
    if nb_pages == 2:
        # Slight overflow (often one line, especially in English): tighten line spacing by 5%, once only.
        # Beyond that, just warn: the content has to get shorter, the layout shouldn't cheat.
        with open(build / "design.tex", "a", encoding="utf-8") as f:
            f.write("\\linespread{0.95}\n")
        res, nb_pages = compiler_une_fois()
        if nb_pages == 1:
            print("Ajustement : interligne très légèrement resserré pour tenir sur une page.")

    args.sortie.mkdir(parents=True, exist_ok=True)
    final = args.sortie.resolve() / nom_pdf(cv, args.variante, suffixe.strip("_"))
    shutil.copy(build / f"{job}.pdf", final)
    print(f"PDF généré : {final}")
    if nb_pages > 1:
        print(f"ATTENTION : {nb_pages} pages. Un CV doit tenir sur une page : raccourcir le contenu.")
    return final


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=".cv-booster/cv.toml", type=Path, help="fichier cv.toml")
    parser.add_argument("--variante", default="cg", help="clé de [variantes.*] dans cv.toml")
    parser.add_argument("--sortie", default="CV", type=Path, help="dossier du PDF final")
    parser.add_argument("--build", type=Path, help="dossier des fichiers techniques (défaut : build/ près de cv.toml)")
    parser.add_argument("--design", type=Path, help="design.toml (défaut : design.toml près de cv.toml, sinon défaut)")
    parser.add_argument("--apercu", action="store_true", help="produire aussi un aperçu PNG basse définition")
    parser.add_argument("--tex-seul", action="store_true", help="générer le .tex sans compiler")
    args = parser.parse_args()

    cv = tomllib.loads(args.source.read_text(encoding="utf-8-sig"))
    choisir_langue(cv)
    v = valider_design(charger_design(args.design, args.source))
    build = (args.build or args.source.parent / "build").resolve()
    build.mkdir(parents=True, exist_ok=True)
    photo = preparer_photo(cv, args.source, build)
    if not args.tex_seul and not shutil.which("pdflatex"):
        sys.exit("pdflatex introuvable : installer MiKTeX ou TeX Live, ou relancer avec --tex-seul.")

    gabarit = args.source.parent / "gabarit"
    if v["sur_mesure"] and (gabarit / "gabarit.html").is_file() and not args.tex_seul:
        # Custom design (maquettiste agent): the design version comes from the HTML template, printed by Edge;
        # the ATS version below stays in plain LaTeX, for job sites.
        sys.path.insert(0, str(Path(__file__).parent))  # run with "python -I": the script's folder isn't on the path
        import generer_html
        final = generer_html.generer(cv, args.variante, gabarit.resolve(), args.source.resolve(),
                                     args.sortie.resolve(), build, pages_max=v["pages_sur_mesure"])
    else:
        final = compiler(cv, v, args, build, photo)
    if not photo and v["photo_provisoire"] and not v["sur_mesure"]:
        print("PHOTO PROVISOIRE : silhouette à la place de la photo. Déposez votre photo dans « Mes infos » "
              "puis cliquez à nouveau sur Générer.")
    if not args.tex_seul:
        # Always a version for job sites: same colors and font, one column, no
        # decorations. Simple rule: the normal CV for humans, the _ATS one for bots.
        ats = copy.deepcopy(v) | {"mise_en_page": "une_colonne", "bandeau": True, "icones": False,
                                  "qrcode": "aucun", "photo_provisoire": False}
        compiler(cv, ats, args, build, photo, suffixe="_ATS")
        print("Version ATS (une colonne) : à utiliser sur les sites d'emploi et les formulaires en ligne.")

    if args.apercu and final:
        if shutil.which("pdftoppm"):
            # 60 dpi: enough to judge the layout, and cheap to read back (tokens)
            subprocess.run(["pdftoppm", "-png", "-r", "60", "-f", "1", "-l", "1", "-singlefile",
                            str(final), str(build / "apercu")], check=False, creationflags=SANS_FENETRE)
            print(f"Aperçu : {build / 'apercu.png'}")
        else:
            print("Aperçu impossible : pdftoppm absent.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
