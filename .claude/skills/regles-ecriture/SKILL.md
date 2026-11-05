---
name: regles-ecriture
description: Règles pour écrire un CV qui ne sonne pas « généré par IA » - garder sa voix, du concret, vocabulaire et tournures à éviter, typographie française. Utilisée par les agents qui proposent du texte (relecteur, reformulateur, adaptateur-offre, redacteur-lettre, preparateur-entretien).
---

# Skill : règles d'écriture

But : un recruteur doit lire un CV écrit par la personne elle-même, pas par une machine.
L'essentiel : **modifier le moins possible et garder ses mots.**
(Les détecteurs d'IA en ligne ne sont pas fiables : le seul juge est un recruteur humain.)

## 1. Garder sa voix
- Partir de ses formulations. Corriger ou resserrer plutôt que réécrire.
- Ne changer une phrase que si on peut dire pourquoi : faute, flou, trop long, mot-clé manquant.
- Garder le vocabulaire de son métier (sigles, noms d'outils, de process internes) : c'est ce qui sonne vrai.

## 2. Du concret, jamais d'invention
- Chaque puce contient au moins un élément vérifiable : chiffre, outil, périmètre, livrable, fréquence.
- **Ne jamais inventer** un chiffre, un résultat, un outil ou une responsabilité.
  S'il manque une info, poser la question (« Combien de pôles ? Quel gain ? »).
- Pas d'auto-évaluation (rigoureuse, dynamique, passionnée) : les faits doivent le montrer.

## 3. Vocabulaire à éviter
Liste complète : annexe `lexique-ia.txt` (expressions régulières), chargée par les agents qui écrivent. Les pires :
« fort(e) de », « passionné(e) », « solide expérience », « véritable », « au cœur de », « levier »,
« clé » (adjectif), « valeur ajoutée », « proactif », « orienté(e) résultats », « environnement dynamique »,
« contribuer activement », « s'inscrire dans », « dans un souci de », « synergie », « écosystème », « booster ».

## 4. Structures qui trahissent l'IA
- **Le tiret cadratin (le grand tiret) dans les phrases** : préférer virgule, deux-points ou parenthèses.
- Les énumérations systématiques par trois (« fiabiliser, analyser et piloter »).
- « Non seulement… mais aussi », « Que ce soit… ou… », « En tant que… », « Grâce à… ».
- Des puces toutes de même longueur et de même structure : varier, pas toutes avec un chiffre.
- Une série de puces commençant toutes par un nom en -tion : casser la série avec un verbe.
- Gras partout, émojis, points d'exclamation, Majuscules À Chaque Mot.

**Exemple**
- Avant (IA) : « Fort d'une solide expérience, j'ai piloté avec succès des projets clés, garantissant fiabilité, réactivité et performance. »
- Après (humain) : « Suivi de 12 projets clients en parallèle, avec un point d'avancement hebdomadaire. »

## 5. Typographie française : cohérente plutôt que parfaite
- Une seule apostrophe dans tout le CV (’ ou ').
- Montants : « 25 M€ », avec une espace. Majuscules accentuées : « Économie », « Élaboration ».
- Points finaux dans les puces : partout ou nulle part.

## 6. Vérifier
- Outil : `scripts/verifier_style.py <fichier>` repère le vocabulaire IA et la typographie incohérente.
  (Dans l'application, il est lancé pour toi : son résultat est dans le message.)
- Corriger ce qui vient de **nos** propositions ; signaler sans corriger ce qui vient de **son** texte.
- Toujours finir par : « Relis à voix haute : ce qui ne sonne pas comme toi, on l'enlève. »
