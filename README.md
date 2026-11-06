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
  **design** d'après un exemple, ou **design sur mesure** : une mise en page fidèle à son propre design
  (graphiste, modèle acheté), remplie automatiquement avec le CV et imprimée par Edge.
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

## Développer
Prérequis : Windows 10/11, Python 3.13, [MiKTeX](https://miktex.org), [Claude Code](https://claude.com/claude-code)
connecté à un compte Claude.

```
pip install pywebview --target .app/lib
pythonw .app/lancer.pyw
```
En développement, les données (`ressources/`, `CV/`, `.cv-booster/`) sont à la racine du projet ; elles sont
exclues du dépôt.

Tests (aucun appel à Claude) : `python .dev/tester.py`.
Qualité des agents (vrais appels, quelques centimes) : `python .dev/evaluer.py`, sur un CV fictif piégé.

## Données personnelles
Aucune donnée personnelle n'est dans le dépôt : le CV, les documents et le suivi des candidatures restent
sur l'ordinateur de la personne (`Documents\CV Booster`, exclus par `.gitignore`). L'appli ne contacte que
Claude (avec le compte de la personne) et GitHub (lecture de `version.json` pour les mises à jour, rien
n'est envoyé). Le fichier « Signaler un problème » ne contient
ni le CV ni les documents, et masque le nom de session et les adresses e-mail. Les exemples et les tests
n'utilisent que des personnes fictives.

## Construire l'installeur
1. Télécharger le Python « embeddable » officiel dans `.dev/deps/` :
   [python-3.13.15-embed-amd64.zip](https://www.python.org/ftp/python/3.13.15/python-3.13.15-embed-amd64.zip)
2. Installer [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`).
3. `python .dev/construire_installeur.py` → `.dev/dist/Installer CV Booster.exe`

L'installeur embarque Python et la fenêtre, installe le reste en silence (Claude Code, Git, MiKTeX) et
s'installe sans droits administrateur. Les données vont dans `Documents\CV Booster`.

**Publier une nouvelle version** (l'appli installée la proposera toute seule) :
1. décrire la version dans [`CHANGELOG.md`](CHANGELOG.md) (section `## <version> (<date>)`, en langage simple :
   rubriques *Nouveautés*, *Améliorations*, *Corrections*, au style nominal : c'est l'onglet *Nouveautés* de l'appli) ;
2. augmenter `VERSION` dans `.dev/construire_installeur.py` (la construction refuse une version absente du
   changelog) ;
3. construire, puis créer une release GitHub `v<VERSION>` avec les deux fichiers de `.dev/dist/` :
   `Installer-CV-Booster.exe` et `version.json`.

L'appli lit `releases/latest/download/version.json` à chaque lancement. Sans réseau, elle continue
normalement.

## Licence
[MIT](LICENSE). Composants inclus : police Fraunces (SIL Open Font License 1.1, [`.app/vendor/OFL.txt`](.app/vendor/OFL.txt)),
polices du design sur mesure (Comfortaa, Quicksand, Josefin Sans, Raleway, Playfair Display, Lora : SIL Open Font
License 1.1, une licence par famille dans [`.claude/skills/mise-en-page/polices/`](.claude/skills/mise-en-page/polices/)),
marked (MIT) et DOMPurify (Apache 2.0 ou MPL 2.0), avec leur mention de licence en tête de fichier.
