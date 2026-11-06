<div align="center">

<img src=".app/icone.png" alt="" width="112">

# CV Booster

Créer, améliorer et adapter son CV sur Windows, avec l'abonnement Claude qu'on a déjà.

[![Dernière version](https://img.shields.io/github/v/release/Indaclouds/cv-booster?label=version&color=1e6b45)](https://github.com/Indaclouds/cv-booster/releases/latest)
![Windows 10 et 11](https://img.shields.io/badge/Windows-10%20%7C%2011-1e6b45)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-1e6b45)](LICENSE)

**[Télécharger l'installeur](https://github.com/Indaclouds/cv-booster/releases/latest)**

</div>

---

CV Booster part de vos documents (ancien CV, notes, photo) et en tire un CV propre, sans rien
inventer. Il le relit, l'adapte à chaque annonce et le met en page. Aucune clé d'API n'est nécessaire :
l'application utilise un compte Claude Pro, et l'installeur s'occupe de tout le reste, sans droits
administrateur.

## Fonctionnalités

**Le CV**
- Création à partir de documents en vrac, relecture et reformulation
- Une version par type de poste ou par annonce
- Design inspiré d'un exemple, ou reproduction fidèle de son propre design (graphiste, modèle Canva)
- Deux PDF par version : l'un mis en page, l'autre lisible par les logiciels de tri des recruteurs
- Traduction en anglais et export Word

**La candidature**
- Lettre de motivation assortie au CV
- Comparaison CV et annonce : mots-clés présents ou manquants
- Préparation d'entretien et messages de relance
- Suivi des candidatures, avec rappels

**Au quotidien**
- Versions précédentes du CV et sauvegarde complète des données
- Mises à jour proposées au lancement
- Suivi de la consommation du forfait
- Onglet *Coulisses* pour voir comment travaillent les agents, et en créer

## Vos données

Le CV, les documents et les candidatures restent sur l'ordinateur, dans `Documents\CV Booster`.
L'application ne contacte que Claude, avec votre compte, et GitHub pour vérifier les mises à jour. Le
rapport « Signaler un problème » ne contient ni le CV ni les documents.

## Fonctionnement

Chaque tâche est confiée à un agent spécialisé. Tout ce qui est mécanique (lire les fichiers, vérifier
le style, produire les PDF) passe par des scripts, ce qui limite la consommation du forfait.

| Dossier | Contenu |
|---|---|
| `.app/` | L'application : serveur local, fenêtre et interface |
| `.claude/agents/` | Les agents, un fichier chacun |
| `.claude/skills/` | Les savoir-faire partagés : format du CV, règles d'écriture, mise en page, lettre |
| `.dev/` | Installeur, guide, tests sur données fictives |

## Licence

[MIT](LICENSE). Les polices incluses (Fraunces, Comfortaa, Quicksand, Josefin Sans, Raleway, Playfair
Display, Lora) sont sous SIL Open Font License 1.1, avec leur licence à côté des fichiers. marked (MIT) et
DOMPurify (Apache 2.0 ou MPL 2.0) gardent leur mention en tête de fichier.
