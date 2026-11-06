"""Design sur mesure : remplit le gabarit HTML (.cv-booster/gabarit/gabarit.html) avec le contenu du CV,
puis le fait imprimer en PDF A4 par Microsoft Edge (présent sur tout Windows 10/11, rien à installer).

    python scripts/generer_html.py --variante principal
    python scripts/generer_html.py --source .cv-booster/cv.toml --variante principal --sortie CV

Le gabarit est écrit par l'agent « maquettiste » (annexe gabarit-html.md) ; le CONTENU vient toujours de
cv.toml, rempli ici par script : l'IA ne retape aucune information.
Syntaxe du gabarit (type Mustache) : {{nom}}, {{identite.email}}, {{#experiences}}…{{/experiences}},
{{^photo}}…{{/photo}} (si absent), {{.}} (élément courant d'une liste de textes). Tout est échappé.
Une page A4 : si le contenu déborde, la variable CSS --echelle passe de 1 à 0,8 jusqu'à tenir.
Normalement lancé par generer_cv.py quand le design est « sur mesure » (la version ATS reste en LaTeX).
"""

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import generer_cv as gc  # noqa: E402  (variantes, photo, noms des PDF, libellés par langue)

SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ECHELLES = (1, 0.96, 0.92, 0.88, 0.84, 0.8)        # en dessous de 0,8 le texte devient trop petit
FICHIERS_UTILES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ttf", ".otf", ".woff", ".woff2"}
POLICES = Path(__file__).resolve().parent.parent / "polices"  # polices libres (OFL) embarquées, voir LISEZMOI.txt
BALISE = re.compile(r"\{\{\s*([#^/]?)\s*([\w.]+)\s*\}\}")


# --------------------------------------------------------------------------- gabarit (type Mustache)
def analyser(modele: str) -> list:
    """Texte du gabarit → arbre : chaînes, ("=", nom), ("#"|"^", nom, enfants). Erreur claire si mal fermé."""
    racine: list = []
    pile = [("", racine)]
    pos = 0
    for m in BALISE.finditer(modele):
        pile[-1][1].append(modele[pos:m.start()])
        pos = m.end()
        genre, nom = m.groups()
        if genre in ("#", "^"):
            noeud = (genre, nom, [])
            pile[-1][1].append(noeud)
            pile.append((nom, noeud[2]))
        elif genre == "/":
            if len(pile) == 1 or pile[-1][0] != nom:
                raise ValueError(f"gabarit : {{{{/{nom}}}}} ne ferme aucun {{{{#{nom}}}}}")
            pile.pop()
        else:
            pile[-1][1].append(("=", nom))
    pile[-1][1].append(modele[pos:])
    if len(pile) > 1:
        raise ValueError(f"gabarit : {{{{#{pile[-1][0]}}}}} n'est jamais fermé par {{{{/{pile[-1][0]}}}}}")
    return racine


def _cles(x, acc: set) -> set:
    if isinstance(x, dict):
        for k, v in x.items():
            acc.add(k)
            _cles(v, acc)
    elif isinstance(x, list):
        for v in x:
            _cles(v, acc)
    return acc


def _valeur(nom: str, pile: list):
    if nom == ".":
        return pile[-1]
    tete, *reste = nom.split(".")
    for ctx in reversed(pile):
        if isinstance(ctx, dict) and tete in ctx:
            v = ctx[tete]
            for r in reste:
                v = v.get(r) if isinstance(v, dict) else None
            return v
    return None


def rendre(modele: str, contexte: dict) -> tuple[str, list[str]]:
    """Gabarit rempli + noms inconnus (fautes de frappe probables, signalées à l'agent)."""
    connus, inconnus, sortie = _cles(contexte, {"."}), [], []

    def produire(noeuds, pile):
        for n in noeuds:
            if isinstance(n, str):
                sortie.append(n)
                continue
            genre, nom = n[0], n[1]
            if nom != "." and nom.split(".")[0] not in connus and nom not in inconnus:
                inconnus.append(nom)
            v = _valeur(nom, pile)
            if genre == "=":
                if v is None or v is False:
                    continue
                if isinstance(v, list):
                    v = ", ".join(str(x) for x in v if not isinstance(x, dict))
                sortie.append(html.escape(str(v)))
            elif genre == "#":
                if isinstance(v, list):
                    for x in v:
                        produire(n[2], pile + [x])
                elif v:
                    produire(n[2], pile + [v])
            elif not v:  # ^ : seulement si absent ou vide
                produire(n[2], pile)

    produire(analyser(modele), [contexte])
    return "".join(sortie), inconnus


