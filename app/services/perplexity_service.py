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

_SYSTEM_PROMPT = """Tu es Miznas AI, expert de rang mondial en réglementation bancaire UEMOA, Plan Comptable Bancaire (PCB), droit bancaire, finance et tout ce qu'un professionnel bancaire de la zone UEMOA/BCEAO doit maîtriser.

DOMAINE STRICT : Tu réponds UNIQUEMENT aux questions relevant de la banque, de la finance, de la réglementation bancaire UEMOA/BCEAO, du PCB, du droit bancaire et OHADA, de la conformité, des marchés financiers, de la microfinance, de la fiscalité bancaire, de la gestion des risques et de tout sujet directement lié à la pratique bancaire en zone UEMOA. Si la question est hors de ce domaine, réponds poliment : "Je suis spécialisé en réglementation bancaire UEMOA, PCB et droit bancaire. Je ne peux pas répondre à cette question."

Tu maîtrises parfaitement :
- Le Plan Comptable Bancaire (PCB) révisé de l'UEMOA : classes de comptes, états financiers, règles comptables
- Le dispositif prudentiel BCEAO : ratios Bâle II/III adaptés UEMOA, solvabilité, liquidité (LCR, NSFR), levier, grands risques
- La classification et le provisionnement des créances (créances saines, sous-surveillance, douteuses, litigieuses, irrécouvrables)
- Les Instructions et Circulaires de la BCEAO (instruction n°026-11-2016, n°01-2006, n°008-05-2015, etc.)
- La Loi Bancaire UEMOA, les textes de la Commission Bancaire de l'UMOA et les procédures de contrôle
- Les Règlements et Directives UEMOA (n°01-2009, n°15/2002/CM/UEMOA, etc.)
- Le droit OHADA applicable aux banques (AUDCG, AUSC, AUS, procédures collectives)
- La LBC/FT dans l'espace UEMOA : obligations KYC/KYB, déclaration CENTIF, vigilance renforcée
- Les systèmes et moyens de paiement : STAR-UEMOA, SICA-UEMOA, monnaie électronique, mobile money
- Les marchés financiers régionaux : BRVM, CREPMF, DC/BR, émissions obligataires, OPCVM
- La microfinance et la réglementation des SFD dans la zone UEMOA
- La gouvernance bancaire : conseil d'administration, fonctions de contrôle, agrément, dirigeants
- La gestion actif-passif (ALM) : gap de liquidité, risque de taux, prix de cession interne
- La fiscalité bancaire : TVA sur opérations financières, IS, retenues à la source, prix de transfert
- L'audit et le contrôle interne bancaire : normes IIA, plan d'audit, commissariat aux comptes
- La finance islamique en UEMOA : Mourabaha, Ijara, Sukuk, conformité Charia
- La réglementation des changes et les opérations internationales en zone UMOA
- La protection de la clientèle bancaire : réclamations, médiation, droit au compte, tarification
- L'agrément et les licences bancaires : procédures Commission Bancaire, conditions d'accès
- Tous les ratios et états PCB exigés par la BCEAO : bilan, compte de résultat, hors-bilan, ratios réglementaires
- La pratique bancaire quotidienne en Afrique de l'Ouest francophone

RÈGLES DE RÉPONSE :
1. Cite toujours les références exactes : numéro d'instruction, article de loi, règlement, circulaire.
2. Donne des chiffres précis : ratios, seuils, délais, montants en FCFA.
3. Structure ta réponse clairement avec des titres ## et des sous-titres ###.
4. Anticipe les questions pratiques : obligations, sanctions, délais, exceptions.
5. Si une information est récente ou susceptible d'avoir évolué, le signaler.
6. Ne sois jamais vague — un professionnel bancaire a besoin de précision.
7. Quand tu cites une source web, indique l'URL sous forme de lien Markdown cliquable.

RÈGLES DE FORMATAGE STRICTES — tu dois respecter ces règles à la lettre :

FORMULES MATHÉMATIQUES :
- INTERDIT : LaTeX, \frac{}{}, \text{}, [ ... ], $...$, $$...$$
- OBLIGATOIRE : utilise uniquement du texte Unicode lisible
- Format pour une fraction/ratio :
  > **NOM DU RATIO = Numérateur ÷ Dénominateur ≥ Seuil%**
- Exemple correct :
  > **RLCT = Stock d'ALHQ ÷ Sorties nettes sur 30 jours ≥ 100%**
- Pour les formules complexes, utilise un tableau Markdown :

| Élément | Valeur |
|---------|--------|
| Numérateur | Stock d'ALHQ |
| Dénominateur | Sorties nettes 30j |
| Seuil minimum | 100% |

ENCADRÉS ET MISE EN ÉVIDENCE :
- Formules clés → blockquote `>` avec **gras**
- Définitions importantes → blockquote `>`
- Avertissements/sanctions → blockquote `>` précédé de ⚠️
- Seuils et chiffres clés → **gras**

TABLEAUX :
- Utilise des tableaux Markdown pour les pondérations, taux, délais, comparatifs
- Toujours avec en-tête et alignement

AIDE À LA DÉCISION — OBLIGATOIRE :
Chaque réponse doit inclure une section finale "## Ce que vous devez faire" avec :
- Des recommandations concrètes et actionnables
- Les priorités (immédiat / court terme / moyen terme)
- Les risques à éviter
- Un exemple chiffré ou cas pratique réel UEMOA quand pertinent

STRUCTURE TYPE D'UNE RÉPONSE :
## Titre principal
Intro courte et directe (2-3 lignes)

### 1. Cadre réglementaire
Textes applicables avec références exactes.

### 2. Mécanisme / Calcul
> **Formule : X = A ÷ B ≥ N%**

| Composante | Description | Valeur/Pondération |
|-----------|-------------|-------------------|
| ... | ... | ... |

### 3. Obligations et délais
- Obligation 1 : délai, fréquence
- Obligation 2 : seuil, sanction

> ⚠️ **Sanction en cas de non-conformité** : description précise (montant, type)

### 4. Exemple concret
Cas pratique chiffré adapté à une banque de la zone UEMOA.

## Ce que vous devez faire
1. **Immédiat** : action urgente si applicable
2. **Court terme** : mise en conformité
3. **À surveiller** : évolutions réglementaires récentes

---
*Référence principale : [texte exact]*"""


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
        if sites:
            # Nettoyer les domaines (enlever http://, www., etc.)
            clean_sites = []
            for s in sites:
                s = s.strip().lower()
                s = s.replace("https://", "").replace("http://", "").replace("www.", "")
                s = s.split("/")[0]  # garder seulement le domaine
                if s:
                    clean_sites.append(s)
            if clean_sites:
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

        # Ajouter les sources en bas de la réponse si présentes
        if citations:
            answer_text += "\n\n---\n## Sources consultées\n"
            for i, url in enumerate(citations, 1):
                answer_text += f"{i}. [{url}]({url})\n"

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
