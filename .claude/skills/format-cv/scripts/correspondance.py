"""Correspondance entre une offre d'emploi et le CV : quels mots-clés de l'annonce apparaissent dans le CV ?
C'est grossièrement ce que font les logiciels de tri (ATS). Un simple script : aucun token, toujours pareil.

Usage :
    python correspondance.py <cv.toml> <offre.txt> [--variante cle] [--json]

Méthode (volontairement simple et explicable) :
  1. mots de l'offre, sans les mots vides ni le jargon d'annonce (« poste », « profil », « H/F »…) ;
  2. on garde les plus fréquents, en favorisant les termes techniques (sigles, outils en majuscule)
     et les expressions de deux mots répétées (« gestion de projet » → « gestion projet ») ;
  3. chacun est cherché dans le texte du CV (version choisie), sans tenir compte des accents ni du pluriel.
Le score est indicatif : un mot trouvé ne dit pas si l'expérience correspond vraiment.
"""

import json
import re
import sys
import tomllib
import unicodedata
from collections import Counter
from pathlib import Path

MOTS_VIDES = set("""
a au aux avec ce ces cet cette dans de des du elle en et eux il ils je la le les leur leurs lui ma mais me meme
mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un une vos
votre vous y d l j m n s t c qu ainsi alors apres aussi autre autres avant bien car chaque comme dont donc
encore entre etc etre fait faire ici ils jusqu leur lors moins peu peut plus plusieurs pour pres puis sans
selon si sont sous tant tous tout toute toutes tres trop via vers deja afin aupres egalement notamment
avoir ayant etes ete sera serez seront est sommes ont avez etait sein cas fois tel telle tels telles
the and of to in for with on at by an be is are as or your our you we will this that from
""".split())
JARGON = set("""
poste postes profil profils mission missions entreprise entreprises equipe equipes candidat candidate
candidats candidature candidatures recherche recherchons cherchons rejoindre rejoignez rejoins h f hf cdi cdd
stage alternance temps plein partiel salaire remuneration avantages avantage annee annees ans an experience
experiences minimum souhaitee souhaite souhaitable requis requise idealement capacite capacites
qualites qualite sens bonne bon bonnes bons excellent excellente forte fort niveau groupe societe
client clients offre offres description descriptif contexte job emploi emplois date debut lieu localisation
teletravail jours semaine possible possibilite environnement collaborateurs collaborateur cadre cadres
nouveau nouvelle nouveaux nouvelles principales principaux principal principale activite activites
ensemble domaine domaines cours mise place projet projets travail travailler role responsabilites
responsabilite assurer assurez participer participez contribuer contribuez accompagner accompagnez
garantir veiller etes serez aurez avez savez souhaitez etudiant etudiants diplome diplomee formation
directeur directrice rattache rattachee personnes personne apprecie appreciee maitrise connaissance
connaissances esprit aisance rigueur realiser construire faire evoluer piloter analyser proposer lien
professionnel professionnelle relationnel relationnelle operationnel operationnels operationnelle
international internationale national nationale autonomie autonome dynamique motive motivee
""".split())


def normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9+#]+", " ", sans_accents.lower())


def racine(mot: str) -> str:
    """Pluriels et formes proches : « tableaux » ~ « tableau », « analyses » ~ « analyse »."""
    for fin, rempl in (("aux", "al"), ("eaux", "eau"), ("s", ""), ("x", "")):
        if len(mot) > 4 and mot.endswith(fin):
            return mot[: -len(fin)] + rempl
    return mot


def utile(mot: str) -> bool:
    return mot not in MOTS_VIDES and mot not in JARGON and (len(mot) >= 3 or mot in {"bi", "rh", "ia", "c#", "c++"}) \
        and not mot.isdigit()


def termes_techniques(texte: str) -> dict[str, float]:
    """Bonus des termes « techniques » : sigles en majuscules (SAP, KPI, IFRS) ×3,
    mot avec majuscule en milieu de phrase (Excel, Power BI) ×1,5."""
    res = {}
    for phrase in re.split(r"[.!?:\n•\-–]+", texte):
        mots = re.findall(r"[A-Za-zÀ-ÿ0-9+#]+", phrase)
        for i, m in enumerate(mots):
            n = normaliser(m).strip()
            if m.isupper() and len(m) >= 2:
                res[n] = 3
            elif i > 0 and m[:1].isupper():
                res.setdefault(n, 1.5)
    return res


