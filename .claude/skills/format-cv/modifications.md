# Annexe de format-cv : modifier le CV avec le bloc « modifications »

Chargée seulement par les agents qui modifient un CV existant (relecteur, reformulateur, adaptateur-offre).

N'utilisez **pas** l'outil Edit sur `cv.toml` (un aller-retour par modification : très coûteux). Terminez votre
réponse par **un seul** bloc ; l'application l'applique d'un coup, vérifie que le CV se lit, et lui dit ce qui
a été fait (ne lui montrez pas le bloc, ne le commentez pas) :

````
```modifications
[[remplacer]]
avant = '''de 15000€, 3 agences'''
apres = '''de 15 000 €, 3 agences'''

[[remplacer]]
avant = '''l'entité'''
apres = '''l’entité'''

[ajouter]
texte = '''
[variantes.cle]
titre = "…"
accroche = "…"
'''
```
````
- `avant` : copié **à l'identique** depuis le CV fourni (accents, apostrophes, espaces). Il est remplacé
  **partout** où il apparaît. Prenez l'extrait **le plus court qui ne vise que ce passage** (en général 3 à 6
  mots autour de la correction), pas la puce entière : moins à écrire, donc plus rapide. Court exprès pour
  une correction voulue partout (une apostrophe, un nom d'outil).
- `apres` : jamais de guillemet droit `"` (il casserait le fichier) ; utiliser « » ou ’.
- `[ajouter]` : seulement pour une **nouvelle** version `[variantes.<clé>]` (adaptation à une offre).
- Rien à changer : pas de bloc.
