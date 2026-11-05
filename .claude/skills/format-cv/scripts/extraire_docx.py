"""Extrait le texte d'un .docx sans dépendance, en marquant le barré ~~ainsi~~.

Usage : python scripts/extraire_docx.py <fichier.docx>
Le barré compte : dans une base d'informations il signifie « écarté ».
"""

import re
import sys
import zipfile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extraire(chemin: str) -> str:
    import xml.etree.ElementTree as ET

    racine = ET.fromstring(zipfile.ZipFile(chemin).read("word/document.xml"))
    lignes = []
    for p in racine.iter(f"{W}p"):
        morceaux = []
        for r in p.iter(f"{W}r"):
            rpr = r.find(f"{W}rPr")
            s = rpr.find(f"{W}strike") if rpr is not None else None
            barre = s is not None and s.get(f"{W}val", "true") not in ("0", "false")
            texte = "".join(
                (t.text or "") if t.tag == f"{W}t" else ("\t" if t.tag == f"{W}tab" else " / ")
                for t in r if t.tag in (f"{W}t", f"{W}tab", f"{W}br")
            )
            if texte:
                morceaux.append(f"~~{texte}~~" if barre and texte.strip() else texte)
        ligne = re.sub(r"~~~~", "", "".join(morceaux)).strip()
        if ligne:
            lignes.append(ligne)
    return "\n".join(lignes)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    print(extraire(sys.argv[1]))
