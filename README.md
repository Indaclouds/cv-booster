# CV Booster

Application Windows qui aide à construire, relire, adapter et mettre en page un CV, avec des agents IA
(Claude Code) et un abonnement Claude Pro, sans API ni clé. Pensée pour une personne **non technicienne**
qui veut aussi **comprendre l'agentique** : l'onglet *Coulisses* montre les agents et les Skills, et permet
d'en créer.

## Ce qu'elle fait
- **Créer le CV** à partir de documents en vrac (ancien CV, notes, photo), sans rien inventer.
- **Relire**, **reformuler**, **adapter à une offre** (une version par offre), **veille marché** (web),
  **design** d'après un exemple.
- **Lettre de motivation** (PDF automatique) et **préparation d'entretien**.
- **Correspondance annonce ↔ CV** : mots-clés présents ou absents, calculés par un script (0 token).
- **Suivi des candidatures**, **versions précédentes du CV**, **mises à jour** automatiques.
- Deux PDF par version : un avec le design, un « ATS » (une colonne, lisible par les logiciels de tri).

## Architecture
| Dossier | Rôle |
|---|---|
| `.claude/agents/` | 1 fichier = 1 agent (consignes, outils, modèle, Skills utilisées) |
| `.claude/skills/` | Savoir-faire partagé : `format-cv`, `regles-ecriture`, `mise-en-page`, `lettre-motivation` |
| `.app/` | L'application : `serveur.py` (chef d'orchestre), `fenetre.py` (pywebview), `index.html` |
| `.dev/` | Outils de développement : installeur, guide, icône |

Principe : tout ce qui est mécanique (lire les documents, vérifier le style, générer les PDF) est fait par
des scripts ; l'IA ne sert qu'au jugement. Le serveur prépare tout le contexte d'avance pour qu'un agent
travaille en un seul aller-retour (économie de tokens). Détails : [`.claude/CLAUDE.md`](.claude/CLAUDE.md).

