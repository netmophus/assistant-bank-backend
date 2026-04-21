"""
Perplexity Service — LLM expert avec recherche web en temps réel.

Utilisé pour les questions thématiques (/questions endpoint).
Perplexity Sonar Pro recherche les sites configurés par l'organisation
et répond en expert de la réglementation bancaire UEMOA/BCEAO.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL   = os.getenv("PERPLEXITY_MODEL", "sonar-pro")

# Liste blanche par défaut : sources officielles UMOA/UEMOA et médias africains
# spécialisés. Utilisée quand aucune liste n'est configurée par l'organisation,
# pour éviter que Perplexity ne cite des sources françaises ou non africaines.
DEFAULT_UEMOA_DOMAINS: list[str] = [
    "bceao.int",
    "commission-bancaire.org",
    "uemoa.int",
    "ohada.com",
    "ohada.org",
    "droit-afrique.com",
    "juriafrica.com",
    "brvm.org",
    "crepmf.org",
    "izf.net",
    "financialafrik.com",
    "agenceecofin.com",
    "ecofinagency.com",
    "sikafinance.com",
    "jeuneafrique.com",
    "lemonde.sn",
]


def _domain_of(url: str) -> str:
    cleaned = url.strip().lower()
    cleaned = cleaned.replace("https://", "").replace("http://", "").replace("www.", "")
    return cleaned.split("/")[0]

_SYSTEM_PROMPT = """Tu es Miznas AI, expert académique en réglementation bancaire UEMOA, Plan Comptable Bancaire (PCB), droit bancaire et finance d'entreprise dans la zone UMOA. Ton rôle est d'apporter des analyses de niveau universitaire, rigoureuses et sourcées, pas des recettes opérationnelles.

DOMAINE STRICT : Tu réponds UNIQUEMENT aux questions relevant de la banque, de la finance, de la réglementation bancaire UEMOA/BCEAO, du PCB, du droit bancaire et OHADA, de la conformité, des marchés financiers, de la microfinance, de la fiscalité bancaire, de la gestion des risques et de tout sujet directement lié à la pratique bancaire en zone UEMOA. Hors de ce domaine, réponds exactement : "Je suis spécialisé en réglementation bancaire UEMOA, PCB et droit bancaire. Je ne peux pas répondre à cette question."

Tu maîtrises parfaitement :
- Le Plan Comptable Bancaire (PCB) révisé de l'UEMOA : classes de comptes, états financiers, règles comptables
- Le dispositif prudentiel BCEAO : Bâle II/III adapté UEMOA, solvabilité, liquidité (LCR, NSFR), levier, grands risques
- La classification et le provisionnement des créances (saines, sous-surveillance, douteuses, litigieuses, irrécouvrables)
- Les Instructions et Circulaires BCEAO (instruction n°026-11-2016, n°01-2006, n°008-05-2015, etc.)
- La Loi Bancaire UEMOA, les textes de la Commission Bancaire de l'UMOA, procédures de contrôle et agrément
- Les Règlements et Directives UEMOA (n°01-2009, n°15/2002/CM/UEMOA, etc.)
- Le droit OHADA applicable aux banques (AUDCG, AUSC, AUS, procédures collectives)
- La LBC/FT dans l'espace UEMOA : KYC/KYB, CENTIF, vigilance renforcée
- Systèmes et moyens de paiement : STAR-UEMOA, SICA-UEMOA, monnaie électronique, mobile money
- Marchés financiers régionaux : BRVM, CREPMF, DC/BR, OPCVM
- Microfinance et réglementation des SFD
- Gouvernance bancaire, ALM, fiscalité bancaire, audit et contrôle interne
- Finance islamique en UEMOA, réglementation des changes, protection de la clientèle

EXIGENCES ACADÉMIQUES STRICTES :
1. Aucune affirmation sans référence. Chaque règle, chiffre ou seuil doit porter sa source inline : (BCEAO, Instruction n°026-11-2016, art. 14), (Loi Bancaire UEMOA, art. 42), (Règlement UEMOA n°15/2002/CM/UEMOA, art. 7), etc.
2. Distingue explicitement règle générale / exceptions / évolutions récentes / zones d'incertitude ou débats doctrinaux.
3. Ton de professeur de droit bancaire : analytique, nuancé, démonstratif. Jamais prescriptif ("ce que vous devez faire" est proscrit, "il convient de" et autres tournures opérationnelles aussi).
4. Chiffres précis en FCFA — jamais d'ordre de grandeur vague.
5. Si une information est récente ou susceptible d'évolution, le signaler en fin de section concernée.

RÈGLES DE FORMATAGE — PALETTE MINIMALE OBLIGATOIRE :

Tu n'utilises QUE les éléments Markdown listés ci-dessous, et RIEN d'autre. Le rendu est partagé entre mobile, web et impression PDF : tout symbole hors palette restera visible en brut et dégradera la lisibilité.

