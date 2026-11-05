# Annexe de la Skill format-cv : lire ses documents

Fichier annexe (étage 3) : chargé **seulement par l'importeur**, le seul agent qui lit les documents bruts.
Les autres agents travaillent sur le CV déjà structuré et n'en ont pas besoin.

## Ce qu'on trouve dans `ressources/`
- Un ancien CV, une **base d'informations** (souvent plus longue qu'un CV, avec plusieurs propositions
  d'accroche), des notes en `.txt`, une photo.
- `ressources/design/` : des CV d'exemple pour le **style**. À ignorer pour le contenu.

## Comment les lire
- Une base d'informations brute **n'est pas un CV** : ne pas la juger comme telle (un nom absent est normal).
- Texte **barré** (`~~texte~~` à l'extraction) = **écarté** volontairement : ne pas le reprendre.
- Deux sources qui se contredisent (dates, intitulés) : garder la plus récente, et le signaler.
- Une image dans `ressources/` (hors `design/`) : sans doute sa photo → `photo = "ressources/<fichier>"`.

## Outils d'extraction
- `.docx` : `scripts/extraire_docx.py <fichier>` (texte + barré en `~~…~~`).
- `.pdf` : `pdftotext -layout <fichier> -`.
- Dans l'application, l'extraction est faite pour l'agent : le texte est déjà dans son message.
