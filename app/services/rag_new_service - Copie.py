from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

# Charger .env si présent (ne modifie pas la config existante)
load_dotenv()


def _normalize_mongo_uri(uri: str) -> str:
    """Normalise l'URI MongoDB pour Atlas Local.

    Atlas Local peut annoncer des hostnames internes (container id) en mode replica set.
    Sur Windows, sans `directConnection=true`, le driver peut essayer de résoudre ces
    hostnames internes et échouer.
    """

    u = (uri or "").strip()
    if not u:
        return "mongodb://127.0.0.1:27017/?directConnection=true"

    low = u.lower()
    if low.startswith("mongodb://") and (
        "mongodb://localhost:" in low or "mongodb://127.0.0.1:" in low
    ):
        if "directconnection=" not in low:
            if "?" in u:
                return u + "&directConnection=true"
            return u.rstrip("/") + "/?directConnection=true"

    return u


MONGODB_URI = _normalize_mongo_uri(
    os.getenv("RAG_NEW_MONGO_URI", "mongodb://127.0.0.1:27017")
)
MONGODB_DB = os.getenv("RAG_NEW_DB") or os.getenv("RAG_NEW_DB_NAME") or "rag_new"

GLOBAL_COLLECTION = os.getenv("RAG_NEW_GLOBAL_COLLECTION", "knowledge_global")
LOCAL_COLLECTION = os.getenv("RAG_NEW_LOCAL_COLLECTION", "knowledge_local")

GLOBAL_VECTOR_INDEX = (
    os.getenv("RAG_NEW_GLOBAL_VECTOR_INDEX")
    or os.getenv("RAG_NEW_GLOBAL_INDEX_NAME")
    or "global_vec_idx"
)
LOCAL_VECTOR_INDEX = (
    os.getenv("RAG_NEW_LOCAL_VECTOR_INDEX")
    or os.getenv("RAG_NEW_LOCAL_INDEX_NAME")
    or "local_vec_idx"
)

EMBEDDING_MODEL = os.getenv("RAG_NEW_EMBEDDING_MODEL", "text-embedding-3-large")
EMBEDDING_DIMENSIONS = int(os.getenv("RAG_NEW_EMBEDDING_DIMENSIONS", "3072"))

# Règles de priorisation demandées
GLOBAL_RELEVANCE_THRESHOLD = float(os.getenv("RAG_NEW_GLOBAL_THRESHOLD", "0.79"))
GLOBAL_FALLBACK_MIN_DOCS = int(os.getenv("RAG_NEW_GLOBAL_MIN_DOCS", "3"))
GLOBAL_FALLBACK_MIN_MAX_SCORE = float(os.getenv("RAG_NEW_GLOBAL_MIN_MAX_SCORE", "0.75"))

# Si rien ne passe les seuils, on garde quand même les top-k si le max_score est suffisamment élevé.
# (optionnel, compatible: seulement utilisé si défini ou défaut)
GLOBAL_ABS_MIN_MAX_SCORE = float(os.getenv("RAG_NEW_GLOBAL_ABS_MIN_MAX_SCORE", "0.72"))

# Seuil pour la base locale (par défaut plus permissif que le global)
LOCAL_RELEVANCE_THRESHOLD = float(os.getenv("RAG_NEW_LOCAL_THRESHOLD", "0.73"))
LOCAL_FALLBACK_MIN_MAX_SCORE = float(os.getenv("RAG_NEW_LOCAL_MIN_MAX_SCORE", "0.55"))
LOCAL_ABS_MIN_MAX_SCORE = float(os.getenv("RAG_NEW_LOCAL_ABS_MIN_MAX_SCORE", "0.68"))

ARTICLE_THRESHOLD_DELTA = float(os.getenv("RAG_NEW_ARTICLE_THRESHOLD_DELTA", "0.07"))

ARTICLE_QUERY_K = int(os.getenv("RAG_NEW_ARTICLE_K", "40"))