# --------------------------------------------------------------------------- contenu
def construire_contexte(cv: dict, cle: str, photo: str | None) -> dict:
    """Tout ce que le gabarit peut afficher (liste documentée dans gabarit-html.md)."""
    if cle not in cv["variantes"]:
        sys.exit(f"Variante inconnue « {cle} ». Disponibles : {', '.join(cv['variantes'])}")
    langue = gc.choisir_langue(cv)
    variante = cv["variantes"][cle]
    cv = gc.appliquer_variante(cv, variante)
    ident = dict(cv.get("identite", {}))
    ident.pop("photo", None)
    prenom, _, famille = ident.get("nom", "").partition(" ")
    lib = {k: v for k, v in gc.LIBELLES[langue].items() if k not in {"babel", "et"}} | {"et": "&"}
    contacts = [{"type": k, "libelle": lib.get(k, k), "valeur": ident[k]}
                for k in ("telephone", "email", "linkedin", "ville", "permis") if ident.get(k)]
    niveaux = []
    for n in cv.get("niveaux", []):
        niv = max(0, min(5, int(n.get("niveau", 0) or 0)))
        niveaux.append(dict(n, niveau=niv, pourcent=niv * 20,
                            pastilles=[{"pleine": i < niv} for i in range(5)]))
    divers = cv.get("divers", {})

    def numeroter(liste: list[dict]) -> list[dict]:  # numero (1, 2…) et dernier : listes numérotées, séparateurs
        return [dict(x, numero=i + 1, dernier=i == len(liste) - 1) for i, x in enumerate(liste)]

    interets, forces = list(divers.get("interets", [])), list(divers.get("forces", []))
    listes = {"contacts": contacts, "experiences": cv.get("experiences", []), "competences": cv.get("competences", []),
              "formations": cv.get("formations", []), "langues": cv.get("langues", []), "niveaux": niveaux,
              "interets": interets, "forces": forces}
    # avec_x : afficher un titre de rubrique UNE fois si la liste existe ({{#x}} répéterait le titre par élément)
    return {f"avec_{k}": bool(v) for k, v in listes.items()} | {
        "langue": langue, "lib": lib, "photo": photo,
        "nom": ident.get("nom", ""), "prenom": prenom, "nom_famille": famille or prenom,
        "identite": ident, "contacts": numeroter(contacts),
        "titre": variante.get("titre", ""), "accroche": variante.get("accroche", ""),
        "experiences": numeroter([dict(e, points=list(e.get("points", []))) for e in cv.get("experiences", [])]),
        "competences": numeroter([dict(c, outils=list(c.get("outils", [])), outils_texte=", ".join(c.get("outils", [])))
                                  for c in cv.get("competences", [])]),
        "formations": numeroter(list(cv.get("formations", []))), "langues": numeroter(list(cv.get("langues", []))),
        "niveaux": numeroter(niveaux),
        "interets": interets, "interets_texte": " · ".join(interets),
        "forces": forces, "forces_texte": " · ".join(forces),
    }


# --------------------------------------------------------------------------- impression par Edge
def trouver_edge() -> str | None:
    if p := os.environ.get("CVB_EDGE"):
        return p
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base and (f := Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe").is_file():
            return str(f)
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")


def imprimer(edge: str, page: Path, pdf: Path) -> None:
    pdf.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="cvb-edge-") as profil:  # profil jetable : Edge peut être ouvert
        subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                        "--disable-extensions", f"--user-data-dir={profil}", "--no-pdf-header-footer",
                        "--virtual-time-budget=3000", f"--print-to-pdf={pdf}", page.as_uri()],
                       capture_output=True, timeout=120, creationflags=SANS_FENETRE)
    if not pdf.is_file():
        sys.exit("Edge n'a pas produit le PDF du design sur mesure.")


def textes_attendus(ctx: dict) -> list[str]:
    """Repères qui DOIVENT se lire dans le PDF : un gabarit à hauteur fixe peut couper la fin sans rien dire."""
    t = [e.get("poste", "") for e in ctx["experiences"]] + [f.get("diplome", "") for f in ctx["formations"]]
    t += [e["points"][-1] for e in ctx["experiences"] if e.get("points")]  # la fin de chaque expérience
    t += [ctx["identite"].get("email", "")] + [l.get("langue", "") for l in ctx["langues"]]
    # tout le contenu, pas seulement la fin : un gabarit ne doit rien omettre pour gagner de la place
    t += [ctx["accroche"]] + [c.get(k, "") for c in ctx["competences"] for k in ("domaine", "detail")]
    t += ctx["interets"][:1] + ctx["forces"][:1]
    return [" ".join(x.split())[:24] for x in t if x and x.strip()]


