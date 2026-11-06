# Annexe : gabarit HTML du design sur mesure

Le design sur mesure est **un seul fichier** : `.cv-booster/gabarit/gabarit.html` (HTML + CSS dans `<style>`).
L'application le remplit avec le contenu de `cv.toml` (script, sans IA), puis Microsoft Edge l'imprime en
PDF A4. La version ATS est produite à part : ne vous en occupez pas.

## Règles de la page (sinon le PDF est faux)
- `@page { size: A4; margin: 0; }`, `html, body { margin: 0; }` et, pour que les fonds s'impriment :
  `* { -webkit-print-color-adjust: exact; print-color-adjust: exact; box-sizing: border-box; }`.
- Une page = `<div class="page">` de `width: 210mm; min-height: 297mm; position: relative;`.
  Les décors vont dans un calque `position: absolute; inset: 0; height: 297mm; z-index: 0;` derrière le
  contenu (`position: relative; z-index: 1;`).
- Le contenu **s'écoule** : jamais de hauteur fixe ni de `overflow: hidden` sur un bloc de texte (un texte
  coupé ne se verrait pas). L'application réduit le texte si la page déborde.
- **Toutes** les tailles de police et les espacements verticaux en `calc(10pt * var(--echelle, 1))`.
  Texte courant : 9 à 11 pt à l'échelle 1.
- Repère de place : une page fait 297 mm ; une ligne de texte à 9,5 pt avec un interligne de 1,35 prend
  environ 4,5 mm, soit environ 60 lignes par colonne une fois les marges et le nom ôtés. Une puce longue
  tient sur 2 lignes dans une colonne étroite. L'application réduit au plus de 20 % : au-delà, c'est 2 pages.
- Polices, par ordre de préférence : 1) celle qu'elle a fournie (listée dans le message) ; 2) la plus proche
  de l'exemple parmi les polices libres de l'application ci-dessous ; 3) une police de Windows (Georgia,
  Constantia, Palatino Linotype, Segoe UI, Candara…). Pas Cambria : ses accents se copient mal depuis le
  PDF. Jamais de police en ligne (le PDF doit se générer sans Internet).
  Déclaration (toutes les graisses dans un seul fichier) :
  `@font-face { font-family: "Lora"; src: url("Lora.ttf"); font-weight: 400 700; }`

| Fichier | Caractère | Pour |
|---|---|---|
| `Comfortaa.ttf` (300-700) | arrondie, géométrique, douce | noms, titres « créatifs » |
| `Quicksand.ttf` (300-700) | arrondie, fine, moderne | noms, titres, coordonnées |
| `JosefinSans.ttf` (100-700) | géométrique, élégante, années 1920 | noms en capitales, titres |
| `Raleway.ttf` (100-900) | sans empattement élégante | titres et texte courant |
| `PlayfairDisplay.ttf` (400-900) | à empattement, contrastée, chic | noms et titres de rubriques |
| `Lora.ttf`, `Lora-Italique.ttf` (400-700) | à empattement, lisible | texte courant, dates en italique |
- Fichiers cités par leur **seul nom** (`url("fond.png")`) : ceux de `ressources/design/` et ceux de
  `.cv-booster/gabarit/`.

## Finitions : ce qui fait un design « propre »
- Reprenez les détails typographiques de l'exemple : listes numérotées (`{{numero}}.`) ou à puces, texte
  centré ou aligné, capitales, graisses, couleurs des dates et des lieux, filets.
- De l'air : au moins 5 mm entre deux rubriques, un interligne d'au moins 1,3, des marges comme l'exemple.
  Un CV aéré mais tassé à la fin est moins propre qu'un CV régulier : répartissez l'espace.
- Deux pages (seulement si elle l'a demandé : `pages_sur_mesure = 2` dans `[page]` de `.cv-booster/design.toml`) :
  le contenu continue sur la 2e page ; ajoutez un décor discret à `top: 297mm` pour la 2e page et évitez de
  couper une expérience en deux (`break-inside: avoid` sur chaque bloc).

## Deux modes
**Fond fourni (rendu identique)** : une image SANS texte est le fond de son design (fichier à elle). Mettez-la
en pleine page, sans redessiner aucun décor :
`<img src="fond.png" alt="" style="position:absolute; left:0; top:0; width:210mm; height:297mm; object-fit:cover; z-index:0">`
puis posez le texte exactement dans les zones de l'exemple (positions mesurées en mm sur l'image du CV fini),
la photo dans le cercle prévu (`border-radius: 50%`), avec la police la plus proche.

