"""Applique au CV le bloc « modifications » rendu par un agent (voir la Skill format-cv).

Pourquoi : quand un agent modifie le CV avec l'outil Edit, chaque modification est un aller-retour qui renvoie
tout le contexte au modèle (mesuré : 12 allers-retours, 47 000 tokens pour appliquer une relecture). Avec ce
bloc, l'agent écrit toutes ses modifications en une seule réponse, et ce script les applique : aucun token.

Format (TOML, à la fin de la réponse de l'agent) :
    ```modifications
    [[remplacer]]
    avant = '''texte exact tel qu'il est dans cv.toml'''
    apres = '''nouveau texte'''

    [ajouter]          # facultatif : une nouvelle version, ajoutée à la fin du CV
    texte = '''
    [variantes.cle]
    titre = "…"
    '''
    ```
Chaque « avant » est remplacé partout où il apparaît (ainsi une puce citée dans les remplacements d'une
version reste cohérente). Si le CV obtenu ne se lit plus, rien n'est écrit.

Usage autonome : python appliquer.py <cv.toml> <fichier contenant le bloc>
"""

import os
import re
import sys
import tomllib
from pathlib import Path

BLOC = re.compile(r"```modifications[ \t]*\r?\n(.*?)```", re.S)


def extraire(reponse: str) -> tuple[str | None, str]:
    """(bloc, réponse sans le bloc). bloc = None s'il n'y en a pas."""
    m = BLOC.search(reponse)
    if not m:
        return None, reponse
    return m.group(1), (reponse[:m.start()] + reponse[m.end():]).strip()


def appliquer(cv: Path, bloc: str) -> dict:
    """Applique le bloc à cv.toml. Renvoie {appliquees, introuvables, ajout, erreur}."""
    rapport = {"appliquees": 0, "introuvables": [], "ajout": False, "erreur": ""}
    try:
        d = tomllib.loads(bloc)
    except tomllib.TOMLDecodeError as e:
        rapport["erreur"] = f"bloc illisible ({e})"
        return rapport
    texte = cv.read_text(encoding="utf-8-sig")
    for r in d.get("remplacer", []):
        avant, apres = str(r.get("avant", "")), str(r.get("apres", ""))
        if not avant or avant == apres:
            continue
        if avant not in texte:
            rapport["introuvables"].append(avant[:70])
            continue
        texte = texte.replace(avant, apres)
        rapport["appliquees"] += 1
    if (ajout := str(d.get("ajouter", {}).get("texte", "")).strip()):
        texte = texte.rstrip() + "\n\n" + ajout + "\n"
        rapport["ajout"] = True
    try:
        tomllib.loads(texte)  # le CV doit toujours se lire : sinon on n'écrit rien
    except tomllib.TOMLDecodeError as e:
        return {**rapport, "appliquees": 0, "ajout": False, "erreur": f"le CV ne se lirait plus ({e})"}
    tmp = cv.with_suffix(".tmp")
    tmp.write_text(texte, encoding="utf-8")
    os.replace(tmp, cv)
    return rapport


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    bloc, _ = extraire(Path(sys.argv[2]).read_text(encoding="utf-8-sig"))
    print(appliquer(Path(sys.argv[1]), bloc) if bloc else "Aucun bloc « modifications ».")