def manquants(pdf: Path, attendus: list[str]) -> list[str]:
    """Repères absents du texte du PDF (vide si pdftotext manque : pas de contrôle possible)."""
    if not shutil.which("pdftotext"):
        return []
    res = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"], capture_output=True, creationflags=SANS_FENETRE)
    texte = " ".join(res.stdout.decode("utf-8", "replace").replace("­", "").split())
    return [a for a in attendus if a not in texte]


# Lisibilité : pour chaque texte, ce qui est peint DESSOUS (forme SVG ou fond coloré) et le contraste avec la
# couleur du texte (formule WCAG). Sous 2 : illisible (ex. titre rose sur une forme rose : 1,15) ; un nom blanc
# sur un bandeau foncé, voulu, est au-dessus (2,8). Les dégradés et les images (fond fourni) ne sont pas jugés.
SEUIL_CONTRASTE = 2.0
CONTROLE_JS = r"""<script>(() => {
const lum = (c) => { const m = c.match(/[\d.]+/g); if (!m) return null;
  const v = m.slice(0, 3).map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
  return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
const res = []; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n;
while ((n = w.nextNode())) {
  const el = n.parentElement; if (!n.textContent.trim() || el.closest("script,style,svg")) continue;
  const st = getComputedStyle(el); if (st.visibility === "hidden" || st.display === "none") continue;
  const r = document.createRange(); r.selectNodeContents(n); let pire = 99;
  for (const b of r.getClientRects()) for (const fx of [.2, .5, .8]) {
    for (const d of document.elementsFromPoint(b.left + b.width * fx, b.top + b.height / 2)) {
      if (d === el || (d.contains(el) && !(d instanceof SVGElement))) continue;
      let fond = null;
      if (d instanceof SVGGeometryElement) { const f = getComputedStyle(d).fill; if (f.startsWith("rgb")) fond = f; else break; }
      else if (d.tagName === "IMG") break;
      else { const bg = getComputedStyle(d).backgroundColor; if (bg && !/rgba\(0, 0, 0, 0\)|transparent/.test(bg)) fond = bg; }
      if (!fond) continue;
      const a = lum(st.color), f2 = lum(fond); if (a !== null && f2 !== null) pire = Math.min(pire, (Math.max(a, f2) + .05) / (Math.min(a, f2) + .05));
      break; } }
  if (pire < """ + str(SEUIL_CONTRASTE) + r""") res.push(n.textContent.trim().replace(/\s+/g, " ").slice(0, 40)); }
const p = document.createElement("pre"); p.id = "cvb-controle"; p.textContent = JSON.stringify([...new Set(res)]); document.body.appendChild(p);
})();</script>"""


def controle_lisibilite(edge: str, page: Path) -> list[str]:
    """Textes posés sur un décor de couleur trop proche (contraste < SEUIL_CONTRASTE). Edge rend la page, un
    script mesure ce qu'il y a sous chaque texte (elementsFromPoint), le résultat est lu dans le DOM."""
    essai = page.with_name("controle.html")
    essai.write_text(page.read_text(encoding="utf-8").replace("</body>", CONTROLE_JS + "</body>", 1)
                     if "</body>" in page.read_text(encoding="utf-8") else page.read_text(encoding="utf-8") + CONTROLE_JS,
                     encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="cvb-edge-") as profil:
        res = subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-first-run", "--disable-extensions",
                              f"--user-data-dir={profil}", "--virtual-time-budget=3000", "--dump-dom", essai.as_uri()],
                             capture_output=True, timeout=120, creationflags=SANS_FENETRE)
    m = re.search(rb'<pre id="cvb-controle">(.*?)</pre>', res.stdout, re.S)
    if not m:
        return []  # contrôle impossible (rare) : on ne bloque pas la génération
    try:
        return list(json.loads(html.unescape(m.group(1).decode("utf-8", "replace"))))
    except ValueError:
        return []


def compter_pages(pdf: Path) -> int:
    n = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf.read_bytes()))
    if n or not shutil.which("pdfinfo"):
        return n
    res = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, creationflags=SANS_FENETRE)
    m = re.search(r"^Pages:\s+(\d+)", res.stdout, re.M)
    return int(m.group(1)) if m else 0