**Image seule (très proche)** : mesurez d'abord l'exemple, en pourcentage de la largeur et de la hauteur de
la page : limites de chaque zone colorée, centre et diamètre de la photo, place du nom, début de chaque
colonne. Reproduisez ces proportions à l'identique (210 × 297 mm), puis habillez chaque zone avec la forme
de la bibliothèque dont la silhouette est la plus proche, à la même place, à la même taille et avec le même
chevauchement des bords de page. Les illustrations elles-mêmes ne se décalquent pas : ce sont nos formes.

## Décors : les vôtres, ou ceux qu'elle fournit
- Reproduisez la **disposition**, les **couleurs**, la **typographie** et l'esprit des formes de l'exemple.
- Les formes décoratives (taches, courbes, cadres, dégradés) sont **dessinées par vous** en CSS ou en SVG
  dans le fichier. Ne recopiez pas une illustration ou une image de l'exemple, et ne reprenez jamais son texte.
- **Formes organiques prêtes à l'emploi** (courbes lisses, sans angle) : composez les décors avec elles au
  lieu de tracer des courbes à la main. Chaque forme se place, s'étire (`preserveAspectRatio="none"`), se
  tourne (`transform: rotate(-12deg)`), se retourne (`scale(-1, 1)`), se superpose et peut déborder du bord
  de la page pour l'effet « posé » :
  `<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="position:absolute; left:-18mm; top:-12mm; width:120mm; height:150mm"><path fill="#EBCAD5" d="…"/></svg>`

| Forme | Tracé (`d`) |
|---|---|
| tache ronde | `M96.7 50C96.5 62.7 83.2 80.9 71.6 87.4C60 94 38.5 95.6 27.3 89.4C16 83.1 3.9 62.9 4.1 50C4.2 37.1 16.6 18.4 28 11.9C39.4 5.5 60.9 4.9 72.4 11.2C83.8 17.6 96.8 37.3 96.7 50Z` |
| tache allongée | `M98.3 50C98 57.9 91.4 67.4 83.4 72.9C75.3 78.4 61.1 83 50 83C38.9 83 25.2 78.3 16.8 72.8C8.4 67.3-.2 57.7-.3 50C-.4 42.3 7.9 32 16.3 26.8C24.7 21.6 38.5 19 50 18.8C61.5 18.6 77.5 20.4 85.5 25.6C93.6 30.8 98.7 42.1 98.3 50Z` |
| tache haute | `M85.6 50C85.3 61 78.6 74 72.7 82C66.7 90 58 97.3 50 97.8C42 98.4 30.5 93.4 24.9 85.4C19.4 77.4 16.5 61.6 16.7 50C16.8 38.4 20.3 23.7 25.9 15.9C31.4 8.1 41.9 3.2 50 3.1C58.1 3.1 68.4 7.9 74.3 15.7C80.2 23.5 85.9 39 85.6 50Z` |
| galet | `M96.8 50C96.1 61 86.9 74.2 77.5 80.7C68 87.2 51.2 91.4 40 89.1C28.8 86.9 15.1 76.4 10.2 67.1C5.3 57.8 5.9 42.9 10.7 33.1C15.6 23.4 27.6 11.5 39.3 8.4C51.1 5.3 71.9 7.9 81.5 14.8C91.1 21.7 97.5 39 96.8 50Z` |
| angle (coin haut droit) | `M14 0C15 4 15.7 16.3 20 24C24.3 31.7 32 40.5 40 46C48 51.5 58 54.7 68 57C78 59.3 94.7 59.5 100 60L100 0Z` |
| bandeau à bord ondulé | `M0 0L100 0L100 58C95 60.2 80.7 71 70 71C59.3 71 47.7 58.3 36 58C24.3 57.7 6 67.2 0 69Z` |

- Une forme qui n'est pas dans la liste : seulement des courbes de Bézier lisses (C ou S), jamais de segment
  droit visible ni d'angle, sauf contre le bord de la page.
- **Lisibilité d'abord** : un décor ne passe jamais sous du texte, sauf un bandeau prévu pour lui (texte clair
  sur fond foncé, ou l'inverse). Son contenu est plus long que celui de l'exemple : dimensionnez le bandeau du
  nom pour qu'il s'arrête au moins 6 mm au-dessus de la première rubrique, et placez les rubriques du bas de
  page dans le flux, pas sur un décor de hauteur fixe.