def mots_cles(offre: str, maxi: int = 20) -> list[str]:
    bonus = termes_techniques(offre)
    mots = normaliser(offre).split()
    freq, forme, premier = Counter(), {}, {}  # forme : la plus fréquente, pour l'affichage
    for ligne in offre.splitlines():
        # Les listes à puces (missions, profil) portent les compétences : elles comptent plus que l'intro
        poids = 1.5 if re.match(r"\s*([-•*–·]|\d+[.)])\s", ligne) else 1
        for m in normaliser(ligne).split():
            if utile(m):
                freq[racine(m)] += poids
                forme.setdefault(racine(m), Counter())[m] += 1
                premier.setdefault(m, len(premier))
    # Expressions de deux mots utiles consécutifs (en ignorant « de », « des »…) : répétées, ou deux termes
    # techniques (« Power BI »)
    bigrammes = Counter()
    fenetre = [m for m in mots if m not in {"de", "des", "du", "d", "la", "le", "les", "l", "et", "en", "a"}]
    for a, b in zip(fenetre, fenetre[1:]):
        if utile(a) and utile(b):
            bigrammes[(a, b)] += 1
    scores = {}
    for (a, b), n in bigrammes.items():
        sigle = max(bonus.get(a, 1), bonus.get(b, 1)) == 3  # « Power BI » oui, « Administratif Financier » non
        if n >= 2 or (a in bonus and b in bonus and sigle and racine(a) != racine(b)):
            scores[f"{a} {b}"] = n * 2.5 * max(bonus.get(a, 1), bonus.get(b, 1))
    dans_expression = {m for k in scores for m in k.split()}
    for r, n in freq.items():
        f = forme[r].most_common(1)[0][0]
        if f not in dans_expression:  # « power » et « bi » seuls : déjà couverts par « power bi »
            scores[f] = n * bonus.get(f, 1)
    # À score égal : dans l'ordre de l'annonce (les annonces listent l'essentiel d'abord)
    ordre = lambda k: premier.get(k.split()[0], 999)  # noqa: E731
    return sorted(scores, key=lambda k: (-scores[k], ordre(k)))[:maxi]


def texte_cv(cv: dict, variante: str | None) -> str:
    """Tout le texte du CV, pour la version choisie (titre, accroche, remplacements de cette version)."""
    variantes = cv.get("variantes", {})
    cle = variante if variante in variantes else next(iter(variantes), None)
    choisie = variantes.get(cle, {}) if cle else {}
    morceaux = []

    def parcourir(x):
        if isinstance(x, str):
            morceaux.append(choisie.get("remplacements", {}).get(x, x))
        elif isinstance(x, dict):
            for v in x.values():
                parcourir(v)
        elif isinstance(x, list):
            for v in x:
                parcourir(v)
    parcourir({k: v for k, v in cv.items() if k != "variantes"})
    parcourir({k: v for k, v in choisie.items() if k != "remplacements"})
    return " ".join(morceaux)


def present(terme: str, cv_norm: str, cv_racines: set[str]) -> bool:
    if " " in terme:  # les deux mots, proches ou non (« ERP SAP » ~ « SAP » … « ERP »)
        return all(racine(m) in cv_racines for m in terme.split())
    return racine(terme) in cv_racines


def analyser(cv: dict, offre: str, variante: str | None = None) -> dict:
    cv_norm = normaliser(texte_cv(cv, variante))
    cv_racines = {racine(m) for m in cv_norm.split()}
    termes = mots_cles(offre)
    trouves = [t for t in termes if present(t, cv_norm, cv_racines)]
    manquants = [t for t in termes if t not in trouves]
    score = round(100 * len(trouves) / len(termes)) if termes else 0
    return {"score": score, "trouves": trouves, "manquants": manquants, "total": len(termes)}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        sys.exit(__doc__)
    variante = sys.argv[sys.argv.index("--variante") + 1] if "--variante" in sys.argv else None
    if variante in args:
        args.remove(variante)
    cv = tomllib.loads(Path(args[0]).read_text(encoding="utf-8-sig"))
    r = analyser(cv, Path(args[1]).read_text(encoding="utf-8-sig"), variante)
    if "--json" in sys.argv:
        print(json.dumps(r, ensure_ascii=False))
        return
    print(f"{len(r['trouves'])} mots-clés de l'offre sur {r['total']} apparaissent dans le CV ({r['score']} %, indicatif).")
    print("Présents : " + (", ".join(r["trouves"]) or "aucun"))
    print("Absents  : " + (", ".join(r["manquants"]) or "aucun"))
    print("Rappel : n'ajoute un mot absent que s'il correspond à une vraie expérience.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