FORCE_GLOBAL = (os.getenv("RAG_NEW_FORCE_GLOBAL", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}

STRICT_SOURCES = (os.getenv("RAG_NEW_STRICT_SOURCES", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}

DEBUG_CHUNKS = (os.getenv("RAG_NEW_DEBUG_CHUNKS", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}

# Messages user-facing (configurables, pour éviter le code en dur)
RAG_NO_SOURCES_MESSAGE = os.getenv(
    "RAG_NEW_NO_SOURCES_MESSAGE",
    "Je n'ai trouvé aucune source pertinente dans les bases de connaissances globale et locale.",
)
RAG_ARTICLE_ABSENT_TEMPLATE = os.getenv(
    "RAG_NEW_ARTICLE_ABSENT_TEMPLATE",
    "L'Article {article_num} de l'instruction demandée n'est pas présent dans les extraits disponibles. Veuillez vérifier le document source ou reformuler avec plus de précision.",
)
RAG_INGESTION_INCOMPLETE_TEMPLATE = os.getenv(
    "RAG_NEW_INGESTION_INCOMPLETE_TEMPLATE",
    "Je n'ai pas pu retrouver l'Article {article_num} dans l'index pour ce document. Il est probable que l'ingestion/indexation du PDF soit incomplète (chunks manquants). Veuillez ré-uploader / ré-ingérer le document puis réessayer.",
)
RAG_LIST_DOCUMENTS_HEADER = os.getenv(
    "RAG_NEW_LIST_DOCUMENTS_HEADER",
    "Documents candidats (issus des meilleurs résultats de recherche):",
)

logger = logging.getLogger(__name__)


def _normalize_text(s: str) -> str:
    t = (s or "").lower()
    t = t.replace("’", "'")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _detect_language_hint(text: str) -> str:
    q = (text or "").lower()
    fr_hits = 0
    en_hits = 0
    if re.search(r"\b(je|tu|vous|nous|que|quoi|comment|pourquoi|définition|definir|définir|où|trouver|liste|différence|etapes?|étapes?)\b", q):
        fr_hits += 1
    if re.search(r"\b(i|you|we|what|how|why|define|definition|where|find|list|difference|compare|steps?)\b", q):
        en_hits += 1
    if fr_hits and en_hits:
        return "mixed"
    if fr_hits:
        return "fr"
    if en_hits:
        return "en"
    return "unknown"


def _query_stopwords_fr_en() -> set[str]:
    return {
        "a",
        "about",
        "alors",
        "and",
        "are",
        "as",
        "avec",
        "avoir",
        "be",
        "because",
        "been",
        "but",
        "by",
        "can",
        "comment",
        "comme",
        "dans",
        "de",
        "define",
        "definition",
        "définition",
        "des",
        "do",
        "donc",
        "donner",
        "donne",
        "du",
        "dun",
        "dune",
        "en",
        "est",
        "et",
        "explain",
        "expliquer",
        "explique",
        "for",
        "from",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "je",
        "la",
        "le",
        "les",
        "like",
        "liste",
        "list",
        "mais",
        "me",
        "merci",
        "not",
        "of",
        "on",
        "or",
        "ou",
        "our",
        "pour",
        "pourquoi",
        "provide",
        "quand",
        "que",
        "quel",
        "quels",
        "quelle",
        "quelles",
        "quoi",
        "sont",
        "the",
        "their",
        "this",
        "to",
        "tu",
        "un",
        "une",
        "vos",
        "votre",
        "vous",
        "we",
        "what",
        "where",
        "which",
        "why",
        "with",
        "your",
    }


def _extract_numbers_and_like(question: str, max_items: int = 10) -> List[str]:
    q = (question or "")
    out: List[str] = []
    seen: set[str] = set()
    for m in re.findall(r"\b\d+(?:[\.,]\d+)?\b", q):
        v = str(m)
        if v not in seen:
            seen.add(v)
            out.append(v)
        if len(out) >= max_items:
            return out
    for m in re.findall(r"\b\d+(?:\.\d+){1,4}\b", q):
        v = str(m)
        if v not in seen:
            seen.add(v)
            out.append(v)
        if len(out) >= max_items:
            return out
    for m in re.findall(r"\b[IVXLCDM]{1,8}\b", q, flags=re.IGNORECASE):
        v = str(m)
        if v not in seen:
            seen.add(v)
            out.append(v)
        if len(out) >= max_items:
            return out
    for m in re.findall(r"\b[A-Z]\b", q):
        v = str(m)
        if v not in seen:
            seen.add(v)
            out.append(v)
        if len(out) >= max_items:
            return out
    return out


def _extract_structured_references(question: str, max_refs: int = 8) -> List[Dict[str, Any]]:
    q = question or ""
    refs: List[Dict[str, Any]] = []
    patterns: List[Tuple[str, str, float]] = [
        ("article", r"\b(?:article|art\.?)(?:\s|\u00A0)+(?P<val>\d+)\b", 0.95),
        ("section", r"\b(?:section|sec\.?)(?:\s|\u00A0)+(?P<val>\d+(?:\.\d+){1,4})\b", 0.90),
        ("chapter", r"\b(?:chapter|chapitre)(?:\s|\u00A0)+(?P<val>[IVXLCDM]+|\d+)\b", 0.88),
        ("annex", r"\b(?:annex|annexe)(?:\s|\u00A0)+(?P<val>[A-Z]|\d+)\b", 0.86),
        ("table", r"\b(?:table|tableau)(?:\s|\u00A0)+(?P<val>\d+)\b", 0.84),
        ("figure", r"\b(?:figure|fig\.?)(?:\s|\u00A0)+(?P<val>\d+)\b", 0.84),
        ("numbered_heading", r"\b(?P<val>\d+(?:\.\d+){1,4})\b", 0.55),
    ]

    seen: set[Tuple[str, str]] = set()
    for kind, pat, conf in patterns:
        for m in re.finditer(pat, q, flags=re.IGNORECASE):
            val = (m.groupdict().get("val") or "").strip()
            raw = (m.group(0) or "").strip()
            if not val:
                continue
            key = (kind, val)
            if key in seen:
                continue
            seen.add(key)
            refs.append({"kind": kind, "value": val, "raw": raw, "confidence": float(conf)})
            if len(refs) >= max_refs:
                return refs
    return refs


def analyze_query(question: str) -> Dict[str, Any]:
    q_norm = _normalize_text(question)
    lang = _detect_language_hint(question)
    stop = _query_stopwords_fr_en()

    tokens = re.findall(r"[a-zà-öø-ÿ0-9_'-]{3,}", q_norm, flags=re.IGNORECASE)
    keywords: List[str] = []
    seen_kw: set[str] = set()
    for t in tokens:
        tt = (t or "").strip().lower()
        if not tt:
            continue
        if tt in stop:
            continue
        if tt in seen_kw:
            continue
        seen_kw.add(tt)
        keywords.append(tt)
        if len(keywords) >= 12:
            break

    words = [w for w in re.findall(r"[a-zà-öø-ÿ0-9_'-]{2,}", q_norm) if w]
    phrases: List[str] = []
    seen_ph: set[str] = set()
    for n in (4, 3, 2):
        for i in range(0, max(0, len(words) - n + 1)):
            ph = " ".join(words[i : i + n]).strip()
            if len(ph) < 8:
                continue
            if ph in seen_ph:
                continue
            if all((w in stop) for w in ph.split() if w):
                continue
            seen_ph.add(ph)
            phrases.append(ph)
            if len(phrases) >= 10:
                break
        if len(phrases) >= 10:
            break

    numbers = _extract_numbers_and_like(question)
    structured_refs = _extract_structured_references(question)

    q = q_norm
    intents: Dict[str, float] = {
        "list_request": 0.0,
        "definition_request": 0.0,
        "reference_request": 0.0,
        "comparison_request": 0.0,
        "procedure_request": 0.0,
        "explanation_request": 0.0,
        "document_navigation_request": 0.0,
    }

    if re.search(r"\b(liste|list|enumerate|énum(é|e)rer|enum(?:e|é)rer|give me|provide)\b", q):
        intents["list_request"] = max(intents["list_request"], 0.85)
    if re.search(r"\b(qu['’]?est-ce que|c['’]?est quoi|définition|define|what is|meaning of)\b", q):
        intents["definition_request"] = max(intents["definition_request"], 0.85)
    if re.search(r"\b(source|reference|référence|cite|citation|where is it stated|où est-ce (?:écrit|indiqué)|où (?:trouver|voir))\b", q):
        intents["reference_request"] = max(intents["reference_request"], 0.70)
    if structured_refs:
        intents["reference_request"] = max(intents["reference_request"], 0.92)
    if re.search(r"\b(diff(é|e)rence entre|difference between|compare|comparison|vs\.?|versus)\b", q):
        intents["comparison_request"] = max(intents["comparison_request"], 0.80)
    if re.search(r"\b(comment faire|comment (?:proc(é|e)der|r(é|e)aliser)|how to|steps?|step-by-step|procedure|proc(é|e)dure|workflow|process)\b", q):
        intents["procedure_request"] = max(intents["procedure_request"], 0.80)
    if re.search(r"\b(pourquoi|why|explain|expliquer|explique|explanation)\b", q):
        intents["explanation_request"] = max(intents["explanation_request"], 0.60)
    if re.search(r"\b(quels? documents?|which documents?|where can i find|o[uù] trouver|dans (?:la|les) base|knowledge base|base de connaissance)\b", q):
        intents["document_navigation_request"] = max(intents["document_navigation_request"], 0.85)

    expects = {
        "list_like": bool(intents.get("list_request", 0.0) >= 0.75),
        "reference_like": bool(intents.get("reference_request", 0.0) >= 0.75),
        "procedure_like": bool(intents.get("procedure_request", 0.0) >= 0.75),
        "comparison_like": bool(intents.get("comparison_request", 0.0) >= 0.75),
    }

    return {
        "version": "v1",
        "question": str(question or ""),
        "question_norm": str(q_norm),
        "language_hint": str(lang),
        "terms": {"keywords": keywords, "phrases": phrases, "numbers": numbers},
        "structured_references": structured_refs,
        "intents": intents,
        "expects": expects,
    }


def _extract_keywords(question: str, max_keywords: int = 8) -> List[str]:
    q = _normalize_text(question)
    tokens = re.findall(r"[a-zà-öø-ÿ0-9_'-]{4,}", q, flags=re.IGNORECASE)
    stop = {
        "avec",
        "aussi",
        "ainsi",
        "alors",
        "avoir",
        "comment",
        "dans",
        "donc",
        "donner",
        "donne",
        "entre",
        "expliquer",
        "explique",
        "merci",
        "pourquoi",
        "quels",
        "quelles",
        "quel",
        "quelle",
        "sont",
        "leurs",
        "votre",
        "vous",
        "document",
        "processus",
        "base",
        "connaissance",
        "connaissances",
    }
    out: List[str] = []
    seen = set()
    for t in tokens:
        tt = t.lower()
        if tt in stop or tt in seen:
            continue
        seen.add(tt)
        out.append(tt)
        if len(out) >= max_keywords:
            break
    return out


def _extract_phrases(question: str, max_phrases: int = 6) -> List[str]:
    """Extrait des bigrams/trigrams présents dans la question (générique, pas d'exemples codés en dur)."""
    q = _normalize_text(question)
    words = [w for w in re.findall(r"[a-zà-öø-ÿ0-9_'-]{3,}", q) if w]
    phrases: List[str] = []
    seen = set()
    for n in (3, 2):
        for i in range(0, max(0, len(words) - n + 1)):
            ph = " ".join(words[i : i + n]).strip()
            if len(ph) < 10:
                continue
            if ph in seen:
                continue
            seen.add(ph)
            phrases.append(ph)
            if len(phrases) >= max_phrases:
                return phrases
    return phrases


def _has_enumeration_intent(question: str) -> bool:
    q = _normalize_text(question)
    # Intention générique: "six critères", "3 composantes", etc.
    if re.search(r"\b(\d+|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)\b\s+(crit[eè]res?|composantes?|points?|conditions?|[eé]l[eé]ments?)\b", q):
        return True
    return False


def _looks_like_enumeration(text: str) -> bool:
    t = (text or "")
    if not t:
        return False
    # Signaux génériques de liste/énumération.
    if re.search(r"(^|\n)\s*[-•]\s+", t):
        return True
    if re.search(r"(^|\n)\s*(\d+\)|\d+\.|\d+\s*-)\s+", t):
        return True
    if t.count(";") >= 3:
        return True
    return False


def _lexical_score(
    *,
    question: str,
    content: str,
    keywords: Sequence[str],
    phrases: Sequence[str],
    enumeration_intent: bool,
) -> Tuple[float, Dict[str, Any]]:
    c = _normalize_text(content)
    dbg: Dict[str, Any] = {}

    kw_hits: List[str] = []
    for kw in keywords:
        if kw and kw in c:
            kw_hits.append(kw)

    phrase_hits: List[str] = []
    for ph in phrases:
        if ph and ph in c:
            phrase_hits.append(ph)

    score = 0.0

    # Keywords: contribution progressive
    score += min(0.55, 0.12 * len(kw_hits))

    # Phrases (bigrams/trigrams de la question): bonus fort car correspondance lexicale plus précise
    score += min(0.60, 0.25 * len(phrase_hits))

    # Intention d'énumération: privilégier les chunks qui ont une structure de liste
    has_enum = False
    if enumeration_intent and _looks_like_enumeration(content):
        has_enum = True
        score += 0.35

    dbg["kw_hits"] = kw_hits
    dbg["phrase_hits"] = phrase_hits
    dbg["enumeration_intent"] = bool(enumeration_intent)
    dbg["enumeration_like"] = bool(has_enum)
    dbg["lexical_score"] = float(score)
    return float(score), dbg


def _hybrid_rerank(
    *,
    question: str,
    items: List[Dict[str, Any]],
    alpha: float = 0.70,
    beta: float = 0.30,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    keywords = _extract_keywords(question)
    phrases = _extract_phrases(question)
    enum_intent = _has_enumeration_intent(question)

    dbg: Dict[str, Any] = {
        "alpha": float(alpha),
        "beta": float(beta),
        "keywords": keywords,
        "phrases": phrases,
        "enumeration_intent": bool(enum_intent),
        "items": [],
    }

    out: List[Dict[str, Any]] = []
    for it in list(items or []):
        d = dict(it)
        vector = float(d.get("score") or 0.0)
        lex, lex_dbg = _lexical_score(
            question=question,
            content=str(d.get("content") or ""),
            keywords=keywords,
            phrases=phrases,
            enumeration_intent=enum_intent,
        )
        final = (alpha * vector) + (beta * lex)
        d["_vector_score"] = vector
        d["_lexical_score"] = lex
        d["_rerank_score"] = float(final)
        d["_lex_dbg"] = lex_dbg
        out.append(d)

    out.sort(key=lambda x: float(x.get("_rerank_score") or 0.0), reverse=True)
    for d in out[:40]:
        meta = d.get("metadata") or {}
        dbg["items"].append(
            {
                "id": str(d.get("id") or meta.get("_id") or ""),
                "filename": meta.get("filename") or d.get("filename"),
                "chunk_index": meta.get("chunk_index"),
                "vector_score": float(d.get("_vector_score") or 0.0),
                "lexical_score": float(d.get("_lexical_score") or 0.0),
                "final_score": float(d.get("_rerank_score") or 0.0),
                "kw_hits": (d.get("_lex_dbg") or {}).get("kw_hits"),
                "phrase_hits": (d.get("_lex_dbg") or {}).get("phrase_hits"),
                "enumeration_like": (d.get("_lex_dbg") or {}).get("enumeration_like"),
            }
        )

    return out, dbg


def _select_diverse(
    *,
    items: List[Dict[str, Any]],
    max_total: int = 12,
    max_per_doc: int = 5,
    min_unique_docs: int = 2,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Sélectionne les meilleurs items rerankés tout en maintenant une diversité inter-documents."""
    selected: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    seen_ids = set()

    def _doc_key(d: Dict[str, Any]) -> str:
        meta = d.get("metadata") or {}
        return str(meta.get("filename") or d.get("filename") or "")

    dbg_rows: List[Dict[str, Any]] = []

    for d in list(items or [])[:200]:
        meta = d.get("metadata") or {}
        sid = str(d.get("id") or meta.get("_id") or "").strip()
        if sid and sid in seen_ids:
            continue
        doc = _doc_key(d)
        doc_count = int(counts.get(doc, 0))

        reason = ""
        accept = True
        if len(selected) >= max_total:
            accept = False
            reason = "max_total_reached"
        elif doc and doc_count >= max_per_doc:
            accept = False
            reason = "max_per_doc"

        if accept:
            selected.append(d)
            counts[doc] = doc_count + 1
            if sid:
                seen_ids.add(sid)
            reason = "selected"

        dbg_rows.append(
            {
                "id": sid,
                "filename": doc,
                "chunk_index": meta.get("chunk_index"),
                "vector_score": float(d.get("_vector_score") or d.get("score") or 0.0),
                "lexical_score": float(d.get("_lexical_score") or 0.0),
                "final_score": float(d.get("_rerank_score") or d.get("score") or 0.0),
                "decision": reason,
            }
        )

    # Si on manque de diversité mais qu'on a suffisamment d'items, on force l'introduction de docs alternatifs.
    try:
        if len({(x.get("metadata") or {}).get("filename") for x in selected if (x.get("metadata") or {}).get("filename")}) < min_unique_docs:
            docs_seen = set((x.get("metadata") or {}).get("filename") for x in selected)
            for d in list(items or [])[:200]:
                meta = d.get("metadata") or {}
                fn = meta.get("filename")
                if fn and fn not in docs_seen:
                    selected.append(d)
                    docs_seen.add(fn)
                if len(selected) >= max_total:
                    break
    except Exception:
        pass

    return selected[:max_total], {"selection": dbg_rows, "counts": counts, "max_total": max_total, "max_per_doc": max_per_doc}


@dataclass
class _StructuredRagAnswer:
    answer: str
    direct_answer: str
    reference: Dict[str, str]
    grounded_summary: List[str]
    helpful_explanation: str
    expert_explanation: str
    operational_impact: List[str]
    limitations: str


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    t = (text or "").strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Tolérance: le modèle peut entourer le JSON avec du texte.
    try:
        m = re.search(r"\{[\s\S]*\}", t)
        if not m:
            return None
        obj = json.loads(m.group(0))
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None

    return None


def _coerce_structured_answer(payload: Optional[Dict[str, Any]], *, fallback_answer: str) -> _StructuredRagAnswer:
    if not isinstance(payload, dict):
        return _StructuredRagAnswer(
            answer=(fallback_answer or "").strip(),
            direct_answer="",
            reference={"textName": "", "textNumber": "", "article": "", "section": "", "scope": ""},
            grounded_summary=[],
            helpful_explanation="",
            expert_explanation="",
            operational_impact=[],
            limitations="",
        )

    def _as_str(x: Any) -> str:
        return ("" if x is None else str(x)).strip()

    def _as_list_str(x: Any) -> List[str]:
        if not x:
            return []
        if isinstance(x, list):
            out: List[str] = []
            for it in x:
                s = _as_str(it)
                if s:
                    out.append(s)
            return out
        s = _as_str(x)
        return [s] if s else []

    def _as_ref(x: Any) -> Dict[str, str]:
        if not isinstance(x, dict):
            return {"textName": "", "textNumber": "", "article": "", "section": "", "scope": ""}
        return {
            "textName": _as_str(x.get("textName")),
            "textNumber": _as_str(x.get("textNumber")),
            "article": _as_str(x.get("article")),
            "section": _as_str(x.get("section")),
            "scope": _as_str(x.get("scope")),
        }

    ans = _as_str(payload.get("answer")) or (fallback_answer or "").strip()
    direct_answer = _as_str(payload.get("direct_answer"))
    reference = _as_ref(payload.get("reference"))
    grounded_summary = _as_list_str(payload.get("grounded_summary"))
    helpful_explanation = _as_str(payload.get("helpful_explanation"))
    expert_explanation = _as_str(payload.get("expert_explanation"))
    operational_impact = _as_list_str(payload.get("operational_impact"))
    limitations = _as_str(payload.get("limitations"))

    return _StructuredRagAnswer(
        answer=ans,
        direct_answer=direct_answer,
        reference=reference,
        grounded_summary=grounded_summary,
        helpful_explanation=helpful_explanation,
        expert_explanation=expert_explanation,
        operational_impact=operational_impact,
        limitations=limitations,
    )


def _reference_supported_by_excerpts(reference: Dict[str, str], excerpts_text: str) -> bool:
    """Heuristique anti-hallucination: n'accepte une référence que si elle est visible dans les extraits."""
    try:
        t = (excerpts_text or "").lower()
        if not t:
            return False

        text_name = (reference.get("textName") or "").strip()
        text_number = (reference.get("textNumber") or "").strip()
        article = (reference.get("article") or "").strip()
        section = (reference.get("section") or "").strip()

        # Si on ne fournit aucune info, c'est OK (pas de référence détectée)
        if not any([text_name, text_number, article, section]):
            return True

        # Support minimal: si un numéro/identifiant est donné, il doit apparaitre.
        if text_number and (text_number.lower() not in t):
            return False

        # Article: tolère "Article 12" ou "Art. 12".
        if article:
            m = re.search(r"(\d+)", article)
            if m:
                num = m.group(1)
                pat = re.compile(rf"\b(?:article|art\.?)(?:[\s\n\r\t\u00A0])*{re.escape(num)}\b", flags=re.IGNORECASE)
                if not pat.search(excerpts_text or ""):
                    return False
            else:
                if article.lower() not in t:
                    return False

        # Section: si renseignée, doit être visible textuellement
        if section and (section.lower() not in t):
            return False

        # textName: on ne force pas une correspondance stricte (risque de variations),
        # mais si renseigné, on attend au moins un fragment significatif.
        if text_name:
            frag = text_name.lower().strip()
            if len(frag) >= 12 and frag not in t:
                # tolérance: on cherche les 2-3 premiers mots
                head = " ".join([w for w in re.split(r"\s+", frag) if w][:3]).strip()
                if head and head not in t:
                    return False

        return True
    except Exception:
        return False


def _build_sources_used(sources: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    used: List[Dict[str, Any]] = []
    seen = set()
    for s in list(sources or [])[:20]:
        meta = s.get("metadata") or {}
        scope = (s.get("scope") or meta.get("scope") or "").strip().upper() or None
        fn = (meta.get("filename") or s.get("filename") or meta.get("source") or meta.get("title") or "").strip()
        if not fn:
            continue
        key = (scope, fn)
        if key in seen:
            continue
        seen.add(key)

        page = meta.get("page") or meta.get("page_number") or meta.get("pageIndex")
        page_int: Optional[int] = None
        try:
            if page is not None:
                page_int = int(page)
        except Exception:
            page_int = None

        used.append(
            {
                "documentName": fn,
                "category": meta.get("category"),
                "scope": scope or "",
                "page": page_int,
            }
        )
    return used


def _structured_too_short(s: Optional[_StructuredRagAnswer]) -> bool:
    if not s:
        return True
    try:
        ans_len = len((s.answer or "").strip())
        expl_len = len((s.expert_explanation or s.helpful_explanation or "").strip())
        gs_len = len([x for x in (s.grounded_summary or []) if str(x).strip()])
        lim_len = len((s.limitations or "").strip())
        op_len = len([x for x in (s.operational_impact or []) if str(x).strip()])
        if gs_len < 3:
            return True
        if ans_len < 280:
            return True
        if expl_len < 900:
            return True
        if op_len < 5:
            return True
        if lim_len < 80:
            return True
    except Exception:
        return True
    return False


def _is_article_query(question: str) -> bool:
    q_norm = (question or "").lower()
    q_norm = q_norm.replace("’", "'")
    q_norm = re.sub(r"\s+", " ", q_norm).strip()
    try:
        fr_numbers = {
            "un": "1",
            "une": "1",
            "deux": "2",
            "trois": "3",
            "quatre": "4",
            "cinq": "5",
            "six": "6",
            "sept": "7",
            "huit": "8",
            "neuf": "9",
            "dix": "10",
        }
        m1 = re.search(r"\b(?:article|art\.?)(?:\s|\u00A0)+\d+\b", q_norm, flags=re.IGNORECASE)
        if m1:
            return True
        m2 = re.search(r"\b(?:article|art\.?)(?:\s|\u00A0)+([a-zà-ÿ]+)\b", q_norm, flags=re.IGNORECASE)
        if m2 and fr_numbers.get((m2.group(1) or "").strip().lower()):
            return True
    except Exception:
        return False
    return False


def _chunk_preview(items: Sequence[Dict[str, Any]], max_items: int = 8) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in list(items)[:max_items]:
        meta = s.get("metadata") or {}
        out.append(
            {
                "id": s.get("id"),
                "scope": s.get("scope") or meta.get("scope"),
                "score": float(s.get("score") or 0.0),
                "filename": meta.get("filename") or meta.get("source") or meta.get("title") or s.get("filename"),
                "chunk_index": meta.get("chunk_index") if meta.get("chunk_index") is not None else s.get("chunk_index"),
            }
        )
    return out


def _rerank_by_filename_signals(
    *,
    question: str,
    items: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    q_norm = (question or "").lower()
    q_norm = q_norm.replace("’", "'")
    q_norm = re.sub(r"\s+", " ", q_norm).strip()

    if not items:
        return items, {"enabled": False, "reason": "no_items"}

    # Extraction générique de mots-clés depuis la question (pas de liste hardcodée).
    # On enlève les mots trop génériques pour éviter de re-ranker sur "article", "instruction", etc.
    tokens = re.findall(r"[a-zà-ÿ0-9']{4,}", q_norm)
    stop = {
        "avec",
        "aussi",
        "alors",
        "ainsi",
        "aucune",
        "avoir",
        "comme",
        "comment",
        "concernant",
        "dans",
        "donne",
        "donner",
        "entre",
        "expliquer",
        "explique",
        "faire",
        "merci",
        "pourquoi",
        "quels",
        "quelles",
        "quel",
        "quelle",
        "relative",
        "relatif",
        "relatives",
        "sujet",
        "toutes",
        "tout",
        "toute",
        "votre",
        "vous",
        "article",
        "instruction",
        "instructions",
        "information",
        "informations",
        "modalites",
        "modalités",
        "relative",
        "relatif",
    }

    keywords: List[str] = []
    seen_kw: set[str] = set()
    for t in tokens:
        if t in stop or t in seen_kw:
            continue
        seen_kw.add(t)
        keywords.append(t)
        if len(keywords) >= 8:
            break

    if not keywords:
        return items, {"enabled": False, "reason": "no_keywords"}

    # Petites phrases (bigrams/trigrams) basées sur les keywords présentes dans la question
    phrases: List[str] = []
    for n in (3, 2):
        for i in range(0, len(keywords) - n + 1):
            phrases.append(" ".join(keywords[i : i + n]))
    phrases = phrases[:6]

    before_top = [((it.get("metadata") or {}).get("filename") or "") for it in items[:5]]

    scored: List[Tuple[int, float, int, Dict[str, Any]]] = []
    for i, it in enumerate(items):
        meta = it.get("metadata") or {}
        fn_norm = (meta.get("filename") or "").lower().replace("’", "'")
        fn_norm = re.sub(r"\s+", " ", fn_norm).strip()
        # Score de re-ranking: match phrases (plus fort) + match keywords
        phrase_hits = sum(1 for p in phrases if p and p in fn_norm)
        kw_hits = sum(1 for t in keywords if t and t in fn_norm)
        match = (phrase_hits * 3) + kw_hits
        sc = float(it.get("score") or 0.0)
        # tri: match desc, score desc, index asc (stabilité)
        scored.append((match, sc, -i, it))

    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    reranked = [x[3] for x in scored]
    after_top = [((it.get("metadata") or {}).get("filename") or "") for it in reranked[:5]]

    return reranked, {
        "enabled": True,
        "keywords": keywords,
        "phrases": phrases,
        "before_top_filenames": before_top,
        "after_top_filenames": after_top,
    }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _stable_chunk_id(
    *,
    scope: str,
    user_id: Optional[str],
    organization_id: Optional[str],
    category: Optional[str],
    filename: str,
    chunk_index: int,
    content: str,
) -> str:
    """Génère un identifiant stable pour permettre l'upsert."""

    base = (
        f"{scope}|{organization_id or ''}|{user_id or ''}|{category or ''}|{filename}|{chunk_index}|{content}"
    ).encode("utf-8")
    return hashlib.sha256(base).hexdigest()


def _get_pymongo_collection(collection_name: str):
    """Retourne une collection PyMongo (sync)."""

    from pymongo import MongoClient

    uri = str(MONGODB_URI or "").strip()
    kwargs: Dict[str, Any] = {}

    # Atlas (mongodb+srv) requiert TLS. Sur certains environnements Windows/proxy, la validation OCSP peut échouer.
    # On active TLS + CA certifi quand on détecte un URI SRV.
    if uri.lower().startswith("mongodb+srv://"):
        kwargs["tls"] = True
        try:
            import certifi

            kwargs["tlsCAFile"] = certifi.where()
        except Exception:
            pass

        disable_ocsp = (os.getenv("RAG_NEW_MONGO_TLS_DISABLE_OCSP", "1") or "1").strip().lower() in {"1", "true", "yes", "on"}
        if disable_ocsp:
            kwargs["tlsDisableOCSPEndpointCheck"] = True

    client = MongoClient(uri, **kwargs)
    return client[MONGODB_DB][collection_name]


def _get_chunk_by_id_sync(*, collection_name: str, chunk_id: str) -> Optional[Dict[str, Any]]:
    col = _get_pymongo_collection(collection_name)
    try:
        return col.find_one({"_id": chunk_id})
    except Exception:
        return None


def _get_neighbor_chunks_sync(
    *,
    collection_name: str,
    scope: str,
    organization_id: Optional[str],
    category: Optional[str],
    filename: str,
    chunk_index: int,
    window: int,
    limit: int,
) -> List[Dict[str, Any]]:
    col = _get_pymongo_collection(collection_name)

    q: Dict[str, Any] = {
        "scope": scope,
        "filename": filename,
        "chunk_index": {"$gte": max(0, int(chunk_index) - int(window)), "$lte": int(chunk_index) + int(window)},
    }
    if scope == "LOCAL" and organization_id:
        q["organization_id"] = organization_id
    if category:
        q["category"] = category

    docs = list(col.find(q).sort("chunk_index", 1).limit(int(limit)))
    out: List[Dict[str, Any]] = []
    for d in docs:
        out.append(
            {
                "id": str(d.get("_id") or ""),
                "content": d.get("content") or "",
                "score": 0.0,
                "metadata": {
                    "_id": str(d.get("_id") or ""),
                    "scope": d.get("scope"),
                    "category": d.get("category"),
                    "organization_id": d.get("organization_id"),
                    "filename": d.get("filename"),
                    "chunk_index": d.get("chunk_index"),
                },
                "scope": scope,
            }
        )
    return out


def _get_embeddings() -> "OpenAIEmbeddings":
    """Crée l'objet embeddings OpenAI (sync)."""

    from langchain_openai import OpenAIEmbeddings

    # dimensions est supporté par text-embedding-3-* (optionnel)
    return OpenAIEmbeddings(model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS)


def _get_llm() -> "ChatOpenAI":
    """Crée l'objet LLM (sync)."""

    from langchain_openai import ChatOpenAI

    model = os.getenv("RAG_NEW_LLM_MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("RAG_NEW_LLM_TEMPERATURE", "0.2"))

    return ChatOpenAI(model=model, temperature=temperature)


def _split_text_recursive(text: str) -> List[str]:
    """Chunking via RecursiveCharacterTextSplitter."""

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    t = text or ""
    t = t.replace("\r\n", "\n")
    t = re.sub(r"[\t\u00A0]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"\s+", " ", t.replace("\n\n", "\n\n__PARA__\n\n")).replace(" __PARA__ ", "\n\n")
    t = re.sub(r"(?i)(?<!\n\n)\b(article\s+\d+)\b", r"\n\n\1", t)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=180,
        separators=[
            "\n\n",
            "\n",
            ". ",
            "; ",
            " : ",
            ": ",
            " – ",
            " - ",
            " ",
            "",
        ],
    )
    chunks = splitter.split_text(t)

    try:
        too_small = [c for c in chunks if len((c or "").strip()) < 100]
        too_large = [c for c in chunks if len((c or "").strip()) > 900]
        if too_small or too_large:
            logger.warning(
                "RAG_CHUNKING_WARN total=%s too_small=%s too_large=%s sample_sizes=%s",
                len(chunks),
                len(too_small),
                len(too_large),
                [len((c or "").strip()) for c in (too_small[:2] + too_large[:2])],
            )
    except Exception:
        pass

    return chunks


def _extract_text_from_upload(filename: str, raw_bytes: bytes) -> str:
    """Extraction minimaliste.

    - .txt: UTF-8 (fallback latin-1)
    - .pdf: nécessite pypdf (ou PyPDF2). Si absent, lève une erreur explicite.

    Note: cette extraction est *distincte* de l'existant et ne le remplace pas.
    """

    ext = os.path.splitext(filename.lower())[1]

    if ext in {".txt", ".md", ".csv"}:
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return raw_bytes.decode("latin-1", errors="ignore")

    if ext == ".docx":
        try:
            from docx import Document
        except Exception as e:
            raise ValueError(
                "Extraction DOCX indisponible: installe 'python-docx' (pip install python-docx)."
            ) from e

        import io

        doc = Document(io.BytesIO(raw_bytes))
        parts: List[str] = []
        for p in doc.paragraphs:
            t = (p.text or "").strip()
            if t:
                parts.append(t)
        return "\n".join(parts).strip()

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception as e:
            raise ValueError(
                "Extraction PDF indisponible: installe 'pypdf' (pip install pypdf)."
            ) from e

        import io

        reader = PdfReader(io.BytesIO(raw_bytes))
        pages_text: List[str] = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                pages_text.append(t)
        extracted = "\n\n".join(pages_text).strip()
        if extracted:
            return extracted

        enable_ocr = (os.getenv("RAG_NEW_ENABLE_OCR", "false").strip().lower() in {"1", "true", "yes"})
        if not enable_ocr:
            raise ValueError(
                "Aucun texte n'a pu être extrait du PDF. "
                "Si le PDF est scanné (image), il faut un OCR ou un PDF 'texte'."
            )

        return _ocr_pdf_scanned(raw_bytes)

    raise ValueError(f"Type de fichier non supporté pour l'instant: {ext}")


def _ocr_pdf_scanned(raw_bytes: bytes) -> str:
    try:
        import fitz  # type: ignore
    except Exception as e:
        raise ValueError(
            "OCR PDF indisponible: installe 'pymupdf' (pip install pymupdf)."
        ) from e

    try:
        import pytesseract  # type: ignore
    except Exception as e:
        import sys
        raise ValueError(
            "OCR PDF indisponible: installe 'pytesseract' dans l'environnement Python qui exécute l'API. "
            f"Python utilisé: {sys.executable}. "
            "Commande: python -m pip install pytesseract pillow"
        ) from e

    try:
        from PIL import Image  # type: ignore
    except Exception as e:
        raise ValueError(
            "OCR PDF indisponible: installe 'pillow' (pip install pillow)."
        ) from e

    tesseract_cmd = os.getenv("RAG_NEW_TESSERACT_CMD", "").strip()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    max_pages = int(os.getenv("RAG_NEW_OCR_MAX_PAGES", "10"))
    ocr_lang = os.getenv("RAG_NEW_OCR_LANG", "fra").strip() or "fra"
    tessdata_prefix = os.getenv("TESSDATA_PREFIX", "").strip()

    doc = fitz.open(stream=raw_bytes, filetype="pdf")
    parts: List[str] = []

    page_count = min(len(doc), max_pages)
    for i in range(page_count):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        try:
            txt = pytesseract.image_to_string(img, lang=ocr_lang) or ""
        except Exception as e:
            msg = str(e)
            if "TesseractNotFoundError" in msg or "tesseract is not installed" in msg.lower() or "can't find tesseract" in msg.lower():
                raise ValueError(
                    "OCR PDF: Tesseract n'est pas installé (ou introuvable). "
                    "Installe Tesseract-OCR sur la machine, ou définis RAG_NEW_TESSERACT_CMD "
                    "avec le chemin vers tesseract.exe."
                ) from e
            if "error opening data file" in msg.lower() or "failed loading language" in msg.lower():
                raise ValueError(
                    "OCR PDF: langue OCR introuvable côté Tesseract. "
                    f"Langue demandée: '{ocr_lang}'. "
                    "Assure-toi que le fichier '<lang>.traineddata' existe dans le dossier 'tessdata'. "
                    f"TESSDATA_PREFIX actuel: '{tessdata_prefix or '(non défini)'}'. "
                    "Solutions: (1) installer le pack de langue (ex: fra) de Tesseract, "
                    "(2) définir TESSDATA_PREFIX vers le dossier 'tessdata' (ex: 'C:\\Program Files\\Tesseract-OCR\\tessdata'), "
                    "(3) ou changer RAG_NEW_OCR_LANG (ex: 'eng')."
                ) from e
            raise
        txt = txt.strip()
        if txt:
            parts.append(txt)

    extracted = "\n\n".join(parts).strip()
    if not extracted:
        raise ValueError(
            "OCR PDF: aucun texte détecté. Vérifie que Tesseract est installé et que le document est lisible."
        )
    return extracted


async def ingest_document(
    *,
    filename: str,
    file_bytes: bytes,
    user_id: Optional[str],
    organization_id: Optional[str] = None,
    category: Optional[str] = None,
    scope: Optional[str] = None,
    metadata: Dict[str, Any],
) -> Tuple[str, int, int, Optional[str], datetime]:
    """Ingestion d'un document dans la nouvelle base RAG.

    - Si user_id est fourni => base locale (knowledge_local)
    - Sinon => base globale (knowledge_global)

    Retourne: (collection_name, document_count, chunk_count, user_id, created_at)
    """

    resolved_scope = scope or ("LOCAL" if user_id else "GLOBAL")
    collection_name = LOCAL_COLLECTION if resolved_scope == "LOCAL" else GLOBAL_COLLECTION

    created_at = _now_utc()

    def _sync_job() -> Tuple[str, int, int, Optional[str], datetime]:
        # 1) Extraction
        text = _extract_text_from_upload(filename, file_bytes)
        if not text.strip():
            raise ValueError("Aucun texte n'a pu être extrait du document")

        # 2) Chunking
        chunks = _split_text_recursive(text)
        if not chunks:
            raise ValueError("Découpage en chunks: aucun chunk généré")

        # 3) Embeddings
        embeddings = _get_embeddings()
        vectors: List[List[float]] = embeddings.embed_documents(chunks)
        if len(vectors) != len(chunks):
            raise ValueError("Nombre d'embeddings différent du nombre de chunks")

        # 4) Upsert dans Mongo
        col = _get_pymongo_collection(collection_name)

        from pymongo import ReplaceOne

        ops = []
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            chunk_id = _stable_chunk_id(
                scope=resolved_scope,
                user_id=user_id,
                organization_id=organization_id,
                category=category,
                filename=filename,
                chunk_index=i,
                content=chunk,
            )

            doc: Dict[str, Any] = {
                "_id": chunk_id,
                "scope": resolved_scope,
                "user_id": user_id,
                "organization_id": organization_id,
                "category": category,
                "filename": filename,
                "chunk_index": i,
                "content": chunk,
                "embedding": vec,
                "metadata": metadata or {},
                "created_at": created_at,
                "updated_at": created_at,
            }

            ops.append(ReplaceOne({"_id": chunk_id}, doc, upsert=True))

        if not ops:
            return (collection_name, 0, 0, user_id, created_at)

        result = col.bulk_write(ops, ordered=False)
        written = int(result.upserted_count + result.modified_count)

        return (collection_name, written, len(chunks), user_id, created_at)

    return await asyncio.to_thread(_sync_job)


async def ingest_text_document(
    *,
    filename: str,
    text: str,
    organization_id: Optional[str] = None,
    category: Optional[str] = None,
    scope: str,
    metadata: Dict[str, Any],
) -> Tuple[str, int, int, datetime]:
    resolved_scope = scope
    collection_name = LOCAL_COLLECTION if resolved_scope == "LOCAL" else GLOBAL_COLLECTION
    created_at = _now_utc()

    def _sync_job() -> Tuple[str, int, int, datetime]:
        if not (text or "").strip():
            raise ValueError("Aucun texte fourni pour l'ingestion")

        chunks = _split_text_recursive(text)
        if not chunks:
            raise ValueError("Découpage en chunks: aucun chunk généré")

        embeddings = _get_embeddings()
        vectors: List[List[float]] = embeddings.embed_documents(chunks)
        if len(vectors) != len(chunks):
            raise ValueError("Nombre d'embeddings différent du nombre de chunks")

        col = _get_pymongo_collection(collection_name)

        from pymongo import ReplaceOne

        ops = []
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            chunk_id = _stable_chunk_id(
                scope=resolved_scope,
                user_id=None,
                organization_id=organization_id,
                category=category,
                filename=filename,
                chunk_index=i,
                content=chunk,
            )

            doc: Dict[str, Any] = {
                "_id": chunk_id,
                "scope": resolved_scope,
                "user_id": None,
                "organization_id": organization_id,
                "category": category,
                "filename": filename,
                "chunk_index": i,
                "content": chunk,
                "embedding": vec,
                "metadata": metadata or {},
                "created_at": created_at,
                "updated_at": created_at,
            }

            ops.append(ReplaceOne({"_id": chunk_id}, doc, upsert=True))

        if not ops:
            return (collection_name, 0, 0, created_at)

        result = col.bulk_write(ops, ordered=False)
        written = int(result.upserted_count + result.modified_count)
        return (collection_name, written, len(chunks), created_at)

    return await asyncio.to_thread(_sync_job)


def _vector_search_sync(
    *,
    collection_name: str,
    index_name: str,
    question: str,
    filter_query: Optional[Dict[str, Any]],
    k: int,
) -> List[Dict[str, Any]]:
    """Recherche Vector Search (sync) via MongoDBAtlasVectorSearch."""

    from langchain_mongodb import MongoDBAtlasVectorSearch

    col = _get_pymongo_collection(collection_name)
    embeddings = _get_embeddings()

    # Vector store LangChain MongoDB Atlas Vector Search
    vs = MongoDBAtlasVectorSearch(
        collection=col,
        embedding=embeddings,
        index_name=index_name,
        text_key="content",
        embedding_key="embedding",
    )

    try:
        # Renvoie: List[Tuple[Document, score]]
        results = vs.similarity_search_with_score(
            query=question,
            k=k,
            pre_filter=filter_query,
        )
    except Exception as e:
        msg = str(e)
        err_code = getattr(e, "code", None)
        if (
            "SearchNotEnabled" in msg
            or '"codeName": "SearchNotEnabled"' in msg
            or "31082" in msg
            or "requires additional configuration" in msg
            or err_code == 31082
        ):
            scope = None
            organization_id = None
            category = None
            if isinstance(filter_query, dict):
                scope = filter_query.get("scope")
                organization_id = filter_query.get("organization_id")
                category = filter_query.get("category")

            logger.warning(
                "MongoDB Atlas Search/Vector Search non activé (fallback regex). collection=%s index=%s scope=%s org=%s category=%s error=%s",
                collection_name,
                index_name,
                scope,
                organization_id,
                category,
                msg,
            )

            return _regex_keyword_search_sync(
                collection_name=collection_name,
                scope=str(scope or ""),
                organization_id=str(organization_id) if organization_id else None,
                category=str(category) if category else None,
                question=question,
                limit=max(1, int(k)),
            )
        if "needs to be indexed as token" in msg and "Path '" in msg:
            import re

            m = re.search(r"Path '([^']+)' needs to be indexed as token", msg)
            field = m.group(1) if m else "(champ inconnu)"
            raise ValueError(
                "MongoDB Atlas Vector Search: le champ utilisé dans le filtre doit être indexé en 'token'. "
                f"Champ manquant: {field}. "
                "Corrige l'index Atlas (collection de connaissance) en ajoutant ce champ dans la section 'filters' en type 'token'. "
                "Champs typiques à indexer en token: scope, category, organization_id."
            ) from e
        raise

    out: List[Dict[str, Any]] = []
    for doc, score in results:
        # doc.metadata doit contenir ce que le VectorStore expose; on garde aussi l'id si possible
        item = {
            "id": str(doc.metadata.get("_id") or doc.metadata.get("id") or ""),
            "content": doc.page_content,
            "score": float(score),
            "metadata": dict(doc.metadata or {}),
        }
        out.append(item)
    return out


def _regex_keyword_search_sync(
    *,
    collection_name: str,
    scope: str,
    organization_id: Optional[str],
    category: Optional[str],
    question: str,
    limit: int,
) -> List[Dict[str, Any]]:
    import re

    col = _get_pymongo_collection(collection_name)

    q_lower = (question or "").lower()

    # 1) Essayer d'abord l'expression exacte (utile pour des termes comme "taux d'usure")
    exact = (question or "").strip()
    exact = re.sub(r"\s+", " ", exact)
    exact = exact.strip("\"' ")

    # 2) Extraire des mots-clés simples et stables
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_'-]{4,}", question or "")
    tokens = [t.lower() for t in tokens if t]

    stop = {
        "avec",
        "aussi",
        "alors",
        "ainsi",
        "aucune",
        "avoir",
        "comme",
        "comment",
        "compte",
        "comptes",
        "concernant",
        "dans",
        "donner",
        "donne",
        "entre",
        "expliquer",
        "explique",
        "faire",
        "merci",
        "pourquoi",
        "quels",
        "quelles",
        "quel",
        "quelle",
        "relatif",
        "relative",
        "relatives",
        "sujet",
        "toutes",
        "tout",
        "toute",
        "votre",
        "vous",
        "article",
        "art",
        "instruction",
        "instructions",
        "information",
        "informations",
    }

    seen = set()
    keywords: List[str] = []
    for t in tokens:
        if t in stop or t in seen:
            continue
        seen.add(t)
        keywords.append(t)
        if len(keywords) >= 3:
            break

    if not exact and not keywords:
        return []

    def _run_find(regex: str) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"scope": scope, "content": {"$regex": regex, "$options": "i"}}
        if scope == "LOCAL":
            q["organization_id"] = organization_id
        if category:
            q["category"] = category

        docs = list(col.find(q).sort("chunk_index", 1).limit(limit))
        out: List[Dict[str, Any]] = []
        for d in docs:
            content = (d.get("content") or "")
            content_low = content.lower()
            present_count = 0
            if keywords:
                for kw in keywords:
                    if kw and kw in content_low:
                        present_count += 1

            if keywords and present_count < 2:
                continue

            artificial_score = 0.0
            if keywords:
                artificial_score = 0.65 + (0.08 * max(0, present_count - 1))
            out.append(
                {
                    "id": str(d.get("_id") or ""),
                    "content": content,
                    "score": artificial_score,
                    "metadata": {
                        "_id": str(d.get("_id") or ""),
                        "scope": d.get("scope"),
                        "category": d.get("category"),
                        "organization_id": d.get("organization_id"),
                        "filename": d.get("filename"),
                        "chunk_index": d.get("chunk_index"),
                    },
                    "scope": scope,
                }
            )
        return out

    if exact and len(exact) >= 6:
        exact_hits = _run_find(re.escape(exact))
        if exact_hits:
            return exact_hits

    if keywords:
        and_regex = "(?=.*" + ")(?=.*".join(re.escape(k) for k in keywords) + ")"
        and_hits = _run_find(and_regex)
        if and_hits:
            return and_hits

        or_regex = "|".join(re.escape(k) for k in keywords)
        return _run_find(or_regex)

    q: Dict[str, Any] = {"scope": scope, "content": {"$regex": re.escape(exact), "$options": "i"}}
    if scope == "LOCAL":
        q["organization_id"] = organization_id
    if category:
        q["category"] = category

    docs = list(col.find(q).sort("chunk_index", 1).limit(limit))
    out: List[Dict[str, Any]] = []
    for d in docs:
        content = (d.get("content") or "")
        content_low = content.lower()
        present_count = 0
        if keywords:
            for kw in keywords:
                if kw and kw in content_low:
                    present_count += 1

        if keywords and present_count < 2:
            continue

        artificial_score = 0.0
        if keywords:
            artificial_score = 0.65 + (0.08 * max(0, present_count - 1))
        out.append(
            {
                "id": str(d.get("_id") or ""),
                "content": content,
                "score": artificial_score,
                "metadata": {
                    "_id": str(d.get("_id") or ""),
                    "scope": d.get("scope"),
                    "category": d.get("category"),
                    "organization_id": d.get("organization_id"),
                    "filename": d.get("filename"),
                    "chunk_index": d.get("chunk_index"),
                },
                "scope": scope,
            }
        )
    return out


async def retrieve_prioritized(
    *,
    question: str,
    organization_id: Optional[str],
    category: Optional[str],
    allow_global: bool,
    k: int = 5,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Récupération priorisée: GLOBAL -> LOCAL -> LLM_ONLY.

    Règles:
    1) Recherche d'abord dans GLOBAL (seuil score > 0.82)
    2) Si pas assez pertinent (moins de 3 docs OU score max < 0.75) -> fallback LOCAL (filtre user_id)
    3) Si toujours rien -> pas de contexte

    Retourne: (strategy, sources, debug)
    """

    debug: Dict[str, Any] = {}
    effective_allow_global = bool(allow_global or FORCE_GLOBAL)
    debug["allow_global"] = bool(allow_global)
    debug["force_global"] = bool(FORCE_GLOBAL)
    debug["effective_allow_global"] = effective_allow_global
    debug["question"] = question
    debug["category"] = category
    debug["organization_id"] = organization_id

    # Ajustement des seuils et du k pour les requêtes d'articles: on favorise le recall.
    is_article_query = _is_article_query(question)
    k_eff = int(k)
    if is_article_query:
        k_eff = max(k_eff, int(ARTICLE_QUERY_K))
    debug["k_effective"] = int(k_eff)
    debug["is_article_query"] = bool(is_article_query)

    global_threshold_eff = float(GLOBAL_RELEVANCE_THRESHOLD)
    local_threshold_eff = float(LOCAL_RELEVANCE_THRESHOLD)
    if is_article_query:
        delta = float(ARTICLE_THRESHOLD_DELTA or 0.0)
        global_threshold_eff = max(0.0, global_threshold_eff - delta)
        local_threshold_eff = max(0.0, local_threshold_eff - delta)
        debug["score_adjusted_for_article"] = True
        debug["article_threshold_delta"] = delta
    debug["global_threshold_effective"] = global_threshold_eff
    debug["local_threshold_effective"] = local_threshold_eff
    debug["global_abs_min_max_score"] = float(GLOBAL_ABS_MIN_MAX_SCORE)
    debug["local_abs_min_max_score"] = float(LOCAL_ABS_MIN_MAX_SCORE)

    # Organisation: GLOBAL d'abord (si autorisé), puis LOCAL, puis LLM_ONLY
    if organization_id:
        global_raw: List[Dict[str, Any]] = []
        global_kept: List[Dict[str, Any]] = []
        global_max = 0.0
        need_local_fallback = True

        if effective_allow_global:
            global_filter: Dict[str, Any] = {"scope": "GLOBAL"}
            if category:
                global_filter["category"] = category

            global_raw = await asyncio.to_thread(
                _vector_search_sync,
                collection_name=GLOBAL_COLLECTION,
                index_name=GLOBAL_VECTOR_INDEX,
                question=question,
                filter_query=global_filter,
                k=k_eff,
            )

            global_raw, rerank_dbg = _rerank_by_filename_signals(question=question, items=list(global_raw))
            debug["global_filename_rerank"] = rerank_dbg

            global_max = max((r.get("score", 0.0) for r in global_raw), default=0.0)
            global_kept = [r for r in global_raw if (r.get("score") or 0.0) >= global_threshold_eff]
            need_local_fallback = (len(global_kept) < GLOBAL_FALLBACK_MIN_DOCS) or (global_max < GLOBAL_FALLBACK_MIN_MAX_SCORE)

            debug["global_raw_count"] = len(global_raw)
            debug["global_kept_count"] = len(global_kept)
            debug["global_max_score"] = global_max
            debug["global_threshold"] = global_threshold_eff
            debug["global_need_local_fallback"] = need_local_fallback
            if DEBUG_CHUNKS:
                debug["global_raw_preview"] = _chunk_preview(global_raw)
                debug["global_kept_preview"] = _chunk_preview(global_kept)
                logger.warning(
                    "RAG_DEBUG_CHUNKS retrieve_prioritized org=%s category=%s q=%r global_raw=%s global_kept=%s",
                    organization_id,
                    category,
                    question,
                    debug["global_raw_preview"],
                    debug["global_kept_preview"],
                )

            if global_kept and not need_local_fallback:
                for r in global_kept:
                    r["scope"] = "GLOBAL"
                return "GLOBAL", global_kept, debug

            # Si aucun chunk ne passe le seuil strict mais que le meilleur score est quand même élevé,
            # on préfère répondre avec les meilleurs résultats globaux plutôt que de tomber en LLM_ONLY.
            if (not is_article_query) and global_raw and global_max >= max(GLOBAL_FALLBACK_MIN_MAX_SCORE, GLOBAL_ABS_MIN_MAX_SCORE):
                for r in global_raw:
                    r["scope"] = "GLOBAL"
                debug["global_below_threshold_used"] = True
                return "GLOBAL", global_raw, debug

            # En organisation, si GLOBAL renvoie des résultats, on peut quand même les préférer
            # sauf si on veut explicitement tenter LOCAL pour compléter.
            debug["global_below_threshold_before_local"] = bool(global_raw)

        # LOCAL
        local_filter: Dict[str, Any] = {"scope": "LOCAL", "organization_id": organization_id}
        if category:
            local_filter["category"] = category

        local_raw = await asyncio.to_thread(
            _vector_search_sync,
            collection_name=LOCAL_COLLECTION,
            index_name=LOCAL_VECTOR_INDEX,
            question=question,
            filter_query=local_filter,
            k=k_eff,
        )

        local_max = max((r.get("score", 0.0) for r in local_raw), default=0.0)
        local_kept = [r for r in local_raw if (r.get("score") or 0.0) >= local_threshold_eff]

        debug["local_raw_count"] = len(local_raw)
        debug["local_kept_count"] = len(local_kept)
        debug["local_max_score"] = local_max
        debug["local_threshold"] = local_threshold_eff
        debug["local_min_max_score"] = LOCAL_FALLBACK_MIN_MAX_SCORE
        if DEBUG_CHUNKS:
            debug["local_raw_preview"] = _chunk_preview(local_raw)
            debug["local_kept_preview"] = _chunk_preview(local_kept)
            logger.warning(
                "RAG_DEBUG_CHUNKS retrieve_prioritized org=%s category=%s q=%r local_raw=%s local_kept=%s",
                organization_id,
                category,
                question,
                debug["local_raw_preview"],
                debug["local_kept_preview"],
            )

        if local_kept:
            for r in local_kept:
                r["scope"] = "LOCAL"
            return "LOCAL", local_kept, debug

        if local_raw and local_max >= max(LOCAL_FALLBACK_MIN_MAX_SCORE, LOCAL_ABS_MIN_MAX_SCORE):
            for r in local_raw:
                r["scope"] = "LOCAL"
            debug["local_below_threshold_used"] = True
            return "LOCAL", local_raw, debug

        return "LLM_ONLY", [], debug

    # 1) GLOBAL
    global_raw: List[Dict[str, Any]] = []
    if effective_allow_global:
        global_filter: Dict[str, Any] = {"scope": "GLOBAL"}
        if category:
            global_filter["category"] = category

        global_raw = await asyncio.to_thread(
            _vector_search_sync,
            collection_name=GLOBAL_COLLECTION,
            index_name=GLOBAL_VECTOR_INDEX,
            question=question,
            filter_query=global_filter,
            k=k_eff,
        )

        global_raw, rerank_dbg = _rerank_by_filename_signals(question=question, items=list(global_raw))
        debug["global_filename_rerank"] = rerank_dbg

    global_max = max((r.get("score", 0.0) for r in global_raw), default=0.0)
    global_kept = [r for r in global_raw if (r.get("score") or 0.0) >= global_threshold_eff]

    debug["global_raw_count"] = len(global_raw)
    debug["global_kept_count"] = len(global_kept)
    debug["global_max_score"] = global_max
    if DEBUG_CHUNKS:
        debug["global_raw_preview"] = _chunk_preview(global_raw)
        debug["global_kept_preview"] = _chunk_preview(global_kept)
        logger.warning(
            "RAG_DEBUG_CHUNKS retrieve_prioritized org=%s category=%s q=%r global_raw=%s global_kept=%s",
            organization_id,
            category,
            question,
            debug["global_raw_preview"],
            debug["global_kept_preview"],
        )

    need_local_fallback = (len(global_kept) < GLOBAL_FALLBACK_MIN_DOCS) or (global_max < GLOBAL_FALLBACK_MIN_MAX_SCORE)

    if global_kept and not need_local_fallback:
        for r in global_kept:
            r["scope"] = "GLOBAL"
        return "GLOBAL", global_kept, debug

    # Sans organisation_id, on ne peut pas faire de fallback LOCAL.
    # Si on a tout de même des résultats globaux raisonnables, on les utilise.
    if (not is_article_query) and global_raw and global_max >= max(GLOBAL_FALLBACK_MIN_MAX_SCORE, GLOBAL_ABS_MIN_MAX_SCORE):
        for r in global_raw:
            r["scope"] = "GLOBAL"
        debug["global_below_threshold_used"] = True
        return "GLOBAL", global_raw, debug

    # Si on a des résultats globaux pertinents mais que le fallback LOCAL est requis,
    # et qu'aucun user_id n'est fourni, on ne peut pas faire de fallback LOCAL.
    # Dans ce cas, on répond quand même avec GLOBAL.
    if global_kept and need_local_fallback and not organization_id:
        for r in global_kept:
            r["scope"] = "GLOBAL"
        debug["local_fallback_skipped"] = True
        return "GLOBAL", global_kept, debug

    # 2) LOCAL (si organization_id fourni)
    if organization_id:
        local_filter: Dict[str, Any] = {"scope": "LOCAL", "organization_id": organization_id}
        if category:
            local_filter["category"] = category

        local_raw = await asyncio.to_thread(
            _vector_search_sync,
            collection_name=LOCAL_COLLECTION,
            index_name=LOCAL_VECTOR_INDEX,
            question=question,
            filter_query=local_filter,
            k=k,
        )

        local_max = max((r.get("score", 0.0) for r in local_raw), default=0.0)
        local_kept = [r for r in local_raw if (r.get("score") or 0.0) >= local_threshold_eff]

        debug["local_raw_count"] = len(local_raw)
        debug["local_kept_count"] = len(local_kept)
        debug["local_max_score"] = local_max
        debug["local_threshold"] = local_threshold_eff

        if local_kept:
            for r in local_kept:
                r["scope"] = "LOCAL"
            return "LOCAL", local_kept, debug

        if local_raw and local_max >= max(LOCAL_FALLBACK_MIN_MAX_SCORE, LOCAL_ABS_MIN_MAX_SCORE):
            for r in local_raw:
                r["scope"] = "LOCAL"
            debug["local_below_threshold_used"] = True
            return "LOCAL", local_raw, debug

    # 3) Rien trouvé
    return "LLM_ONLY", [], debug


def _build_context(sources: Sequence[Dict[str, Any]]) -> str:
    if not sources:
        return ""

    lines: List[str] = []
    for i, s in enumerate(sources, 1):
        meta = s.get("metadata") or {}
        filename = meta.get("filename") or meta.get("source") or meta.get("title") or "Document"
        lines.append(
            f"### Extrait {i} ({s.get('scope')}, score={s.get('score', 0):.3f}, source={filename})\n"
            f"{(s.get('content') or '').strip()}"
        )

    return "\n\n".join(lines)


def _regex_article_search_sync(
    *,
    collection_name: str,
    scope: str,
    organization_id: Optional[str],
    category: Optional[str],
    article_num: str,
    filename: Optional[str],
    filename_is_regex: bool = False,
    document_id: Optional[str] = None,
    limit: int,
) -> List[Dict[str, Any]]:
    col = _get_pymongo_collection(collection_name)

    # Regex tolérante: supporte "Article\n3" ou espaces multiples.
    # On garde une borne de mot autour du numéro pour limiter les faux positifs.
    import re

    # Tolère: "Article 3", "ARTICLE\n3", "Art.\u00A03", etc.
    pat = re.compile(
        rf"\b(?:article|art\.?)(?:[\s\n\r\t\u00A0])*{re.escape(str(article_num))}\b",
        flags=re.IGNORECASE,
    )

    q: Dict[str, Any] = {"scope": scope, "content": {"$regex": pat.pattern, "$options": "i"}}
    if scope == "LOCAL":
        q["organization_id"] = organization_id
    if category:
        q["category"] = category
    # Préférence: filtrage par id de document (si fourni) plutôt que par filename exact.
    if document_id:
        q["metadata.document_id"] = document_id
    elif filename:
        if filename_is_regex:
            q["filename"] = {"$regex": filename, "$options": "i"}
        else:
            q["filename"] = filename

    docs = list(col.find(q).sort("chunk_index", 1).limit(limit))
    out: List[Dict[str, Any]] = []
    for d in docs:
        out.append(
            {
                "id": str(d.get("_id") or ""),
                "content": d.get("content") or "",
                # score élevé car correspondance déterministe
                "score": 0.99,
                "metadata": {
                    "_id": str(d.get("_id") or ""),
                    "scope": d.get("scope"),
                    "category": d.get("category"),
                    "organization_id": d.get("organization_id"),
                    "filename": d.get("filename"),
                    "chunk_index": d.get("chunk_index"),
                },
                "scope": scope,
            }
        )
    return out


async def answer_question(
    *,
    question: str,
    organization_id: Optional[str],
    category: Optional[str],
    allow_global: bool,
) -> Tuple[str, str, List[Dict[str, Any]], Dict[str, Any]]:
    """Répond à une question avec priorisation GLOBAL -> LOCAL -> LLM_ONLY."""

    effective_allow_global = bool(allow_global or FORCE_GLOBAL)

    strategy, sources, debug = await retrieve_prioritized(
        question=question,
        organization_id=organization_id,
        category=category,
        allow_global=allow_global,
    )

    try:
        analysis = analyze_query(question or "")
        if not isinstance(debug, dict):
            debug = {}
        rag_pipeline = debug.get("rag_pipeline")
        if not isinstance(rag_pipeline, dict):
            rag_pipeline = {}
        rag_pipeline.setdefault("meta", {})
        rag_pipeline["query_analysis"] = {
            "analysis": analysis,
        }
        debug["rag_pipeline"] = rag_pipeline
    except Exception:
        pass

    initial_sources: List[Dict[str, Any]] = list(sources or [])

    # Reranking hybride (vectoriel + lexical) pour stabiliser la pertinence avant toute expansion.
    try:
        rr_alpha = float(os.getenv("RAG_NEW_RERANK_ALPHA", "0.70"))
        rr_beta = float(os.getenv("RAG_NEW_RERANK_BETA", "0.30"))
        reranked_initial, rr_dbg = _hybrid_rerank(question=question, items=list(initial_sources), alpha=rr_alpha, beta=rr_beta)
        initial_sources = reranked_initial
        sources = reranked_initial
        debug["hybrid_rerank_initial"] = rr_dbg
    except Exception:
        pass

    # Sélection diversifiée dès le départ (évite qu'un top-1 + expansion écrase d'autres sections/documents).
    try:
        max_total = int(os.getenv("RAG_NEW_FINAL_MAX_CHUNKS", "12"))
        max_per_doc = int(os.getenv("RAG_NEW_FINAL_MAX_PER_DOC", "5"))
        selected0, sel0_dbg = _select_diverse(items=list(sources or []), max_total=max_total, max_per_doc=max_per_doc)
        sources = selected0
        debug["final_selection_pre_neighbors"] = sel0_dbg
    except Exception:
        pass

    # Validation du contexte final (avant génération): métriques pour diagnostiquer les réponses hors-sujet.
    try:
        phrases = _extract_phrases(question)
        keywords = _extract_keywords(question)
        unique_docs = sorted({str((s.get("metadata") or {}).get("filename") or "") for s in (sources or []) if (s.get("metadata") or {}).get("filename")})
        all_text = "\n".join(str(s.get("content") or "") for s in (sources or []))
        all_norm = _normalize_text(all_text)
        phrase_covered = [p for p in phrases if p and p in all_norm]
        kw_covered = [k for k in keywords if k and k in all_norm]
        debug["final_context_validation"] = {
            "unique_docs": unique_docs,
            "unique_docs_count": int(len(unique_docs)),
            "phrases": phrases,
            "keywords": keywords,
            "phrase_covered": phrase_covered,
            "keyword_covered": kw_covered,
            "enumeration_intent": bool(_has_enumeration_intent(question)),
        }
    except Exception:
        pass

    # Intention "liste de documents": si l'utilisateur demande quelles instructions/documents existent dans la base,
    # on retourne une liste de fichiers candidats sans demander au LLM de synthétiser (évite les réponses hors-sujet).
    try:
        import re

        q_norm = (question or "").strip().lower()
        list_intent = False
        if q_norm:
            has_base = ("base de connaissance" in q_norm) or ("base de connaissances" in q_norm) or ("dans ta base" in q_norm) or ("dans votre base" in q_norm)
            has_list = bool(re.search(r"\b(quelles?|liste|quels?)\b", q_norm))
            has_doc_word = bool(re.search(r"\b(instructions?|documents?|textes?)\b", q_norm))
            list_intent = bool(has_base and has_list and has_doc_word)

        if list_intent:
            def _src_filename(s: Optional[Dict[str, Any]]) -> Optional[str]:
                if not isinstance(s, dict):
                    return None
                meta = s.get("metadata") or {}
                return (meta.get("filename") or s.get("filename") or None)

            filenames: List[str] = []
            for s in list(initial_sources or []):
                fn = _src_filename(s)
                if fn and fn not in filenames:
                    filenames.append(fn)
                if len(filenames) >= 12:
                    break

            debug["list_documents_intent"] = True
            debug["list_documents_filenames"] = filenames

            if not filenames:
                return str(RAG_NO_SOURCES_MESSAGE), strategy, [], debug

            lines = [str(RAG_LIST_DOCUMENTS_HEADER)]
            for fn in filenames:
                lines.append(f"- {fn}")
            return "\n".join(lines) + "\n", strategy, initial_sources, debug
    except Exception:
        pass

    if DEBUG_CHUNKS:
        debug["sources_initial_preview"] = _chunk_preview(sources)
        logger.warning(
            "RAG_DEBUG_CHUNKS answer_question initial strategy=%s org=%s category=%s q=%r sources=%s",
            strategy,
            organization_id,
            category,
            question,
            debug["sources_initial_preview"],
        )

    article_requested = False
    locked_filename_for_article: Optional[str] = None
    article_num_for_guardrail: Optional[str] = None
    article_whole_doc_regex_attempted: bool = False
    article_whole_doc_regex_hits: int = 0

    # Si la question vise explicitement un article (ex: "article 2"), on force des extraits pertinents.
    # 1) Filtrage dans les sources vectorielles
    # 2) Si aucun extrait ne contient l'article demandé, fallback regex MongoDB (déterministe)
    try:
        import re

        def _src_filename(s: Optional[Dict[str, Any]]) -> Optional[str]:
            if not isinstance(s, dict):
                return None
            meta = s.get("metadata") or {}
            return (meta.get("filename") or s.get("filename") or None)

        fr_numbers = {
            "un": "1",
            "une": "1",
            "deux": "2",
            "trois": "3",
            "quatre": "4",
            "cinq": "5",
            "six": "6",
            "sept": "7",
            "huit": "8",
            "neuf": "9",
            "dix": "10",
        }

        def _extract_article_num(q: str) -> Optional[str]:
            m1 = re.search(r"\b(?:article|art\.?)(?:\s|\u00A0)+(\d+)\b", q, flags=re.IGNORECASE)
            if m1:
                return m1.group(1)
            m2 = re.search(r"\b(?:article|art\.?)(?:\s|\u00A0)+([A-Za-zÀ-ÖØ-öø-ÿ]+)\b", q, flags=re.IGNORECASE)
            if m2:
                w = (m2.group(1) or "").strip().lower()
                return fr_numbers.get(w)
            return None

        article_num = _extract_article_num(question or "")
        if article_num:
            article_requested = True
            article_num_for_guardrail = str(article_num)
            debug["article_requested"] = True
            debug["article_num"] = str(article_num)
            pat = re.compile(
                rf"\b(?:article|art\.?)(?:[\s\n\r\t\u00A0])*{re.escape(str(article_num))}\b",
                flags=re.IGNORECASE,
            )

            # Verrouillage "thème": on force le document majoritaire (ou top-1) parmi les sources vectorielles initiales.
            # Objectif: ne jamais basculer vers un autre PDF juste parce qu'il contient "Article X" ailleurs.
            try:
                fn_counts: Dict[str, int] = {}
                for s in list(initial_sources or [])[:50]:
                    fn = _src_filename(s)
                    if not fn:
                        continue
                    fn_counts[fn] = int(fn_counts.get(fn, 0)) + 1
                majority_filename = None
                if fn_counts:
                    majority_filename = sorted(fn_counts.items(), key=lambda kv: (kv[1], str(kv[0])), reverse=True)[0][0]
                top1_filename = _src_filename((initial_sources or [None])[0]) if initial_sources else None
                preferred_from_sources = majority_filename or top1_filename
                debug["article_preferred_from_sources"] = {
                    "majority_filename": majority_filename,
                    "top1_filename": top1_filename,
                    "counts": fn_counts,
                    "chosen": preferred_from_sources,
                }
                if preferred_from_sources:
                    locked_filename_for_article = str(preferred_from_sources)
                    debug["article_locked_filename_from_sources"] = locked_filename_for_article
            except Exception:
                pass

            # 0) Chercher l'article déterministiquement dans le document verrouillé par thème.
            try:
                topic_query = re.sub(
                    r"\b(?:article|art\.?)(?:\s|\u00A0)+(?:\d+|[A-Za-zÀ-ÖØ-öø-ÿ]+)\b",
                    " ",
                    question or "",
                    flags=re.IGNORECASE,
                )
                topic_query = re.sub(r"\s+", " ", (topic_query or "")).strip()
                debug["article_topic_query"] = topic_query

                topic_candidates: List[Dict[str, Any]] = []
                if topic_query:
                    if effective_allow_global:
                        global_filter: Dict[str, Any] = {"scope": "GLOBAL"}
                        if category:
                            global_filter["category"] = category
                        topic_candidates.extend(
                            await asyncio.to_thread(
                                _vector_search_sync,
                                collection_name=GLOBAL_COLLECTION,
                                index_name=GLOBAL_VECTOR_INDEX,
                                question=topic_query,
                                filter_query=global_filter,
                                k=8,
                            )
                        )
                    if organization_id:
                        local_filter: Dict[str, Any] = {"scope": "LOCAL", "organization_id": organization_id}
                        if category:
                            local_filter["category"] = category
                        topic_candidates.extend(
                            await asyncio.to_thread(
                                _vector_search_sync,
                                collection_name=LOCAL_COLLECTION,
                                index_name=LOCAL_VECTOR_INDEX,
                                question=topic_query,
                                filter_query=local_filter,
                                k=8,
                            )
                        )

                def _topic_filename(s: Optional[Dict[str, Any]]) -> Optional[str]:
                    if not isinstance(s, dict):
                        return None
                    meta = s.get("metadata") or {}
                    return (meta.get("filename") or s.get("filename") or None)

                def _topic_document_id(s: Optional[Dict[str, Any]]) -> Optional[str]:
                    if not isinstance(s, dict):
                        return None
                    meta = s.get("metadata") or {}
                    did = meta.get("document_id") or meta.get("documentId") or meta.get("doc_id")
                    return str(did) if did else None

                def _topic_scope(s: Optional[Dict[str, Any]]) -> Optional[str]:
                    if not isinstance(s, dict):
                        return None
                    meta = s.get("metadata") or {}
                    return (s.get("scope") or meta.get("scope") or None)

                preferred_filename: Optional[str] = locked_filename_for_article
                preferred_scope: Optional[str] = (strategy or "").upper() if (strategy or "") else None
                preferred_document_id: Optional[str] = None

                # Si on a un document_id dans les sources initiales (cas ORG_DOCUMENT), on le réutilise.
                try:
                    if initial_sources:
                        meta0 = (initial_sources[0] or {}).get("metadata") or {}
                        did0 = meta0.get("document_id") or meta0.get("documentId") or meta0.get("doc_id")
                        if did0:
                            preferred_document_id = str(did0)
                except Exception:
                    pass

                debug["article_preferred_from_topic"] = {
                    "filename": preferred_filename,
                    "scope": preferred_scope,
                    "document_id": preferred_document_id,
                }

                # Tentative déterministe dans le document préféré (thème)
                if preferred_filename and preferred_scope in {"GLOBAL", "LOCAL"}:
                    article_whole_doc_regex_attempted = True

                    # Filename en regex (tolère petites variations / tronquage côté client)
                    # Match plus tolérant (pas d'ancre '^') pour éviter les faux négatifs sur variations de nom.
                    try:
                        fn_prefix = str(preferred_filename)[:80]
                        fn_pat = re.escape(fn_prefix)
                    except Exception:
                        fn_pat = None

                    hits_pref = await asyncio.to_thread(
                        _regex_article_search_sync,
                        collection_name=(GLOBAL_COLLECTION if preferred_scope == "GLOBAL" else LOCAL_COLLECTION),
                        scope=str(preferred_scope),
                        organization_id=(organization_id if preferred_scope == "LOCAL" else None),
                        category=category,
                        article_num=str(article_num),
                        filename=(fn_pat or str(preferred_filename)),
                        filename_is_regex=bool(fn_pat),
                        document_id=preferred_document_id,
                        limit=60,
                    )
                    if hits_pref:
                        article_whole_doc_regex_hits = len(hits_pref)
                        sources = list(hits_pref)
                        strategy = str(preferred_scope)
                        debug["article_regex_scope"] = preferred_scope
                        debug["article_regex_filename_filter"] = preferred_filename
                        debug["article_regex_document_id_filter"] = preferred_document_id
                        debug["article_regex_filename_regex"] = (fn_pat or None)
                        debug["article_regex_topic_first"] = True
            except Exception:
                pass

            # IMPORTANT: on ne filtre plus les résultats vectoriels par présence de "Article X" pour choisir le document.
            # Cette logique conduisait à verrouiller le mauvais PDF (un autre document peut contenir "Article X").

            # Si on a déjà une source "best" (vector), on peut verrouiller sur ce filename pour éviter de mélanger,
            # mais uniquement si on n'a pas déjà verrouillé via les sources initiales.
            locked_filename: Optional[str] = None
            if sources and not locked_filename_for_article:
                try:
                    locked_filename = _src_filename(sources[0])
                except Exception:
                    locked_filename = None

            debug["article_locked_filename_candidate"] = locked_filename

            # Le vector store peut renvoyer un objet sans metadata; on récupère alors le chunk en base
            # pour obtenir le filename exact stocké dans Mongo (évite les mismatch et les bascules).
            try:
                if sources and ((not locked_filename) or not isinstance(locked_filename, str)):
                    best0 = sources[0] or {}
                    best0_id = str(best0.get("id") or (best0.get("metadata") or {}).get("_id") or "").strip()
                    best0_scope = (best0.get("scope") or (best0.get("metadata") or {}).get("scope") or strategy or "").upper()
                    if best0_id and best0_scope in {"GLOBAL", "LOCAL"}:
                        collection_name = GLOBAL_COLLECTION if best0_scope == "GLOBAL" else LOCAL_COLLECTION
                        chunk_doc = await asyncio.to_thread(
                            _get_chunk_by_id_sync,
                            collection_name=collection_name,
                            chunk_id=best0_id,
                        )
                        if chunk_doc and chunk_doc.get("filename"):
                            locked_filename = str(chunk_doc.get("filename"))
                            debug["article_locked_filename_from_mongo"] = locked_filename
            except Exception:
                pass

            if locked_filename and not locked_filename_for_article:
                locked_filename_for_article = locked_filename

            if sources and locked_filename:
                before_lock = len(sources)
                sources = [s for s in sources if (_src_filename(s) == locked_filename)]
                debug["article_filename_lock"] = True
                debug["article_filename"] = locked_filename
                debug["sources_before_article_filename_lock"] = before_lock
                debug["sources_after_article_filename_lock"] = len(sources)

            if not sources or not any(pat.search((s.get("content") or "")) for s in sources):
                debug["article_regex_fallback"] = f"article {article_num}"

                # Exploration multi-documents: on prend plusieurs documents candidats issus de la recherche vectorielle
                # et on tente une recherche déterministe "Article X" dans chacun.
                try:
                    candidates: List[str] = []
                    scores_by_fn: Dict[str, List[float]] = {}
                    all_scores: List[float] = []

                    for s in list(initial_sources or [])[:30]:
                        fn = _src_filename(s)
                        if not fn:
                            continue
                        sc = float(s.get("score") or 0.0)
                        all_scores.append(sc)
                        scores_by_fn.setdefault(fn, []).append(sc)
                        if fn not in candidates:
                            candidates.append(fn)
                        if len(candidates) >= 8:
                            break

                    preferred = locked_filename_for_article or locked_filename
                    # Ne jamais basculer vers un autre document juste parce qu'il contient l'article.
                    # Si un document est verrouillé, la recherche déterministe doit rester dans ce document.
                    if preferred:
                        candidates = [preferred]

                    debug["article_regex_candidates"] = candidates

                    overall_max = max(all_scores, default=0.0)
                    near_delta = 0.03
                    near_threshold = max(0.0, overall_max - near_delta)

                    def _vector_stats(fn: str) -> Dict[str, Any]:
                        vals = scores_by_fn.get(fn) or []
                        if not vals:
                            return {"count": 0, "max": 0.0, "mean": 0.0, "near_count": 0}
                        v_max = max(vals)
                        v_mean = sum(vals) / max(1, len(vals))
                        v_near = sum(1 for v in vals if v >= near_threshold)
                        return {"count": len(vals), "max": float(v_max), "mean": float(v_mean), "near_count": int(v_near)}

                    # Si le document préféré (issu du vector search par thème) domine,
                    # on évite de basculer vers un autre PDF juste parce que la regex trouve un "Article X" ailleurs.
                    try:
                        dominance_delta = 0.015
                        if preferred:
                            st_pref = _vector_stats(preferred)
                            debug["article_preferred_filename"] = preferred
                            debug["article_preferred_vector_max"] = float(st_pref.get("max") or 0.0)
                            debug["article_overall_vector_max"] = float(overall_max or 0.0)
                            if float(st_pref.get("max") or 0.0) >= float(overall_max or 0.0) - dominance_delta:
                                debug["article_preferred_filename_dominates"] = True
                                candidates = [preferred]
                                debug["article_regex_candidates_restricted"] = True
                    except Exception:
                        pass

                    ranking: List[Dict[str, Any]] = []
                    best_choice: Optional[Dict[str, Any]] = None

                    async def _regex_hits(scope_name: str, fn: str) -> List[Dict[str, Any]]:
                        if scope_name == "GLOBAL":
                            return await asyncio.to_thread(
                                _regex_article_search_sync,
                                collection_name=GLOBAL_COLLECTION,
                                scope="GLOBAL",
                                organization_id=None,
                                category=category,
                                article_num=article_num,
                                filename=fn,
                                document_id=None,
                                limit=5,
                            )
                        return await asyncio.to_thread(
                            _regex_article_search_sync,
                            collection_name=LOCAL_COLLECTION,
                            scope="LOCAL",
                            organization_id=organization_id,
                            category=category,
                            article_num=article_num,
                            filename=fn,
                            document_id=None,
                            limit=5,
                        )

                    scopes_to_try: List[str] = []
                    if effective_allow_global:
                        scopes_to_try.append("GLOBAL")
                    if organization_id:
                        scopes_to_try.append("LOCAL")

                    for scope_name in scopes_to_try:
                        for fn in candidates:
                            hits = await _regex_hits(scope_name, fn)
                            st = _vector_stats(fn)
                            hit_count = len(hits)

                            # Ranking demandé:
                            # 1) si regex hit, choisir le meilleur doc par score vectoriel (max puis mean)
                            # 2) sinon, choisir le doc avec le plus de chunks "proches" (near_count)
                            if hit_count > 0:
                                rank_score = (st["max"] * 100.0) + (st["mean"] * 10.0) + min(9, hit_count)
                            else:
                                rank_score = (st["near_count"] * 10.0) + (st["max"] * 10.0) + (st["mean"])

                            row = {
                                "scope": scope_name,
                                "filename": fn,
                                "regex_hit_count": int(hit_count),
                                "vector_count": int(st["count"]),
                                "vector_max": float(st["max"]),
                                "vector_mean": float(st["mean"]),
                                "vector_near_count": int(st["near_count"]),
                                "near_threshold": float(near_threshold),
                                "rank_score": float(rank_score),
                            }
                            ranking.append(row)

                            if hit_count > 0:
                                cand = {"scope": scope_name, "filename": fn, "hits": hits, "rank_score": rank_score, "row": row}
                                if (best_choice is None) or (float(cand.get("rank_score") or 0.0) > float(best_choice.get("rank_score") or 0.0)):
                                    best_choice = cand

                    # Si on n'a aucun hit regex, on choisit le meilleur doc selon la proximité vectorielle
                    if best_choice is None and ranking:
                        ranking_sorted = sorted(ranking, key=lambda r: float(r.get("rank_score") or 0.0), reverse=True)
                        top = ranking_sorted[0]
                        chosen_fn = str(top.get("filename") or "")
                        chosen_scope = str(top.get("scope") or "")
                        if chosen_fn and chosen_scope in {"GLOBAL", "LOCAL"}:
                            hits = await _regex_hits(chosen_scope, chosen_fn)
                            best_choice = {"scope": chosen_scope, "filename": chosen_fn, "hits": hits, "rank_score": float(top.get("rank_score") or 0.0), "row": top}

                    debug["article_filename_ranking"] = ranking

                    if best_choice and isinstance(best_choice.get("hits"), list) and best_choice.get("hits"):
                        chosen_fn = str(best_choice.get("filename"))
                        locked_filename_for_article = chosen_fn
                        sources = list(best_choice.get("hits"))
                        strategy = str(best_choice.get("scope") or strategy)
                        debug["article_regex_scope"] = best_choice.get("scope")
                        debug["article_regex_filename_filter"] = chosen_fn
                        debug["article_regex_best_choice"] = {
                            "scope": best_choice.get("scope"),
                            "filename": chosen_fn,
                            "regex_hit_count": int((best_choice.get("row") or {}).get("regex_hit_count") or 0),
                            "vector_max": float((best_choice.get("row") or {}).get("vector_max") or 0.0),
                            "vector_mean": float((best_choice.get("row") or {}).get("vector_mean") or 0.0),
                            "vector_near_count": int((best_choice.get("row") or {}).get("vector_near_count") or 0),
                            "rank_score": float(best_choice.get("rank_score") or 0.0),
                        }
                except Exception:
                    pass
    except Exception:
        # Ne jamais bloquer la réponse pour un simple filtrage de sources
        pass

    # Si aucune source vectorielle n'a été trouvée, on tente un fallback déterministe par mots-clés.
    # Exception: si un article a été demandé, on évite de basculer sur un autre document.
    if not sources and not article_requested:
        try:
            debug["keyword_regex_fallback"] = True

            if effective_allow_global:
                global_hits = await asyncio.to_thread(
                    _regex_keyword_search_sync,
                    collection_name=GLOBAL_COLLECTION,
                    scope="GLOBAL",
                    organization_id=None,
                    category=category,
                    question=question,
                    limit=5,
                )
                if global_hits:
                    strategy = "GLOBAL"
                    sources = global_hits
                    debug["keyword_regex_scope"] = "GLOBAL"

            if not sources and organization_id:
                local_hits = await asyncio.to_thread(
                    _regex_keyword_search_sync,
                    collection_name=LOCAL_COLLECTION,
                    scope="LOCAL",
                    organization_id=organization_id,
                    category=category,
                    question=question,
                    limit=5,
                )
                if local_hits:
                    strategy = "LOCAL"
                    sources = local_hits
                    debug["keyword_regex_scope"] = "LOCAL"
        except Exception:
            pass

    # En toute fin de préparation des sources, si un article a été demandé et qu'un filename est verrouillé,
    # on s'assure de ne garder que ce document pour éviter les mélanges.
    if sources and article_requested and locked_filename_for_article:
        try:
            before_final_lock = len(sources)
            sources = [s for s in sources if (_src_filename(s) == locked_filename_for_article)]
            debug["article_final_filename_lock"] = True
            debug["article_final_filename"] = locked_filename_for_article
            debug["sources_before_article_final_filename_lock"] = before_final_lock
            debug["sources_after_article_final_filename_lock"] = len(sources)
        except Exception:
            pass

    # Guardrail anti-hallucination: si un article précis est demandé mais qu'il n'est pas explicitement présent
    # dans les extraits finaux, on ne laisse pas le LLM improviser.
    if article_requested and article_num_for_guardrail:
        try:
            import re

            pat_guard = re.compile(
                rf"\b(?:article|art\.?)(?:[\s\n\r\t\u00A0])*{re.escape(str(article_num_for_guardrail))}\b",
                flags=re.IGNORECASE,
            )
            has_article_in_excerpts = bool(sources) and any(pat_guard.search((s.get("content") or "")) for s in sources)
            debug["article_guardrail_has_article_in_excerpts"] = bool(has_article_in_excerpts)
            debug["article_guardrail_whole_doc_regex_attempted"] = bool(article_whole_doc_regex_attempted)

            # Si on a tenté la recherche "document entier" et qu'elle ne remonte rien,
            # on considère que l'ingestion/indexation du PDF est probablement incomplète.
            if bool(article_whole_doc_regex_attempted) and int(article_whole_doc_regex_hits or 0) <= 0:
                debug["article_ingestion_incomplete_suspected"] = True
                msg = str(RAG_INGESTION_INCOMPLETE_TEMPLATE).format(article_num=article_num_for_guardrail)
                return msg, strategy, sources, debug

            if (not has_article_in_excerpts) and bool(article_whole_doc_regex_attempted):
                msg = str(RAG_ARTICLE_ABSENT_TEMPLATE).format(article_num=article_num_for_guardrail)
                debug["article_guardrail_triggered"] = True
                return msg, strategy, sources, debug
        except Exception:
            pass

    # Si des sources existent mais semblent hors sujet, on tente aussi un fallback mots-clés.
    # On évite d'introduire des règles statiques liées à un domaine: on se base uniquement sur les tokens de la question.
    # Exception: si un article a été demandé, on évite de remplacer les sources par des hits d'un autre document.
    if sources and not article_requested:
        try:
            import re

            tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_'\-]{5,}", question or "")
            tokens = [t.lower() for t in tokens if t]

            stop = {
                "avoir",
                "avec",
                "aussi",
                "alors",
                "ainsi",
                "aucune",
                "comme",
                "comment",
                "compte",
                "comptes",
                "concernant",
                "dans",
                "donner",
                "donne",
                "entre",
                "expliquer",
                "explique",
                "faire",
                "merci",
                "article",
                "art",
                "instruction",
                "instructions",
                "information",
                "informations",
                "pourquoi",
                "quels",
                "quelles",
                "quel",
                "quelle",
                "relatif",
                "relative",
                "relatives",
                "sujet",
                "toutes",
                "tout",
                "toute",
                "votre",
                "vous",
            }

            keywords: List[str] = []
            seen = set()
            for t in tokens:
                if t in stop or t in seen:
                    continue
                seen.add(t)
                keywords.append(t)
                if len(keywords) >= 4:
                    break

            if keywords:
                joined_sources_text = "\n".join((s.get("content") or "") for s in sources).lower()
                has_any = any(k in joined_sources_text for k in keywords)

                debug["keyword_expected"] = keywords
                debug["keyword_present_in_sources"] = bool(has_any)

                if not has_any:
                    debug["keyword_regex_fallback_non_relevant_sources"] = True

                    new_sources: List[Dict[str, Any]] = []
                    new_strategy: Optional[str] = None

                    if effective_allow_global:
                        global_hits = await asyncio.to_thread(
                            _regex_keyword_search_sync,
                            collection_name=GLOBAL_COLLECTION,
                            scope="GLOBAL",
                            organization_id=None,
                            category=category,
                            question=question,
                            limit=5,
                        )
                        if global_hits:
                            new_strategy = "GLOBAL"
                            new_sources = global_hits

                    if not new_sources and organization_id:
                        local_hits = await asyncio.to_thread(
                            _regex_keyword_search_sync,
                            collection_name=LOCAL_COLLECTION,
                            scope="LOCAL",
                            organization_id=organization_id,
                            category=category,
                            question=question,
                            limit=5,
                        )
                        if local_hits:
                            new_strategy = "LOCAL"
                            new_sources = local_hits

                    if new_sources and new_strategy:
                        strategy = new_strategy
                        sources = new_sources
                        debug["keyword_regex_scope"] = new_strategy
                    else:
                        # Si les sources vectorielles semblent hors-sujet et que le fallback déterministe ne trouve rien,
                        # on préfère répondre sans sources plutôt que d'afficher des extraits non pertinents.
                        debug["keyword_regex_fallback_no_hits"] = True
                        strategy = "LLM_ONLY"
                        sources = []
        except Exception:
            pass

    if sources:
        try:
            # Choisir le centre d'expansion sur le meilleur chunk APRES reranking hybride
            best = (sources or [None])[0] or {}
            best_meta = best.get("metadata") or {}
            best_scope = (best.get("scope") or best_meta.get("scope") or strategy or "").upper()
            best_id = str(best.get("id") or best_meta.get("_id") or "").strip()

            best_category = best_meta.get("category")
            best_org = best_meta.get("organization_id")
            best_filename = best_meta.get("filename")
            best_chunk_index = best_meta.get("chunk_index")

            # Relecture chunk si metadata incomplète
            if best_id and (
                not best_category
                or not best_filename
                or best_chunk_index is None
                or (best_scope == "LOCAL" and not best_org)
            ):
                collection_name = GLOBAL_COLLECTION if best_scope == "GLOBAL" else LOCAL_COLLECTION
                chunk_doc = await asyncio.to_thread(
                    _get_chunk_by_id_sync,
                    collection_name=collection_name,
                    chunk_id=best_id,
                )
                if chunk_doc:
                    best_category = best_category or chunk_doc.get("category")
                    best_org = best_org or chunk_doc.get("organization_id")
                    best_scope = (chunk_doc.get("scope") or best_scope or "").upper()
                    best_filename = best_filename or chunk_doc.get("filename")
                    if best_chunk_index is None:
                        best_chunk_index = chunk_doc.get("chunk_index")

            # Expansion conditionnée à une proximité lexicale suffisante (évite d'étendre un chunk hors-sujet)
            expand = False
            expand_reason = ""
            try:
                best_lex = float(best.get("_lexical_score") or 0.0)
                lex_dbg = best.get("_lex_dbg") or {}
                phrase_hits = lex_dbg.get("phrase_hits") if isinstance(lex_dbg, dict) else None
                if best_lex >= float(os.getenv("RAG_NEW_NEIGHBOR_MIN_LEX_SCORE", "0.35")):
                    expand = True
                    expand_reason = "lex_score_threshold"
                elif isinstance(phrase_hits, list) and phrase_hits:
                    expand = True
                    expand_reason = "phrase_hit"
            except Exception:
                pass

            debug["neighbor_chunks_expand_intent"] = {
                "enabled": bool(expand),
                "reason": expand_reason,
                "best_lexical_score": float(best.get("_lexical_score") or 0.0),
                "best_vector_score": float(best.get("_vector_score") or best.get("score") or 0.0),
                "best_final_score": float(best.get("_rerank_score") or best.get("score") or 0.0),
            }

            if expand and best_scope in {"GLOBAL", "LOCAL"} and best_filename and best_chunk_index is not None:
                collection_name = GLOBAL_COLLECTION if best_scope == "GLOBAL" else LOCAL_COLLECTION
                window = int(os.getenv("RAG_NEW_NEIGHBOR_WINDOW", "1"))
                neighbors = await asyncio.to_thread(
                    _get_neighbor_chunks_sync,
                    collection_name=collection_name,
                    scope=best_scope,
                    organization_id=str(best_org) if best_scope == "LOCAL" and best_org else None,
                    category=str(best_category) if best_category else None,
                    filename=str(best_filename),
                    chunk_index=int(best_chunk_index),
                    window=max(1, window),
                    limit=12,
                )

                debug["neighbor_chunks_expansion"] = {
                    "attempted": True,
                    "scope": best_scope,
                    "filename": str(best_filename),
                    "center_index": int(best_chunk_index),
                    "window": int(window),
                    "neighbors_count": int(len(neighbors or [])),
                }

                if neighbors:
                    # Merge sans perdre la diversité: on reranke puis on sélectionne diversifié.
                    by_id: Dict[str, Dict[str, Any]] = {}
                    for s in (list(sources) + list(neighbors)):
                        sid = str(s.get("id") or (s.get("metadata") or {}).get("_id") or "").strip()
                        if sid and sid not in by_id:
                            by_id[sid] = s
                    merged = list(by_id.values())

                    # Rerank hybride post-expansion
                    try:
                        rr_alpha2 = float(os.getenv("RAG_NEW_RERANK_ALPHA", "0.70"))
                        rr_beta2 = float(os.getenv("RAG_NEW_RERANK_BETA", "0.30"))
                        merged_reranked, rr2_dbg = _hybrid_rerank(question=question, items=list(merged), alpha=rr_alpha2, beta=rr_beta2)
                        debug["hybrid_rerank_post_neighbors"] = rr2_dbg
                    except Exception:
                        merged_reranked = merged

                    # Sélection diversifiée (évite qu'un doc/section écrase les autres)
                    try:
                        max_total = int(os.getenv("RAG_NEW_FINAL_MAX_CHUNKS", "12"))
                        max_per_doc = int(os.getenv("RAG_NEW_FINAL_MAX_PER_DOC", "5"))
                        selected, sel_dbg = _select_diverse(items=list(merged_reranked), max_total=max_total, max_per_doc=max_per_doc)
                        sources = selected
                        debug["final_selection"] = sel_dbg
                    except Exception:
                        sources = list(merged_reranked)[:12]
            else:
                debug["neighbor_chunks_expansion"] = {"attempted": False, "reason": "lexical_gate" if not expand else "missing_metadata"}

        except Exception:
            pass

    # Si on a des sources finales, on peut retourner aussi la liste des documents de la même catégorie
    # que le document cité (utile pour navigation/contrôle).
    if sources:
        try:
            best = sources[0]
            best_meta = best.get("metadata") or {}
            best_scope = (best.get("scope") or best_meta.get("scope") or strategy or "").upper()
            best_id = str(best.get("id") or best_meta.get("_id") or "").strip()

            best_category = best_meta.get("category")
            best_org = best_meta.get("organization_id")

            # Le vector store ne renvoie pas toujours category/organization_id dans metadata.
            # On relit le chunk directement depuis Mongo pour récupérer les champs.
            if best_id and (not best_category or (best_scope == "LOCAL" and not best_org)):
                collection_name = GLOBAL_COLLECTION if best_scope == "GLOBAL" else LOCAL_COLLECTION
                chunk_doc = await asyncio.to_thread(
                    _get_chunk_by_id_sync,
                    collection_name=collection_name,
                    chunk_id=best_id,
                )
                if chunk_doc:
                    best_category = best_category or chunk_doc.get("category")
                    best_org = best_org or chunk_doc.get("organization_id")
                    best_scope = (chunk_doc.get("scope") or best_scope or "").upper()

            if best_category:
                docs_scope = best_scope if best_scope in {"GLOBAL", "LOCAL"} else None
                docs_org = str(best_org) if (docs_scope == "LOCAL" and best_org) else None
                total, items = await list_knowledge_documents(
                    scope=docs_scope,
                    organization_id=docs_org,
                    category=str(best_category),
                    offset=0,
                    limit=50,
                )
                debug["category_documents"] = {
                    "scope": docs_scope,
                    "organization_id": docs_org,
                    "category": str(best_category),
                    "total": int(total),
                    "items": items,
                }
        except Exception:
            pass

    if DEBUG_CHUNKS:
        debug["sources_final_preview"] = _chunk_preview(sources)
        try:
            debug_summary = {
                "article_requested": bool(debug.get("article_requested")),
                "article_num": debug.get("article_num"),
                "article_filename": debug.get("article_filename"),
                "article_final_filename": debug.get("article_final_filename"),
                "article_regex_filename_filter": debug.get("article_regex_filename_filter"),
                "article_regex_scope": debug.get("article_regex_scope"),
            }
        except Exception:
            debug_summary = {}
        logger.warning(
            "RAG_DEBUG_CHUNKS answer_question final strategy=%s org=%s category=%s q=%r debug=%s sources=%s",
            strategy,
            organization_id,
            category,
            question,
            debug_summary,
            debug["sources_final_preview"],
        )

    def _sync_llm_job() -> str:
        llm = _get_llm()

        if not sources:
            if STRICT_SOURCES:
                prompt = (
                    "Je n'ai trouvé aucune source pertinente dans les bases de connaissances globale et locale.\n"
                    "Réponds de façon courte et actionnable (maximum 8 lignes):\n"
                    "- 1 phrase: dire clairement que rien n'a été trouvé dans la base.\n"
                    "- 2 à 4 puces: quoi faire pour retrouver l'information (mots-clés exacts, nom du document, catégorie, etc.).\n"
                    "- 1 à 2 puces: conseils pratiques généraux (sans affirmer de faits spécifiques).\n"
                    "Interdictions: ne donne pas une longue explication générale, ne fais pas de cours, n'invente pas des règles.\n\n"
                    f"Question: {question}"
                )
            else:
                prompt = (
                    "Je n'ai trouvé aucune source pertinente dans les bases de connaissances globale et locale.\n"
                    "Tu dois répondre en 2 parties:\n"
                    "1) Commence par une phrase courte et explicite: 'Je n'ai pas trouvé d'information formelle dans les bases de connaissances (globale ou locale) pour cette question.'\n"
                    "2) Donne ensuite une réponse utile:\n"
                    "- Si la question est GENERIQUE (connaissances générales), réponds proprement comme ChatGPT, de façon structurée et pratique.\n"
                    "- Si la question semble SPECIFIQUE à une politique interne / procédure d'une organisation / un document, donne une réponse prudente: explique ce qu'on fait généralement dans ce type de situation, liste les points à vérifier, et recommande où chercher dans la documentation (titre/section/mots-clés).\n"
                    "N'invente pas des règles internes. Ne cite aucune source interne puisqu'il n'y en a pas.\n\n"
                    "Exigences de qualité pour la réponse utile:\n"
                    "- Donne une réponse détaillée et structurée (titres courts).\n"
                    "- Fournis 8 à 12 points concrets minimum quand c'est pertinent.\n"
                    "- Donne des exemples concrets et des définitions courtes si nécessaire.\n"
                    "- Termine par un mini-résumé en 2-3 lignes.\n\n"
                    f"Question: {question}"
                )
            return llm.invoke(prompt).content

        context = _build_context(sources)
        prompt = (
            "Tu es un assistant expert, précis et rigoureux.\n"
            "Quand des documents sont fournis, ta priorité est la fidélité aux extraits. Tu peux reformuler, structurer et expliquer, "
            "mais tu ne dois pas inventer de contenu non soutenu par les extraits.\n\n"
            "Règles strictes:\n"
            "- Ta réponse doit être principalement fondée sur les extraits.\n"
            "- N'ajoute pas de conseils généraux non ancrés dans les extraits.\n"
            "- Si une référence structurée (ex: titre, numéro, article/section/chapitre/annexe, tableau, etc.) est visible dans les extraits, tu dois la citer explicitement.\n"
            "- Tu n'as pas le droit d'inventer un numéro, une référence, un article, une section ou une obligation absente des extraits.\n"
            "- Si un point n'est pas couvert par les extraits, écris explicitement que ce point n'apparaît pas clairement dans les extraits retrouvés.\n"
            "- Si une déduction est possible mais pas explicitement écrite, indique-le comme interprétation prudente.\n"
            "- Tu dois répondre UNIQUEMENT en JSON valide (aucun texte hors JSON, pas de markdown).\n\n"

            "Schéma JSON attendu:\n"
            "{\n"
            "  \"answer\": \"réponse finale\",\n"
            "  \"direct_answer\": \"réponse directe si possible (ancrée dans les extraits)\",\n"
            "  \"reference\": {\n"
            "    \"textName\": \"nom exact si présent\",\n"
            "    \"textNumber\": \"numéro/référence si présent\",\n"
            "    \"article\": \"article si présent\",\n"
            "    \"section\": \"section/chapitre si présent\",\n"
            "    \"scope\": \"GLOBAL|LOCAL\"\n"
            "  },\n"
            "  \"grounded_summary\": [\"points factuels tirés des extraits\"],\n"
            "  \"expert_explanation\": \"explication structurée et fidèle aux extraits\",\n"
            "  \"operational_impact\": [\"implication pratique 1\", \"implication pratique 2\"],\n"
            "  \"limitations\": \"ce que les extraits ne permettent pas d'affirmer\"\n"
            "}\n\n"
            "Contraintes de contenu:\n"
            "- grounded_summary: uniquement des affirmations présentes dans les extraits (ou très directement déductibles).\n"
            "- limitations: liste clairement les manques (ce qui n'est pas trouvé explicitement).\n"
            "\nExigences de détail (obligatoires):\n"
            "- answer: 2 à 4 paragraphes, concrets et orientés usage (évite 2-3 lignes).\n"
            "- grounded_summary: au moins 4 points (si possible).\n"
            "- expert_explanation: au moins 12 à 20 lignes, structurées en sections.\n"
            "- operational_impact: au moins 6 points concrets, orientés mise en pratique.\n"
            "- limitations: au moins 3 limites précises (ce qui manque / ce qui n'est pas explicite).\n"
        )

        user_prompt = (
            f"Question utilisateur:\n{question}\n\n"
            f"Extraits retrouvés:\n{context}\n"
        )

        raw = llm.invoke(prompt + "\n\n" + user_prompt).content

        # Retry JSON strict si le modèle a renvoyé autre chose.
        if not _extract_json_object(raw):
            retry_prompt = (
                "Tu dois répondre UNIQUEMENT en JSON valide strict. "
                "Aucun texte hors JSON. Aucun markdown. Respecte exactement les clés: "
                "answer, direct_answer, reference, grounded_summary, expert_explanation, operational_impact, limitations.\n\n"
            )
            raw = llm.invoke(retry_prompt + prompt + "\n\n" + user_prompt).content

        # Garde-fou qualité: si c'est valide mais trop court, on relance une fois en exigeant plus de détail.
        try:
            payload0 = _extract_json_object(raw)
            structured0 = _coerce_structured_answer(payload0, fallback_answer=(raw or ""))
            if _structured_too_short(structured0):
                detail_prompt = (
                    "Réponse trop courte. Réécris en étant PLUS DÉTAILLÉ et PÉDAGOGIQUE, mais toujours fidèle aux extraits.\n"
                    "Obligatoire: grounded_summary >= 5 points si les extraits le permettent; "
                    "expert_explanation en 2 sections minimum; "
                    "limitations avec 3 à 6 points précis.\n"
                    "Interdiction: n'ajoute aucun conseil général non présent dans les extraits.\n\n"
                )
                raw = llm.invoke(detail_prompt + prompt + "\n\n" + user_prompt).content
        except Exception:
            pass

        return raw

    answer = await asyncio.to_thread(_sync_llm_job)

    structured: Optional[_StructuredRagAnswer] = None
    used_retrieval = bool(sources) and str(strategy).upper() in {"GLOBAL", "LOCAL"}

    # Post-traitement: si on a des sources, on attend un JSON structuré (et on ne renvoie pas le JSON brut).
    if sources:
        try:
            excerpts_text = "\n".join((s.get("content") or "") for s in (sources or []))
            payload = _extract_json_object(answer)
            structured = _coerce_structured_answer(payload, fallback_answer=(answer or ""))

            # Garde-fou anti-hallucination sur les références: on ne conserve une référence que si elle est visible
            # dans les extraits (numéro/article/section/textName).
            try:
                ref = dict(structured.reference or {})
                if not _reference_supported_by_excerpts(ref, excerpts_text):
                    structured.reference = {"textName": "", "textNumber": "", "article": "", "section": "", "scope": ""}
                    extra_lim = (
                        "Référence citée: les extraits ne permettent pas d'identifier avec certitude le nom/numéro/article/section mentionné. "
                        "Je ne peux donc pas confirmer une référence précise à partir des sources retrouvées."
                    )
                    if structured.limitations:
                        structured.limitations = structured.limitations.rstrip() + "\n" + extra_lim
                    else:
                        structured.limitations = extra_lim
            except Exception:
                pass

            debug["structured_answer"] = {
                "answer": structured.answer,
                "direct_answer": structured.direct_answer,
                "reference": structured.reference,
                "grounded_summary": structured.grounded_summary,
                "helpful_explanation": structured.helpful_explanation,
                "expert_explanation": structured.expert_explanation,
                "operational_impact": structured.operational_impact,
                "limitations": structured.limitations,
            }
            debug["sources_used"] = _build_sources_used(sources)
            debug["used_retrieval"] = True
            debug["usedRetrieval"] = True
            debug["mode"] = str(strategy).upper()
            answer = structured.answer
        except Exception:
            # Ne jamais casser la réponse; on renvoie le texte brut si parsing impossible.
            debug["structured_answer_parse_failed"] = True
            debug["used_retrieval"] = bool(used_retrieval)
            debug["usedRetrieval"] = bool(used_retrieval)
            debug["mode"] = str(strategy).upper() if used_retrieval else "LLM_ONLY"
    else:
        debug["used_retrieval"] = False
        debug["usedRetrieval"] = False
        debug["mode"] = "LLM_ONLY"

    # Si aucune source n'a été trouvée et qu'aucune catégorie n'est spécifiée,
    # on expose une liste de documents globaux disponibles pour guider l'utilisateur.
    try:
        if (not sources) and (not category) and allow_global:
            total, items = await list_knowledge_documents(
                scope="GLOBAL",
                organization_id=None,
                category=None,
                offset=0,
                limit=50,
            )
            debug["global_documents"] = {
                "scope": "GLOBAL",
                "total": int(total),
                "items": items,
            }
    except Exception:
        pass

    # Ajouter des listes de documents / conseils uniquement si on n'a pas de sources.
    # Sinon, on risque de produire une réponse générique alors que retrieval_used=True.
    if not sources:
        # Ajouter explicitement la liste des documents de la même catégorie à la fin de la réponse
        # (évite les réponses vagues et rend la navigation concrète).
        try:
            cat_docs = debug.get("category_documents") if isinstance(debug, dict) else None
            if isinstance(cat_docs, dict) and isinstance(cat_docs.get("items"), list) and cat_docs.get("items"):
                items = cat_docs.get("items")
                filenames = []
                for d in items:
                    fn = (d or {}).get("filename")
                    if fn and fn not in filenames:
                        filenames.append(fn)
                    if len(filenames) >= 20:
                        break

                if filenames:
                    total = int(cat_docs.get("total") or len(filenames))
                    category_name = cat_docs.get("category")
                    scope_name = cat_docs.get("scope")
                    lines = [
                        "",
                        "Documents dans la même catégorie:",
                        f"- Catégorie: {category_name}",
                        f"- Scope: {scope_name}",
                    ]
                    for fn in filenames:
                        lines.append(f"- {fn}")
                    if total > len(filenames):
                        lines.append(f"- ... ({total - len(filenames)} autres)")

                    answer = (answer or "").rstrip() + "\n" + "\n".join(lines) + "\n"
        except Exception:
            pass

    # Si pas de sources (donc pas de "même catégorie"), afficher la liste des documents globaux disponibles.
    try:
        glob_docs = debug.get("global_documents") if isinstance(debug, dict) else None
        if isinstance(glob_docs, dict) and isinstance(glob_docs.get("items"), list) and glob_docs.get("items"):
            items = glob_docs.get("items")
            filenames = []
            for d in items:
                fn = (d or {}).get("filename")
                if fn and fn not in filenames:
                    filenames.append(fn)
                if len(filenames) >= 20:
                    break

            if filenames:
                total = int(glob_docs.get("total") or len(filenames))
                lines = [
                    "",
                    "Documents disponibles dans la base globale (toutes catégories):",
                    f"- Scope: GLOBAL",
                ]
                for fn in filenames:
                    lines.append(f"- {fn}")
                if total > len(filenames):
                    lines.append(f"- ... ({total - len(filenames)} autres)")
                answer = (answer or "").rstrip() + "\n" + "\n".join(lines) + "\n"
    except Exception:
        pass

    if not sources:
        try:
            tips: List[str] = []
            if organization_id:
                tips.append(
                    "Tu peux préciser une catégorie (ex: 'Procédure de gestion de risque') ou le nom du document pour améliorer la recherche dans la base locale."
                )

                if allow_global:
                    tips.append("La recherche interroge d'abord la base globale, puis la base locale de ton organisation.")
                else:
                    tips.append(
                        "La base globale n'est pas interrogée (licence inactive). Si tu dois accéder à la base globale, contacte ton administrateur pour activer la licence."
                    )

            tips.append(
                "Si tu cherches un tableau/section précise, reformule avec des mots-clés exacts (ex: 'processus de surveillance des seuils', 'déclenchement', 'dépassement des limites')."
            )
            tips.append(
                "Si le document est scanné, un ré-upload peut améliorer l'OCR et donc la qualité des extraits retrouvés."
            )

            if tips:
                answer = (answer or "").rstrip() + "\n\nConseils:\n" + "\n".join(f"- {t}" for t in tips)
        except Exception:
            pass

    return answer, strategy, sources, debug


def parse_metadata_json(metadata_json: Optional[str]) -> Dict[str, Any]:
    """Parse un JSON de métadonnées envoyé côté upload (optionnel)."""

    if not metadata_json:
        return {}

    try:
        data = json.loads(metadata_json)
        if isinstance(data, dict):
            return data
        return {"value": data}
    except Exception:
        return {"raw": metadata_json}


async def list_knowledge_documents(
    *,
    scope: Optional[str],
    organization_id: Optional[str],
    category: Optional[str],
    offset: int,
    limit: int,
) -> Tuple[int, List[Dict[str, Any]]]:
    def _sync_job() -> Tuple[int, List[Dict[str, Any]]]:
        from pymongo import ASCENDING

        items: List[Dict[str, Any]] = []

        collections: List[Tuple[str, str]] = []
        if scope == "GLOBAL":
            collections = [(GLOBAL_COLLECTION, "GLOBAL")]
        elif scope == "LOCAL":
            collections = [(LOCAL_COLLECTION, "LOCAL")]
        else:
            collections = [(GLOBAL_COLLECTION, "GLOBAL"), (LOCAL_COLLECTION, "LOCAL")]

        for collection_name, fixed_scope in collections:
            col = _get_pymongo_collection(collection_name)

            match: Dict[str, Any] = {"scope": fixed_scope}
            if fixed_scope == "LOCAL" and organization_id:
                match["organization_id"] = organization_id
            if category:
                match["category"] = category

            pipeline = [
                {"$match": match},
                {
                    "$group": {
                        "_id": {
                            "scope": "$scope",
                            "filename": "$filename",
                            "category": "$category",
                            "organization_id": "$organization_id",
                        },
                        "chunk_count": {"$sum": 1},
                        "created_at": {"$min": "$created_at"},
                        "updated_at": {"$max": "$updated_at"},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "scope": "$_id.scope",
                        "filename": "$_id.filename",
                        "category": "$_id.category",
                        "organization_id": "$_id.organization_id",
                        "chunk_count": 1,
                        "created_at": 1,
                        "updated_at": 1,
                    }
                },
            ]

            docs = list(col.aggregate(pipeline, allowDiskUse=True))
            items.extend(docs)

        items.sort(key=lambda d: ((d.get("scope") or ""), (d.get("filename") or "")))
        total = len(items)
        sliced = items[max(0, offset) : max(0, offset) + max(1, limit)]
        return total, sliced

    return await asyncio.to_thread(_sync_job)
