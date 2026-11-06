---
name: mise-en-page
description: Transformer le CV (cv.toml) en PDF avec LaTeX, et régler son style (design.toml - couleurs, police, colonnes, barres de niveau, icônes, QR code). Toujours une version « ATS » en plus. Utilisée par l'agent designer.
---

# Skill : mise en page

La forme est **entièrement** dans `modeles/modele.tex`. Personne n'écrit de LaTeX pour le contenu :
le script assemble le contenu (`cv.toml`) et le style (`design.toml`).

## Générer le PDF
`python scripts/generer_cv.py --variante <clé>` (depuis le dossier du projet)
- Produit **toujours deux PDF** dans `CV/` :
  - `CV_Prenom_Nom_Titre.pdf` : avec son design, pour un recruteur (e-mail, impression) ;
  - `…_ATS.pdf` : une colonne, sans décorations, pour les sites d'emploi (les logiciels de tri, ou ATS,
    lisent mal les colonnes et les icônes).
- « ATTENTION : 2 pages » → proposer 2 ou 3 coupes de contenu. Ne jamais tricher sur la police ou les marges.
- Sans pdflatex : `--tex-seul`, puis compiler sur overleaf.com.
- Dans l'application, c'est le bouton « Générer » : aucun agent n'est nécessaire.

## Régler le style : `.cv-booster/design.toml`
Écrire **seulement les réglages qui changent**. Réglages et valeurs permises : annexe
`modeles/design-defaut.toml`, chargée par le designer (le script refuse toute autre valeur et dit lesquelles
sont permises).

| Élément | Réglages |
|---|---|
| Couleurs | `accent` (titres, filets, barres), `secondaire`, `entete_fond` (bandeau du nom) |
| Police | 5 modernes (helvetica, lato, roboto, fira, opensans), 3 classiques (palatino, charter, garamond) |
| Mise en page | `une_colonne` ou `deux_colonnes` (barre latérale : photo, compétences, langues, contact) |
| En-tête | alignement, taille et majuscules du nom, bandeau, côté de la photo, `photo_provisoire` |
| Décorations | `icones` devant les contacts, `qrcode` (vrai lien LinkedIn ou e-mail) |
| Rubriques | trait dessous, fond de couleur, trait à gauche, ou rien |
| Compétences | `liste` ou `barres` (barres : il faut des `[[niveaux]]` dans le CV) |

Ces réglages ne savent PAS faire : photo ronde ou détourée, fond de page coloré, formes décoratives, cadres.
Pour cela : le design sur mesure (agent maquettiste, gabarit HTML rempli par `scripts/generer_html.py`,
annexe `gabarit-html.md`), activé par l'application (`[page] sur_mesure`).
