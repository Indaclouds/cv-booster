---
name: format-cv
description: Structure du CV de CV Booster (fichier cv.toml), emplacement des fichiers, et lecture des documents fournis (ressources, texte barré). Utilisée par tous les agents : c'est le socle commun.
---

# Skill : format du CV

Tous les agents travaillent sur **un seul fichier** : `.cv-booster/cv.toml`. Il contient le **contenu** du CV,
jamais sa mise en forme (gérée par la Skill `mise-en-page`).

## Où sont les fichiers
| Dossier | Rôle |
|---|---|
| `ressources/` | **Entrée** : tout ce que la personne dépose (anciens CV, notes, photo). |
| `ressources/design/` | Exemples de CV pour le **style** uniquement, jamais pour le contenu. |
| `.cv-booster/cv.toml` | Le CV (source de vérité). |
| `.cv-booster/design.toml` | Les réglages de style. |
| `.cv-booster/tendances/` | Les fiches de veille marché. |
| `.cv-booster/lettres/` | Les lettres de motivation (une par entreprise, Skill `lettre-motivation`). |
| `.cv-booster/offres/` | Les annonces collées dans l'application. |
| `.cv-booster/historique/` | Les versions précédentes du CV (rangées par l'application, ne pas y toucher). |
| `CV/` | **Sortie** : les PDF (CV et lettres). |

## Les blocs du CV
- `[identite]` : nom, contacts, photo (facultative).
- `[variantes.<clé>]` : une **version** du CV = un titre + une accroche. Une par type de poste, ou par offre.
  Une version adaptée à une offre peut aussi avoir ses propres `remplacements` (puce d'origine → puce adaptée)
  et son `ordre_competences`, **sans toucher au contenu commun**.
- `[[experiences]]`, `[[competences]]`, `[[formations]]`, `[[langues]]` : le contenu commun.
- `[[niveaux]]` (facultatif) : barres de niveau. `mention` = un fait (durée), `niveau` 1 à 5 = donné par la personne.
- `[divers]` : qualités, centres d'intérêt. **Toujours à la fin** : en TOML, une clé écrite après un bloc
  `[[...]]` appartient à ce bloc.

## Fichiers annexes (chargés seulement par les agents qui en ont besoin)
| Annexe | Contenu | Chargée par |
|---|---|---|
| `lecture-documents.md` | Comment lire ses documents bruts (barré, contradictions, photo) | importeur |
| `cv-exemple.toml` | La structure complète, commentée | importeur, adaptateur-offre |

## Scripts (lancés par l'application, sans IA)
- `scripts/extraire_docx.py` : texte d'un .docx, barré compris.
- `scripts/correspondance.py` : mots-clés d'une annonce présents ou non dans le CV (indicatif). Son résultat
  est fourni à l'adaptateur d'offre ; la personne le voit aussi avec « Vérifier la correspondance ».

## Règles de modification
- **Ne rien inventer** : aucun chiffre, outil ou résultat absent de ses documents. Demander.
- **La personne décide** : ne modifier `cv.toml` qu'après sa validation (sauf l'import, qui le crée).
- Répondre **court** : seulement les changements (avant → après), jamais le CV entier.
