---
name: lettre-motivation
description: Écrire une lettre de motivation pour une offre précise, à partir du CV (jamais d'invention), et la ranger au bon format (un fichier par lettre dans .cv-booster/lettres/). Le PDF est mis en page par un script. Utilisée par l'agent redacteur-lettre.
---

# Skill : lettre de motivation

## Ce qui fait une bonne lettre (recruteurs, 2024-2026)
- **Courte** : 250 à 350 mots, 3 ou 4 paragraphes. Elle se lit en 30 secondes.
- **Pour CETTE offre** : elle cite l'entreprise, le poste et 2 ou 3 besoins précis de l'annonce.
- **Des preuves, pas des qualités** : chaque besoin cité → une expérience réelle du CV, avec un chiffre ou
  un résultat. « Rigoureuse » ne prouve rien ; « 40 dossiers clients suivis en parallèle, sans retard en 2 ans » si.
- **Elle complète le CV** sans le recopier : le pourquoi (ce poste, cette entreprise), le lien entre les
  expériences, une transition de carrière à expliquer.
- **Un ton à elle** : phrases simples, verbes d'action, première personne. Pas de formules toutes faites.

## Plan
1. **Accroche** (2-3 phrases) : le poste visé et la raison concrète de candidater, liée à l'entreprise
   (activité, projet, valeur citée dans l'annonce). Jamais « Je me permets de vous adresser… ».
2. **Ce que j'apporte** : 2 ou 3 besoins de l'offre → une preuve tirée du CV pour chacun.
3. **Pourquoi vous** (court) : ce qui l'attire dans cette entreprise ou ce poste, sans flatterie.
4. **Conclusion** : proposition d'échange, simple. Puis la formule de politesse.

## Interdits
- Inventer une expérience, un chiffre, une motivation. Si une info manque (pourquoi cette entreprise ?),
  **pose la question** plutôt que d'inventer.
- Les marqueurs « IA » de la Skill `regles-ecriture` (« passionnée », « dynamique », « fort de »,
  tirets cadratins en série, énumérations de trois adjectifs…).
- Répéter le CV ligne à ligne.

## Format du fichier : `.cv-booster/lettres/<entreprise>.toml`
Un fichier par lettre ; `<entreprise>` en minuscules, sans accent ni espace (ex. `acme`, `groupe-exemple`).
Voir l'annexe `lettre-exemple.toml`. L'en-tête (nom, contact), la date et la signature sont ajoutés par le
script à partir du CV : ne les écris pas. Le PDF (dossier `CV/`) est produit tout seul après ton passage.
