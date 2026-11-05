"""Exporte une version du CV en Word (.docx), pour les cabinets et sites qui exigent ce format.

Usage :
    python scripts/generer_docx.py --source .cv-booster/cv.toml --variante <clé> --sortie CV

Mise en page volontairement simple, sur une colonne (lisible par les logiciels de tri) ; titres dans la
couleur d'accent du design. Même nom que le PDF, en .docx. Aucune dépendance : un .docx est un zip de XML.
"""

import argparse
import sys
import tomllib
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generer_cv as cvgen  # noqa: E402  (mêmes textes par langue, variantes, nommage et couleurs)

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def run(texte: str, gras: bool = False, couleur: str = "", taille: int = 0) -> str:
    props = ("<w:b/>" if gras else "") + (f'<w:color w:val="{couleur}"/>' if couleur else "") + \
            (f'<w:sz w:val="{taille}"/>' if taille else "")
    return f'<w:r>{f"<w:rPr>{props}</w:rPr>" if props else ""}<w:t xml:space="preserve">{escape(texte)}</w:t></w:r>'


def para(contenu: str, style: str = "", puce: bool = False, apres: int | None = None) -> str:
    p = (f'<w:pStyle w:val="{style}"/>' if style else "") + \
        ('<w:ind w:left="360" w:hanging="240"/>' if puce else "") + \
        (f'<w:spacing w:after="{apres}"/>' if apres is not None else "")
    return f"<w:p>{f'<w:pPr>{p}</w:pPr>' if p else ''}{contenu}</w:p>"


def corps(cv: dict, variante: dict, accent: str) -> str:
    L = cvgen.L
    ident = cv["identite"]
    contacts = [ident[k] for k, _ in cvgen.CONTACTS if ident.get(k)]
    x = [para(run(ident.get("nom", ""), gras=True, taille=40), apres=0),
         para(run(variante.get("titre", ""), couleur=accent, taille=26), apres=60),
         para(run(" · ".join(contacts), couleur="555555"), apres=120)]
    rubrique = lambda t: para(run(t.upper(), gras=True, couleur=accent), "Rubrique")  # noqa: E731
    x += [rubrique(L["profil"]), para(run(variante.get("accroche", "")))]
    x.append(rubrique(L["experiences"]))
    for e in cv.get("experiences", []):
        x.append(para(run(e.get("poste", ""), gras=True) + run(f", {e.get('entreprise', '')}"), apres=0))
        x.append(para(run(" · ".join(v for v in (e.get("dates", ""), e.get("lieu", "")) if v), couleur="555555"),
                      apres=40))
        x += [para(run("•  " + p), puce=True, apres=20) for p in e.get("points", [])]
        x.append(para("", apres=40))
    x.append(rubrique(L["competences"]))
    for c in cv.get("competences", []):
        outils = f" ({', '.join(c['outils'])})" if c.get("outils") else ""
        x.append(para(run(f"{c.get('domaine', '')} : ", gras=True) + run(c.get("detail", "") + outils), apres=40))
    x.append(rubrique(L["formations"]))
    for f in cv.get("formations", []):
        x.append(para(run(f.get("diplome", ""), gras=True) + run(f", {f.get('ecole', '')}") +
                      run(f"  {f.get('annees', '')}", couleur="555555"), apres=40))
    if cv.get("langues"):
        x.append(rubrique(L["langues"]))
        x.append(para(run(" · ".join(f"{l['langue']} ({l['niveau']})" for l in cv["langues"]))))
    divers = cv.get("divers", {})
    for cle, libelle in (("forces", L["qualites"]), ("interets", L["interets"])):
        if divers.get(cle):
            x += [rubrique(libelle), para(run(" · ".join(divers[cle])))]
    marge = 1000  # ~1,8 cm
    x.append(f'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="{marge}" w:right="{marge}" '
             f'w:bottom="{marge}" w:left="{marge}" w:header="0" w:footer="0" w:gutter="0"/></w:sectPr>')
    return "".join(x)


def styles(accent: str) -> str:
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
            '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
            '<w:sz w:val="21"/><w:lang w:val="fr-FR"/></w:rPr></w:rPrDefault>'
            '<w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
            '</w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
            '<w:style w:type="paragraph" w:styleId="Rubrique"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
            '<w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="220" w:after="80"/>'
            f'<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="{accent}"/></w:pBdr>'
            '<w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:sz w:val="23"/></w:rPr></w:style></w:styles>')


def ecrire_docx(chemin: Path, cv: dict, variante: dict, accent: str) -> None:
    nom = escape(cv["identite"].get("nom", ""))
    maintenant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fichiers = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.'
            'openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.'
            'openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" '
            'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.'
            'openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.'
            'org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="r2" '
            'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
            'Target="docProps/core.xml"/></Relationships>',
        "word/_rels/document.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://'
            'schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "word/styles.xml": styles(accent),
        "word/document.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>'
            f"{corps(cv, variante, accent)}</w:body></w:document>",
        "docProps/core.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp='
            '"http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/'
            'elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-'
            f'instance"><dc:title>CV {nom}</dc:title><dc:creator>{nom}</dc:creator><dcterms:created xsi:type="dcterms:'
            f'W3CDTF">{maintenant}</dcterms:created></cp:coreProperties>',
    }
    tmp = chemin.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for nom_f, contenu in fichiers.items():
            z.writestr(nom_f, contenu)
    tmp.replace(chemin)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default=".cv-booster/cv.toml", type=Path)
    p.add_argument("--variante", required=True)
    p.add_argument("--sortie", default="CV", type=Path)
    args = p.parse_args()
    cv = tomllib.loads(args.source.read_text(encoding="utf-8-sig"))
    cvgen.choisir_langue(cv)
    if args.variante not in cv.get("variantes", {}):
        sys.exit(f"Variante inconnue « {args.variante} ».")
    variante = cv["variantes"][args.variante]
    accent = cvgen.valider_design(cvgen.charger_design(None, args.source))["accent"]
    args.sortie.mkdir(parents=True, exist_ok=True)
    final = args.sortie.resolve() / cvgen.nom_pdf(cv, args.variante).replace(".pdf", ".docx")
    ecrire_docx(final, cvgen.appliquer_variante(cv, variante), variante, accent)
    print(f"Word généré : {final}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
