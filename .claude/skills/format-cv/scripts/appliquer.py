"""Applies to the CV the "modifications" block returned by an agent (see the format-cv Skill).

Why: when an agent edits the CV with the Edit tool, each change is a round trip that sends
the whole context back to the model (measured: 12 round trips, 47,000 tokens to apply one review). With this
block, the agent writes all its changes in a single reply, and this script applies them: no tokens.

Format (TOML, at the end of the agent's reply):
    ```modifications
    [[remplacer]]
    avant = '''exact text as it appears in cv.toml'''
    apres = '''new text'''

    [ajouter]          # optional: a new version, appended to the end of the CV
    texte = '''
    [variantes.cle]
    titre = "…"
    '''
    ```
Each "avant" is replaced everywhere it appears (so a bullet quoted in a version's replacements
stays consistent). If the resulting CV no longer parses, nothing is written.

Standalone usage: python appliquer.py <cv.toml> <file containing the block>
"""

import os
import re
import sys
import tomllib
from pathlib import Path

BLOC = re.compile(r"```modifications[ \t]*\r?\n(.*?)```", re.S)


def extraire(reponse: str) -> tuple[str | None, str]:
    """(bloc, reply without the block). bloc = None if there is none."""
    m = BLOC.search(reponse)
    if not m:
        return None, reponse
    return m.group(1), (reponse[:m.start()] + reponse[m.end():]).strip()


def appliquer(cv: Path, bloc: str) -> dict:
    """Applies the block to cv.toml. Returns {appliquees, introuvables, ajout, erreur}."""
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
        tomllib.loads(texte)  # the CV must always parse: otherwise write nothing
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
