"""Repère les marqueurs typiques d'un texte « IA » et les incohérences typographiques.

Usage : python scripts/verifier_style.py <fichier.toml | fichier.txt | fichier.md>
Sortie volontairement courte (économie de tokens) : une ligne par problème, plafonnée par catégorie.
Aucune dépendance : Python >= 3.11.
"""

import re
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

ICI = Path(__file__).resolve().parent.parent
PLAFOND = 6          # nb max de lignes affichées par catégorie
PUCE_MAX_MOTS = 22   # au-delà, une puce est trop longue

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
TRIPLET = re.compile(r"\b[\w’'-]+, [\w’'-]+ et [\w’'-]+\b")
MAJ_SANS_ACCENT = re.compile(r"\bE[cdlqtv][a-zàâçéèêëîïôûù]+")
MONTANT_COLLE = re.compile(r"\d+[MkK]?€")


def charger_lexique() -> list[re.Pattern]:
    lignes = (ICI / "lexique-ia.txt").read_text(encoding="utf-8-sig").splitlines()
    return [re.compile(l, re.I) for l in lignes if l.strip() and not l.startswith("#")]


def textes(fichier: Path) -> list[tuple[str, str]]:
    """Liste de (emplacement, texte). Pour un TOML : seulement les valeurs texte."""
    if fichier.suffix == ".toml":
        res = []

        def parcourir(x, chemin):
            if isinstance(x, str):
                res.append((chemin, x))
            elif isinstance(x, dict):
                for k, v in x.items():
                    parcourir(v, f"{chemin}.{k}" if chemin else k)
            elif isinstance(x, list):
                for i, v in enumerate(x):
                    parcourir(v, f"{chemin}[{i}]")

        parcourir(tomllib.loads(fichier.read_text(encoding="utf-8-sig")), "")
        return res
    return [(f"l.{i}", t) for i, t in enumerate(fichier.read_text(encoding="utf-8-sig").splitlines(), 1) if t.strip()]


def analyser(items: list[tuple[str, str]]) -> dict[str, list[str]]:
    lexique = charger_lexique()
    pb = defaultdict(list)
    tout = " ".join(t for _, t in items)

    for ou, t in items:
        for motif in lexique:
            if m := motif.search(t):
                pb["Vocabulaire IA"].append(f"{ou} : « {m.group(0)} »")
        if "—" in t:
            pb["Tiret cadratin dans le texte"].append(f"{ou} : « …{t[max(0, t.index('—') - 25):t.index('—') + 15]}… »")
        if EMOJI.search(t) or "!" in t:
            pb["Émoji / exclamation"].append(ou)
        for m in MAJ_SANS_ACCENT.finditer(t):
            pb["Majuscule sans accent"].append(f"{ou} : « {m.group(0)} »")
        if MONTANT_COLLE.search(t):
            pb["Montant sans espace (25 M€)"].append(f"{ou} : « {MONTANT_COLLE.search(t).group(0)} »")
        if ".points[" in ou and len(t.split()) > PUCE_MAX_MOTS:
            pb["Puce trop longue"].append(f"{ou} : {len(t.split())} mots")

    if "'" in tout and "’" in tout:
        n1, n2 = tout.count("'"), tout.count("’")
        pb["Apostrophes mélangées"].append(f"{n1} droites (') et {n2} typographiques (’) : en choisir une")

    triplets = [m.group(0) for _, t in items for m in TRIPLET.finditer(t)]
    if len(triplets) >= 3:
        pb["Énumérations par trois (à varier)"].append(f"{len(triplets)} : " + " / ".join(triplets[:4]))

    # Séries de puces commençant par un nom en -tion dans une même expérience
    series = defaultdict(list)
    for ou, t in items:
        if ".points[" in ou:
            series[ou.split(".points[")[0]].append(t.split()[0] if t.split() else "")
    for exp, premiers in series.items():
        n = sum(1 for p in premiers if p.lower().endswith(("tion", "sion", "ment")))
        if n >= 4:
            pb["Série de puces en -tion/-ment"].append(f"{exp} : {n}/{len(premiers)} puces")

    return pb


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    pb = analyser(textes(Path(sys.argv[1])))
    if not pb:
        print("OK : aucun marqueur détecté.")
        return
    for cat, lignes in pb.items():
        print(f"## {cat} ({len(lignes)})")
        for l in lignes[:PLAFOND]:
            print(f"- {l}")
        if len(lignes) > PLAFOND:
            print(f"- … et {len(lignes) - PLAFOND} autre(s)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
