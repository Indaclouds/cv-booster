# CV Booster

Application Windows qui aide à construire, relire, adapter et mettre en page un CV, avec des agents IA
(Claude Code) et un abonnement Claude Pro, sans API ni clé. Pensée pour une personne **non technicienne**
qui veut aussi **comprendre l'agentique** : l'onglet *Coulisses* montre les agents et les Skills, et permet
d'en créer.

**Télécharger** : [dernière version](https://github.com/Indaclouds/cv-booster/releases/latest)
(`Installer-CV-Booster.exe`, Windows 10/11, sans droits administrateur).

## Ce qu'elle fait
- **Créer le CV** à partir de documents en vrac (ancien CV, notes, photo), sans rien inventer.
- **Relire**, **reformuler**, **adapter à une offre** (une version par offre), **veille marché** (web),
  **design** d'après un exemple.
- **Lettre de motivation** (PDF automatique) et **préparation d'entretien**.
- **Correspondance annonce ↔ CV** : mots-clés présents ou absents, calculés par un script (0 token).
- **CV en anglais** (vraie traduction, même design), **export Word**, **message de relance**.
- **Suivi des candidatures**, **versions précédentes du CV**, **sauvegarde** de ses données, **mises à jour**
  automatiques, **consommation** du forfait, **signaler un problème** (diagnostic sans données personnelles).
- Deux PDF par version : un avec le design, un « ATS » (une colonne, lisible par les logiciels de tri).

## Architecture
| Dossier | Rôle |
|---|---|
| `.claude/agents/` | 1 fichier = 1 agent (consignes, outils, modèle, Skills utilisées) |
| `.claude/skills/` | Savoir-faire partagé : `format-cv`, `regles-ecriture`, `mise-en-page`, `lettre-motivation` |
| `.app/` | L'application : `serveur.py` (chef d'orchestre), `fenetre.py` (pywebview), `index.html` |
| `.dev/` | Outils de développement : `installeur/`, `guide/`, `icone/`, `tests/` (données fictives), `sandbox/` (test sur un Windows neuf) |

Principe : tout ce qui est mécanique (lire les documents, vérifier le style, générer les PDF) est fait par
des scripts ; l'IA ne sert qu'au jugement. Le serveur prépare tout le contexte d'avance pour qu'un agent
travaille en un seul aller-retour (économie de tokens). Détails : [`.claude/CLAUDE.md`](.claude/CLAUDE.md).

## Données personnelles
Aucune donnée personnelle n'est dans le dépôt : le CV, les documents et le suivi des candidatures restent
sur l'ordinateur de la personne (`Documents\CV Booster`, exclus par `.gitignore`). L'appli ne contacte que
Claude (avec le compte de la personne) et GitHub (lecture de `version.json` pour les mises à jour, rien
n'est envoyé). Le fichier « Signaler un problème » ne contient
ni le CV ni les documents, et masque le nom de session et les adresses e-mail. Les exemples et les tests
n'utilisent que des personnes fictives.

## Licence
[MIT](LICENSE). Composants inclus : police Fraunces (SIL Open Font License 1.1, [`.app/vendor/OFL.txt`](.app/vendor/OFL.txt)),
marked (MIT) et DOMPurify (Apache 2.0 ou MPL 2.0), avec leur mention de licence en tête de fichier.