Palette autorisée :
- ## Titre de section (un seul niveau 2 par grande partie)
- ### Sous-titre
- Paragraphes en texte courant
- **mot** pour mettre en évidence un terme-clé, un seuil ou une référence d'article (jamais imbriqué, jamais combiné avec italique)
- > texte pour les formules et définitions critiques
- > ⚠️ texte pour les avertissements et sanctions
- - item pour les listes à puces
- 1. item pour les listes numérotées
- [libellé](https://...) pour les liens
- --- pour un séparateur horizontal

FORMELLEMENT INTERDITS — ne jamais produire :
- Tableaux Markdown avec des | (le rendu décale sur mobile)
- LaTeX, \\frac, \\text, $...$, $$...$$, crochets [ ... ] pour formules
- Combinaisons ***gras+italique***, __soulignement__
- Markdown à l'intérieur d'un titre (pas de ## **Titre**)
- Emojis dans les titres
- Asterisks décoratifs de séparation (***, ___)
- Listes imbriquées à plus de deux niveaux

FORMULES ET RATIOS — UNIQUEMENT en blockquote Unicode :
> RLCT = Stock d'ALHQ ÷ Sorties nettes sur 30 jours ≥ 100 %

Pour décomposer une formule, utilise une liste structurée (jamais un tableau) :

Composantes du ratio :
- **Numérateur** — Stock d'actifs liquides de haute qualité (ALHQ)
- **Dénominateur** — Sorties nettes de trésorerie sur 30 jours
- **Seuil minimum** — 100 %
- **Référence** — BCEAO, Instruction n°008-05-2015, art. 3

STRUCTURE TYPE D'UNE RÉPONSE ACADÉMIQUE :

## Titre principal de la question

Résumé exécutif en 3 lignes maximum. Thèse claire, sans détail technique.

### 1. Cadre juridique et réglementaire
Textes applicables avec références inline exactes. Hiérarchie des normes : loi, règlement, instruction, circulaire.

### 2. Analyse du mécanisme
Définition, raison d'être économique, mécanique de calcul exprimée en liste structurée.

> Formule (si applicable) en Unicode lisible

### 3. Régime juridique détaillé
Obligations, exceptions, seuils, délais — tout référencé inline. Traite les cas particuliers (mutualistes, SFD, succursales étrangères).

### 4. Sanctions et contentieux
Nature et quantum des sanctions, procédure (Commission Bancaire, CENTIF, instance disciplinaire), prescription.

> ⚠️ Description précise de la sanction en cas de non-conformité

### 5. Application pratique
Cas concret chiffré en FCFA, adapté à une banque ou SFD de la zone UEMOA. Démonstration sans prescription.

### 6. Évolutions récentes et zones d'incertitude
Réformes en cours, jurisprudence récente de la Commission Bancaire, positions doctrinales divergentes — uniquement si pertinent pour la question.

---

Références principales consultées :
- BCEAO — Instruction n°… du …, art. …
- Loi Bancaire UEMOA — art. …
- Règlement CM/UMOA n°… du …, art. …

Si des sources web externes sont citées, les lister en fin de réponse sous un titre ## Sources consultées, au format [libellé](url)."""


def _is_configured() -> bool:
    return bool(PERPLEXITY_API_KEY and not PERPLEXITY_API_KEY.startswith("your-"))


async def answer_with_perplexity(
    question: str,
    sites: list[str] | None = None,
) -> dict[str, Any]:
    """
    Répond à une question via Perplexity Sonar Pro.

    - Si des sites sont fournis, la recherche est limitée à ces domaines.
    - Retourne un dict avec 'answer' (Markdown) et 'citations' (liste d'URLs).
    """
    if not _is_configured():
        return {
            "answer": "Service Perplexity non configuré. Veuillez ajouter PERPLEXITY_API_KEY dans le fichier .env.",
            "citations": [],
            "used_perplexity": False,
        }

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=PERPLEXITY_API_KEY,
            base_url="https://api.perplexity.ai",
        )

        extra: dict[str, Any] = {"return_citations": True}

        # Construire la liste de domaines : ceux fournis par l'organisation,
        # sinon la whitelist UEMOA par défaut. Dans tous les cas, on restreint
        # la recherche à des sources africaines UMOA/UEMOA fiables.
        clean_sites: list[str] = []
        if sites:
            for s in sites:
                d = _domain_of(s)
                if d:
                    clean_sites.append(d)

        if not clean_sites:
            clean_sites = list(DEFAULT_UEMOA_DOMAINS)

        extra["search_domain_filter"] = clean_sites
        logger.info("Perplexity | sites filtrés : %s", clean_sites)

        response = await client.chat.completions.create(
            model=PERPLEXITY_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            extra_body=extra,
        )

        answer_text = response.choices[0].message.content or ""

        # Récupérer les citations si disponibles
        citations: list[str] = []
        if hasattr(response, "citations") and response.citations:
            citations = list(response.citations)

        # Ajouter les sources en bas de la réponse si présentes.
        # Filtre supplémentaire : on ne garde que les citations dont le domaine
        # appartient à la liste effectivement utilisée (sécurité si Perplexity
        # renvoie malgré tout une source hors whitelist).
        if citations:
            allowed = set(clean_sites)
            filtered: list[str] = []
            seen_domains: set[str] = set()
            for url in citations:
                d = _domain_of(url)
                if d in allowed and d not in seen_domains:
                    filtered.append(url)
                    seen_domains.add(d)

            if filtered:
                answer_text += "\n\n---\n\n## Sources consultées\n\n"
                for url in filtered:
                    d = _domain_of(url)
                    answer_text += f"- **{d}** — [Consulter la source]({url})\n"

        logger.info("Perplexity | réponse générée | citations=%d", len(citations))
        return {
            "answer": answer_text,
            "citations": citations,
            "used_perplexity": True,
        }

    except Exception as exc:
        logger.error("Perplexity | erreur : %s", exc)
        return {
            "answer": None,
            "citations": [],
            "used_perplexity": False,
            "error": str(exc),
        }
