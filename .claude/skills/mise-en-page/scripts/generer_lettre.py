"""Met en page les lettres de motivation (.cv-booster/lettres/*.toml) en PDF, dans CV/.

Usage :
    python scripts/generer_lettre.py                    # les lettres modifiées depuis leur PDF
    python scripts/generer_lettre.py --toutes
    python scripts/generer_lettre.py --source .cv-booster/cv.toml --sortie CV

En-tête (nom, contacts), lieu, date et signature viennent du CV ; police et couleur, du design du CV.
Le PDF s'appelle « Lettre_Prenom_Nom_Entreprise.pdf ».
"""

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generer_cv as cvgen  # noqa: E402  (mêmes polices, couleurs et échappement que le CV)

MODELE = cvgen.ASSETS / "lettre.tex"
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def nom_pdf(cv: dict, lettre: dict) -> str:
    brut = f"Lettre {cv.get('identite', {}).get('nom', '')} {lettre.get('entreprise', '')}"
    brut = unicodedata.normalize("NFKD", brut).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", brut).strip("_") + ".pdf"


def lieu_et_date(cv: dict) -> str:
    ville = re.sub(r"^[\d\s–-]+", "", str(cv.get("identite", {}).get("ville", ""))).strip()
    j = date.today()
    jour = "1er" if j.day == 1 else str(j.day)
    return f"{ville + ', ' if ville else ''}le {jour} {MOIS[j.month - 1]} {j.year}"


def contenu(cv: dict, l: dict) -> str:
    t = cvgen.tex
    ident = cv.get("identite", {})
    nom = ident.get("nom", "")
    contacts = [ident.get(k, "") for k in ("telephone", "email", "ville")]
    lignes = [
        rf"{{\Large\bfseries\color{{accent}}{t(nom)}}}\par\smallskip",
        rf"{{\small\color{{discret}}{t(' · '.join(c for c in contacts if c))}}}\par",
        r"\vspace{1.4cm}",
    ]
    if dest := [d for d in l.get("destinataire", []) if str(d).strip()]:
        lignes += [r"\hfill\begin{minipage}[t]{7.5cm}", r"\\ ".join(t(d) for d in dest), r"\end{minipage}\par",
                   r"\vspace{0.9cm}"]
    lignes += [rf"\hfill {t(lieu_et_date(cv))}\par", r"\vspace{0.8cm}"]
    if l.get("objet"):
        lignes += [rf"\textbf{{Objet :}} {t(l['objet'])}\par", r"\vspace{0.7cm}"]
    lignes += [rf"{t(l.get('appel', 'Madame, Monsieur,'))}\par", r"\vspace{0.45cm}",
               r"\setlength{\parskip}{0.75em}"]
    lignes += [t(p) + r"\par" for p in l.get("paragraphes", []) if str(p).strip()]
    if l.get("formule"):
        lignes.append(t(l["formule"]) + r"\par")
    lignes += [r"\vspace{0.9cm}", rf"\hfill {t(nom)}\par"]
    return "\n".join(lignes) + "\n"


def compiler(cv: dict, lettre_toml: Path, design: dict, build: Path, sortie: Path,
             source: Path | None = None) -> Path | None:
    l = tomllib.loads(lettre_toml.read_text(encoding="utf-8-sig"))
    gabarit = source.parent / "gabarit" if source else None
    if design.get("sur_mesure") and gabarit and (gabarit / "lettre.html").is_file():
        # Design sur mesure : la lettre assortie (mêmes formes et mise en page que le CV), imprimée par Edge
        import generer_html
        return generer_html.generer_lettre(cv, l, gabarit.resolve(), source.resolve(),
                                           sortie.resolve() / nom_pdf(cv, l), build, lieu_et_date(cv))
    job = f"lettre_{lettre_toml.stem}"
    (build / "contenu-lettre.tex").write_text(contenu(cv, l), encoding="utf-8")
    (build / "design-lettre.tex").write_text(
        cvgen.POLICES[design["police"]] + "\n" + rf"\definecolor{{accent}}{{HTML}}{{{design['accent']}}}" + "\n"
        + rf"\definecolor{{discret}}{{HTML}}{{{design['secondaire']}}}" + "\n", encoding="utf-8")
    shutil.copy(MODELE, build / "lettre.tex")
    res = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"-jobname={job}", "lettre.tex"],
                         cwd=build, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         creationflags=cvgen.SANS_FENETRE)
    if res.returncode != 0:
        print("\n".join(res.stdout.splitlines()[-20:]))
        print(f"Échec de la mise en page de la lettre {lettre_toml.name}.")
        return None
    sortie.mkdir(parents=True, exist_ok=True)
    final = sortie.resolve() / nom_pdf(cv, l)
    shutil.copy(build / f"{job}.pdf", final)
    print(f"PDF généré : {final}")
    pages = re.search(r"Output written on .*?\((\d+) pages?", res.stdout)
    if pages and int(pages.group(1)) > 1:
        print(f"ATTENTION : la lettre {lettre_toml.stem} fait {pages.group(1)} pages : la raccourcir.")
    return final


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default=".cv-booster/cv.toml", type=Path)
    p.add_argument("--lettres", type=Path, help="dossier des lettres (défaut : lettres/ près de cv.toml)")
    p.add_argument("--sortie", default="CV", type=Path)
    p.add_argument("--toutes", action="store_true", help="toutes les lettres, même déjà à jour")
    args = p.parse_args()
    dossier = args.lettres or args.source.parent / "lettres"
    if not dossier.is_dir():
        return
    if not shutil.which("pdflatex"):
        sys.exit("pdflatex introuvable.")
    cv = tomllib.loads(args.source.read_text(encoding="utf-8-sig"))
    design = cvgen.valider_design(cvgen.charger_design(None, args.source))
    build = (args.source.parent / "build").resolve()
    build.mkdir(parents=True, exist_ok=True)
    for f in sorted(dossier.glob("*.toml")):
        try:
            l = tomllib.loads(f.read_text(encoding="utf-8-sig"))
        except tomllib.TOMLDecodeError as e:
            print(f"Lettre {f.name} illisible : {e}")
            continue
        pdf = args.sortie / nom_pdf(cv, l)
        if args.toutes or not pdf.is_file() or pdf.stat().st_mtime < f.stat().st_mtime:
            compiler(cv, f, design, build, args.sortie, args.source)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