# --------------------------------------------------------------------------- génération
def generer(cv: dict, cle: str, gabarit: Path, source: Path, sortie: Path, build: Path,
            suffixe: str = "", pages_max: int = 1) -> Path:
    """PDF du design sur mesure pour une variante. Renvoie son chemin (même nom que la version design LaTeX).
    pages_max : 1 (défaut) ou 2 si elle a choisi un design sur deux pages."""
    edge = trouver_edge()
    if not edge:
        sys.exit("Microsoft Edge introuvable : il sert à imprimer le design sur mesure en PDF.")
    dossier = build / "gabarit"
    shutil.rmtree(dossier, ignore_errors=True)
    dossier.mkdir(parents=True)
    # Fichiers que le gabarit peut citer par leur seul nom : polices libres de l'appli, puis ses fichiers à elle
    # (fond sans texte, police de son graphiste : prioritaires à nom égal), puis ceux du gabarit.
    for d in (POLICES, source.parent.parent / "ressources" / "design", gabarit):
        for f in (d.iterdir() if d.is_dir() else []):
            if f.is_file() and f.suffix.lower() in FICHIERS_UTILES:
                shutil.copy2(f, dossier / f.name)
    photo = None
    if src := gc.trouver_photo(cv, source):
        photo = f"photo{src.suffix.lower()}"
        shutil.copy2(src, dossier / photo)
    modele = (gabarit / "gabarit.html").read_text(encoding="utf-8-sig")
    # Cambria imprimée par Edge : les lettres accentuées se copient mal depuis le PDF (« Contrô leuse »), ce
    # qu'un recruteur verrait en copiant une phrase. Constantia, très proche, est sans défaut (testé le 06/11).
    modele = re.sub(r"\bCambria\b", "Constantia", modele)
    ctx = construire_contexte(cv, cle, photo)
    texte, inconnus = rendre(modele, ctx)
    attendus = textes_attendus(ctx)
    if inconnus:
        print("Gabarit : noms inconnus (rien affiché) : " + ", ".join(inconnus))
    final = sortie / gc.nom_pdf(cv, cle, suffixe)
    sortie.mkdir(parents=True, exist_ok=True)
    pdf, pages = dossier / "rendu.pdf", 0
    for echelle in ECHELLES:  # une page A4 (ou deux, si choisi) : on réduit un peu si le contenu déborde
        style = f"<style>:root{{--echelle:{echelle}}}</style>"
        page = dossier / "rendu.html"
        page.write_text(re.sub(r"(<head[^>]*>)", r"\1" + style, texte, count=1, flags=re.I)
                        if re.search(r"<head", texte, re.I) else style + texte, encoding="utf-8")
        imprimer(edge, page, pdf)
        pages = compter_pages(pdf)
        absents = manquants(pdf, attendus) if pages <= pages_max else []
        if pages <= pages_max and not absents:
            break
    if pages > pages_max:
        print(f"ATTENTION : le design sur mesure fait {pages} pages, même avec un texte réduit. "
              "Raccourcissez le CV ou demandez un gabarit plus compact.")
    elif absents:  # imprimé sur une page… mais une partie du texte est cachée (hauteur fixe, overflow)
        print("ATTENTION : contenu coupé, absent du PDF : " + " ; ".join(absents[:4]))
    elif echelle < 1:  # la page est bonne ; au-delà de ~10 % de réduction, le design perd l'air de l'exemple
        print(f"Texte réduit à {round(echelle * 100)} % pour tenir sur {pages_max} page{'s' if pages_max > 1 else ''}.")
    if pages <= pages_max and (illisibles := controle_lisibilite(edge, page)):  # même si un contenu manque
        print("LISIBILITE : texte peu lisible sur un décor : " + " ; ".join(f"« {t} »" for t in illisibles[:4]))
    shutil.copy2(pdf, final)
    print(f"PDF généré : {final}")
    return final


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=".cv-booster/cv.toml", type=Path, help="fichier cv.toml")
    parser.add_argument("--variante", default="principal", help="clé de [variantes.*] dans cv.toml")
    parser.add_argument("--sortie", default="CV", type=Path, help="dossier du PDF final")
    parser.add_argument("--gabarit", type=Path, help="dossier du gabarit (défaut : gabarit/ près de cv.toml)")
    parser.add_argument("--build", type=Path, help="dossier de travail (défaut : build/ près de cv.toml)")
    args = parser.parse_args()
    gabarit = (args.gabarit or args.source.parent / "gabarit").resolve()
    if not (gabarit / "gabarit.html").is_file():
        sys.exit(f"Pas de gabarit : {gabarit / 'gabarit.html'}")
    cv = tomllib.loads(args.source.read_text(encoding="utf-8-sig"))
    generer(cv, args.variante, gabarit, args.source.resolve(), args.sortie.resolve(),
            (args.build or args.source.parent / "build").resolve())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
