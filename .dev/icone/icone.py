"""Compiles .dev/icone/icone.tex into .app/icone.png (256 px) and .app/icone.ico (multi-size).

Usage: python .dev/icone/icone.py    (needs pdflatex and pdftocairo, shipped with MiKTeX)
The .ico embeds PNGs (a format Windows accepts since Vista): no Python dependency.
pdftocairo -transp: TRANSPARENT corners (pdftoppm puts the image on white, which shows in dark mode).
"""

import struct
import subprocess
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
TAILLES = [256, 64, 48, 32, 16]

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={tmp}",
                    str(Path(__file__).with_name("icone.tex"))], check=True, capture_output=True)
    pngs = []
    for t in TAILLES:
        subprocess.run(["pdftocairo", "-png", "-transp", "-singlefile", "-scale-to-x", str(t), "-scale-to-y", str(t),
                        str(tmp / "icone.pdf"), str(tmp / f"i{t}")], check=True)
        pngs.append((t, (tmp / f"i{t}.png").read_bytes()))

(RACINE / ".app" / "icone.png").write_bytes(pngs[0][1])
entete = struct.pack("<HHH", 0, 1, len(pngs))
decalage = 6 + 16 * len(pngs)
entrees, donnees = b"", b""
for t, png in pngs:
    entrees += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(png), decalage + len(donnees))
    donnees += png
(RACINE / ".app" / "icone.ico").write_bytes(entete + entrees + donnees)
print("Icône générée : .app/icone.ico, .app/icone.png")
