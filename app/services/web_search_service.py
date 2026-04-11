"""
Web Search Service — fallback RAG.

Déclenché quand le RAG ne trouve pas de sources suffisantes (strategy == "NONE").
Interroge DuckDuckGo avec un filtre site: par domaine configuré,
scrape les pages retournées via httpx + BeautifulSoup,
et retourne des chunks au format compatible RAG.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Mots parasites à supprimer pour construire une requête de recherche propre
_NOISE_PHRASES = [
    "est-ce que vous pouvez", "est ce que vous pouvez", "pouvez-vous", "pouvez vous",
    "donnez-moi", "donnez moi", "donne moi", "donne-moi",
    "me donner des informations", "me donner", "des informations sur",
    "des informations de", "parlez-moi de", "parlez moi de",
    "qu'est-ce que", "qu est ce que", "qu'est ce que",
    "expliquez-moi", "expliquez moi", "j'aimerais savoir", "j aimerais savoir",
    "s'il vous plaît", "s il vous plait", "svp",
]


def _build_search_query(question: str) -> str:
    """
    Extrait les mots-clés essentiels de la question pour construire
    une requête de recherche concise et efficace.
    """
    q = question.lower()
    # Couper au premier saut de ligne (instructions de prompt annexées)
    q = q.split("\n")[0].strip()
    # Supprimer les phrases parasites
    for noise in _NOISE_PHRASES:
        q = q.replace(noise, " ")
    # Nettoyer les espaces multiples et ponctuation finale
    q = " ".join(q.split()).strip(" ?.,;:")
    # Si la requête nettoyée est trop courte, utiliser la question originale tronquée
    if len(q) < 10:
        q = question.split("\n")[0][:120].strip()
    return q


# Pays de la zone UEMOA/CEDEAO : noms reconnus comme entités géographiques
_COUNTRY_NAMES = {
    "niger", "nigérien", "nigériens",
    "mali", "malien", "maliens",
    "sénégal", "senegal", "sénégalais",
    "burkina", "burkinabè",
    "côte d'ivoire", "ivoirien",
    "bénin", "benin", "béninois",
    "togo", "togolais",
    "guinée", "guinee", "guinéen",
    "mauritanie", "mauritanien",
    "cameroun", "camerounais",
    "tchad", "tchadien",
    "guinée-bissau",
    "france", "français",
}


def _extract_entities(query: str) -> tuple[set[str], set[str]]:
    """
    Extrait les entités importantes (pays, années 4 chiffres) d'une requête.
    Retourne (pays_trouvés, années_trouvées).
    """
    q_lower = query.lower()
    countries = {c for c in _COUNTRY_NAMES if c in q_lower}
    years = set(re.findall(r"\b(20\d{2})\b", query))
    return countries, years


def _is_relevant(content: str, query: str) -> bool:
    """
    Vérifie que le contenu web est pertinent par rapport à la requête.

    Logique à deux niveaux :
    1. Entités obligatoires : si la requête mentionne un pays et/ou une année,
       le contenu DOIT les contenir aussi (filtre strict).
    2. Mots-clés généraux : au moins MIN_KEYWORD_MATCH mots-clés présents.
    """
    content_lower = content.lower()

    # ── Niveau 1 : entités obligatoires (pays + année) ──────────────────────
    countries, years = _extract_entities(query)

    if countries:
        # Au moins un pays mentionné dans la requête doit être dans le contenu
        if not any(c in content_lower for c in countries):
            return False

    if years:
        # Toutes les années mentionnées dans la requête doivent être dans le contenu
        if not any(yr in content_lower for yr in years):
            return False

    # ── Niveau 2 : mots-clés généraux ───────────────────────────────────────
    stop = {"de", "du", "la", "le", "les", "des", "un", "une", "et", "en",
            "au", "aux", "sur", "par", "pour", "est", "que", "qui", "dans",
            "ce", "se", "ou", "si", "il", "elle", "ils", "elles", "je", "tu",
            "nous", "vous", "me", "te", "lui", "leur", "ma", "sa", "mon", "son",
            "lien", "télécharger", "telecharger", "donner", "donne", "veux"}
    keywords = [w for w in query.lower().split() if len(w) > 3 and w not in stop]
    if not keywords:
        return True  # pas de mots-clés filtrables → garder par défaut
    matches = sum(1 for kw in keywords if kw in content_lower)
    min_match = min(MIN_KEYWORD_MATCH, len(keywords))
    return matches >= min_match

# ── Paramètres ──────────────────────────────────────────────────────────────
MAX_CONTENT_CHARS  = 2000   # longueur max du texte extrait par page
FETCH_TIMEOUT      = 8      # secondes par requête HTTP
MAX_PER_SITE       = 1      # résultats DDG max par domaine (1 suffit)
WEB_SCORE          = 0.80   # score fixe assigné aux sources web
MAX_TOTAL_RESULTS  = 5      # cap total de chunks retournés
WEB_SEARCH_TIMEOUT = 20     # timeout global de toute la recherche web (secondes)
MIN_KEYWORD_MATCH  = 2      # nb minimum de mots-clés trouvés dans le contenu pour le garder

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ── DuckDuckGo search ────────────────────────────────────────────────────────

def _ddg_search_sync(query: str, max_results: int) -> list[dict]:
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results, region="fr-fr"))
    except Exception as exc:
        logger.warning("DDG search échoué pour '%s': %s", query, exc)
        return []


async def _ddg_search(query: str, max_results: int = MAX_PER_SITE) -> list[dict]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_ddg_search_sync, query, max_results),
            timeout=10,  # 10s max par appel DDG
        )
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning("DDG timeout/erreur pour '%s': %s", query, exc)
        return []


# ── Extraction de texte ───────────────────────────────────────────────────────

async def _fetch_text(url: str) -> str:
    """Récupère une page et extrait son texte principal."""
    try:
        async with httpx.AsyncClient(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=FETCH_TIMEOUT,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "html" not in ct:
                return ""

            soup = BeautifulSoup(resp.text, "lxml")

            # Supprimer les balises inutiles
            for tag in soup(["script", "style", "nav", "footer", "header",
                              "aside", "form", "noscript", "iframe"]):
                tag.decompose()

            # Privilégier le contenu principal si disponible
            main = soup.find("main") or soup.find("article") or soup.find("div", {"id": "content"})
            target = main if main else soup.body or soup

            lines = [l.strip() for l in target.get_text(separator="\n").splitlines() if l.strip()]
            return "\n".join(lines)[:MAX_CONTENT_CHARS]

    except Exception as exc:
        logger.warning("Fetch échoué pour %s: %s", url, exc)
        return ""


# ── Point d'entrée principal ─────────────────────────────────────────────────

async def _search_one_site(search_query: str, original_question: str, site: str) -> list[dict[str, Any]]:
    """Recherche sur un seul site et retourne les chunks pertinents."""
    query = f"{search_query} site:{site}"
    hits  = await _ddg_search(query, MAX_PER_SITE)
    chunks: list[dict[str, Any]] = []

    for hit in hits:
        url     = hit.get("href") or hit.get("url") or ""
        title   = hit.get("title") or url
        snippet = hit.get("body") or ""
        if not url:
            continue

        # Vérifier pertinence du titre/snippet avant de fetcher
        combined_preview = f"{title} {snippet}"
        if not _is_relevant(combined_preview, search_query):
            logger.debug("Résultat ignoré (hors sujet) : %s", url)
            continue

        content = await _fetch_text(url)
        if not content or len(content) < 120:
            content = snippet
        if not content or len(content) < 50:
            continue

        # Vérifier pertinence du contenu complet
        if not _is_relevant(content, search_query):
            logger.debug("Contenu ignoré (hors sujet après fetch) : %s", url)
            continue

        chunk_id = hashlib.sha256(url.encode()).hexdigest()[:24]
        chunks.append({
            "id":      chunk_id,
            "content": f"[Web · {site}] {title}\n\n{content}",
            "score":   WEB_SCORE,
            "scope":   "WEB",
            "metadata": {
                "url":      url,
                "title":    title,
                "site":     site,
                "source":   "WEB_SEARCH",
                "filename": f"web:{site}",
                "category": None,
            },
        })
    return chunks


async def search_web(
    question: str,
    sites: list[str],
    max_per_site: int = MAX_PER_SITE,
) -> list[dict[str, Any]]:
    """
    Recherche la question sur tous les sites configurés en parallèle.
    Retourne au maximum MAX_TOTAL_RESULTS chunks au format RAG.
    Timeout global : WEB_SEARCH_TIMEOUT secondes.
    """
    if not question or not sites:
        return []

    # Construire une requête propre sans le bruit conversationnel
    search_query = _build_search_query(question)
    logger.info("web_search | requête nettoyée : '%s'", search_query)

    tasks = [_search_one_site(search_query, question, site) for site in sites]

    try:
        all_results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=WEB_SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("web_search: timeout global (%ds) atteint", WEB_SEARCH_TIMEOUT)
        return []

    results: list[dict[str, Any]] = []
    for res in all_results:
        if isinstance(res, list):
            results.extend(res)

    # Limiter au cap total
    results = results[:MAX_TOTAL_RESULTS]

    logger.info(
        "web_search | question='%s...' | sites=%d | chunks=%d",
        question[:60], len(sites), len(results),
    )
    return results