- Un fichier fourni par la personne (« fond sans texte », décor, logo, police : listés dans le message) est
  le sien : utilisez-le tel quel, par exemple `background: url("fond.png") center / cover;`.

## Contenu : tout, depuis les variables (rien d'écrit en dur)
Affichez **tout** le CV : chaque expérience et chaque point, compétences (domaine ET détail ET outils),
formations, langues, intérêts. Ne retirez jamais un champ pour gagner de la place : l'application le
détecte comme un contenu coupé.
Les titres de rubriques viennent de `lib` (le même gabarit sert au CV anglais).

| Variable | Contenu |
|---|---|
| `{{nom}}`, `{{prenom}}`, `{{nom_famille}}` | nom complet, et en deux morceaux (nom sur deux lignes) |
| `{{titre}}`, `{{accroche}}` | titre et accroche de la version |
| `{{#photo}}<img src="{{photo}}">{{/photo}}{{^photo}}…{{/photo}}` | sa photo, sinon une silhouette (SVG) |
| `{{#contacts}}{{libelle}} {{valeur}}{{/contacts}}` | `type` = telephone, email, linkedin, ville, permis |
| `{{identite.email}}`, `{{identite.telephone}}`… | un contact précis (vide s'il manque) |
| `{{#experiences}}` : `poste`, `entreprise`, `dates`, `lieu`, `{{#points}}{{.}}{{/points}}` | expériences |
| `{{#competences}}` : `domaine`, `detail`, `outils_texte` (ou `{{#outils}}{{.}}{{/outils}}`) | compétences |
| `{{#formations}}` : `diplome`, `ecole`, `annees` | formations |
| `{{#langues}}` : `langue`, `niveau` | langues |
| `{{#niveaux}}` : `nom`, `mention`, `pourcent` (0-100), `{{#pastilles}}{{#pleine}}…{{/pleine}}{{/pastilles}}` | jauges (si présentes) |
| `{{#interets}}{{.}}{{/interets}}`, `{{#forces}}{{.}}{{/forces}}` | centres d'intérêt, qualités (une ligne chacun) |
| `{{interets_texte}}`, `{{forces_texte}}` | les mêmes sur une ligne, déjà séparés par « · » |
| `numero` (1, 2…), `{{^dernier}}…{{/dernier}}` | dans chaque liste de blocs : numérotation, séparateur sauf après le dernier |

Points numérotés (1., 2.…) : `<ol>{{#points}}<li>{{.}}</li>{{/points}}</ol>`, les numéros sont automatiques
(style avec `li::marker`). Jamais `{{numero}}` dans `{{#points}}` : ce serait le numéro de l'expérience.
L'application vérifie que tout le texte se lit dans le PDF : un contenu caché (hauteur fixe, `overflow`)
est signalé comme coupé.
| `{{lib.profil}}`, `lib.experiences`, `lib.competences`, `lib.formations`, `lib.langues`, `lib.interets`, `lib.qualites`, `lib.contact` | titres de rubriques |

Syntaxe : `{{x}}` affiche (échappé), `{{#x}}…{{/x}}` répète une liste ou affiche si présent,
`{{^x}}…{{/x}}` affiche si absent.
**Titre d'une rubrique facultative** : `{{#avec_interets}}<h2>{{lib.interets}}</h2>…{{/avec_interets}}`
(de même `avec_niveaux`, `avec_forces`, `avec_langues`, `avec_competences`, `avec_formations`,
`avec_experiences`, `avec_contacts`). Jamais `{{#interets}}` autour d'un titre : il serait répété pour
chaque élément.

## Squelette
```html
<!doctype html><html lang="{{langue}}"><head><meta charset="utf-8"><style>
@page { size: A4; margin: 0; } html, body { margin: 0; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page { width: 210mm; min-height: 297mm; position: relative; font: calc(10pt * var(--echelle, 1)) Calibri, sans-serif; }
.decor { position: absolute; inset: 0; height: 297mm; z-index: 0; }
.contenu { position: relative; z-index: 1; padding: 14mm; }
</style></head><body><div class="page">
<svg class="decor" viewBox="0 0 210 297" preserveAspectRatio="none"><!-- vos formes --></svg>
<div class="contenu"><h1>{{nom}}</h1><p>{{titre}}</p>…</div>
</div></body></html>
```
