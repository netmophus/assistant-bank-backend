"""
RAG Pipeline — simplifié, dynamique, sans valeurs hardcodées.

Flux:
  1. Ingestion  : upload → extraction texte → chunking → embeddings → MongoDB
  2. Retrieval  : question → embedding → Vector Search (LOCAL si user connecté, GLOBAL sinon)
  3. Generation : extraits → LLM → réponse ancrée dans les sources

Configuration complète via variables d'environnement (.env).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CONFIG — tout vient de l'environnement, zéro valeur métier hardcodée
# ---------------------------------------------------------------------------

class Config:
    # MongoDB
    MONGO_URI: str = os.getenv("RAG_MONGO_URI") or os.getenv("RAG_NEW_MONGO_URI") or "mongodb://127.0.0.1:27017/?directConnection=true"
    MONGO_DB: str = (
        os.getenv("RAG_MONGO_DB")
        or os.getenv("RAG_NEW_DB")
        or os.getenv("RAG_NEW_DB_NAME")
        or os.getenv("RAG_NEW_MONGO_DB")
        or "rag_db"
    )
    GLOBAL_COLLECTION: str = os.getenv("RAG_GLOBAL_COLLECTION") or os.getenv("RAG_NEW_GLOBAL_COLLECTION") or "knowledge_global"
    LOCAL_COLLECTION: str = os.getenv("RAG_LOCAL_COLLECTION") or os.getenv("RAG_NEW_LOCAL_COLLECTION") or "knowledge_local"
    GLOBAL_INDEX: str = (
        os.getenv("RAG_GLOBAL_INDEX")
        or os.getenv("RAG_NEW_GLOBAL_VECTOR_INDEX")
        or os.getenv("RAG_NEW_GLOBAL_INDEX_NAME")
        or "global_vec_idx"
    )
    LOCAL_INDEX: str = (
        os.getenv("RAG_LOCAL_INDEX")
        or os.getenv("RAG_NEW_LOCAL_VECTOR_INDEX")
        or os.getenv("RAG_NEW_LOCAL_INDEX_NAME")
        or "local_vec_idx"
    )

    # OpenAI
    EMBEDDING_MODEL: str = os.getenv("RAG_EMBEDDING_MODEL") or os.getenv("RAG_NEW_EMBEDDING_MODEL") or "text-embedding-3-large"
    EMBEDDING_DIMS: int = int(os.getenv("RAG_EMBEDDING_DIMS") or os.getenv("RAG_NEW_EMBEDDING_DIMENSIONS") or "3072")
    LLM_MODEL: str = os.getenv("RAG_LLM_MODEL") or os.getenv("RAG_NEW_LLM_MODEL") or "gpt-4o-mini"
    LLM_TEMPERATURE: float = float(os.getenv("RAG_LLM_TEMPERATURE") or os.getenv("RAG_NEW_LLM_TEMPERATURE") or "0.2")

    # Retrieval
    RETRIEVAL_K: int = int(os.getenv("RAG_RETRIEVAL_K") or os.getenv("RAG_NEW_K") or "10")
    SCORE_THRESHOLD: float = float(os.getenv("RAG_SCORE_THRESHOLD") or os.getenv("RAG_NEW_LOCAL_THRESHOLD") or "0.75")
    MIN_DOCS: int = int(os.getenv("RAG_MIN_DOCS") or os.getenv("RAG_NEW_GLOBAL_MIN_DOCS") or "2")

    # Chunking
    CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE") or os.getenv("RAG_NEW_CHUNK_SIZE") or "600")
    CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP") or os.getenv("RAG_NEW_CHUNK_OVERLAP") or "150")

    # Comportement
    STRICT_SOURCES: bool = (os.getenv("RAG_STRICT_SOURCES") or os.getenv("RAG_NEW_STRICT_SOURCES") or "0").lower() in {"1", "true", "yes", "on"}

    # OCR (PDF scannés)
    ENABLE_OCR: bool        = os.getenv("RAG_ENABLE_OCR", "false").lower() in {"1", "true"}
    OCR_LANG: str           = os.getenv("RAG_OCR_LANG", "fra")
    OCR_MAX_PAGES: int      = int(os.getenv("RAG_OCR_MAX_PAGES", "10"))
    TESSERACT_CMD: str      = os.getenv("RAG_TESSERACT_CMD", "")


cfg = Config()


def parse_metadata_json(metadata_json: Optional[str]) -> Dict[str, Any]:
    if not metadata_json:
        return {}
    try:
        data = json.loads(metadata_json)
        if isinstance(data, dict):
            return data
        return {"value": data}
    except Exception:
        return {"raw": metadata_json}


# ---------------------------------------------------------------------------
# CONNEXION MONGODB — singleton, pas de fuite de connexions
# ---------------------------------------------------------------------------

_mongo_client = None


def get_mongo_client():
    global _mongo_client
    if _mongo_client is None:
        from pymongo import MongoClient
        kwargs: dict[str, Any] = {
            "serverSelectionTimeoutMS": 8000,   # échoue vite si Atlas injoignable
            "connectTimeoutMS": 10000,
            "socketTimeoutMS": 45000,
        }
        if cfg.MONGO_URI.lower().startswith("mongodb+srv://"):
            kwargs["tls"] = True
            try:
                import certifi
                kwargs["tlsCAFile"] = certifi.where()
            except ImportError:
                pass
            kwargs["tlsDisableOCSPEndpointCheck"] = True
        _mongo_client = MongoClient(cfg.MONGO_URI, **kwargs)
    return _mongo_client


def get_collection(name: str):
    return get_mongo_client()[cfg.MONGO_DB][name]


# ---------------------------------------------------------------------------
# EMBEDDINGS & LLM — singletons
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_embeddings():
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model=cfg.EMBEDDING_MODEL, dimensions=cfg.EMBEDDING_DIMS)


@lru_cache(maxsize=1)
def get_llm():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=cfg.LLM_MODEL, temperature=cfg.LLM_TEMPERATURE)


# ---------------------------------------------------------------------------
# EXTRACTION TEXTE
# ---------------------------------------------------------------------------

def _extract_text(filename: str, raw_bytes: bytes) -> str:
    """Extrait le texte brut depuis le fichier uploadé."""
    ext = os.path.splitext(filename.lower())[1]

    if ext in {".txt", ".md", ".csv"}:
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return raw_bytes.decode("latin-1", errors="ignore")

    if ext == ".docx":
        try:
            from docx import Document
            import io
            doc = Document(io.BytesIO(raw_bytes))
            return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
        except ImportError:
            raise ValueError("python-docx requis : pip install python-docx")

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(raw_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(p.strip() for p in pages if p.strip())
            if text:
                return text
            # PDF scanné : tentative OCR si activé
            if not cfg.ENABLE_OCR:
                raise ValueError(
                    "PDF sans texte extractible. "
                    "Activez l'OCR avec RAG_ENABLE_OCR=true pour les PDFs scannés."
                )
            return _ocr_pdf(raw_bytes)
        except ImportError:
            raise ValueError("pypdf requis : pip install pypdf")

    raise ValueError(
        f"Format non supporté : {ext}. "
        "Formats acceptés : .txt, .md, .csv, .docx, .pdf"
    )


def _ocr_pdf(raw_bytes: bytes) -> str:
    """OCR sur PDF scanné via Tesseract. Activé par RAG_ENABLE_OCR=true."""
    try:
        import fitz
    except ImportError:
        raise ValueError("pymupdf requis pour l'OCR : pip install pymupdf")

    try:
        import pytesseract
    except ImportError:
        raise ValueError("pytesseract requis pour l'OCR : pip install pytesseract")

    try:
        from PIL import Image
    except ImportError:
        raise ValueError("pillow requis pour l'OCR : pip install pillow")

    if cfg.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = cfg.TESSERACT_CMD

    doc = fitz.open(stream=raw_bytes, filetype="pdf")
    parts = []

    for i in range(min(len(doc), cfg.OCR_MAX_PAGES)):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        try:
            txt = pytesseract.image_to_string(img, lang=cfg.OCR_LANG) or ""
        except Exception as e:
            msg = str(e).lower()
            if "failed loading language" in msg or "error opening data file" in msg:
                raise ValueError(
                    f"Langue OCR '{cfg.OCR_LANG}' introuvable. "
                    f"Vérifiez TESSDATA_PREFIX ({os.getenv('TESSDATA_PREFIX', 'non défini')}) "
                    f"et que le fichier {cfg.OCR_LANG}.traineddata existe."
                )
            raise
        if txt.strip():
            parts.append(txt.strip())

    result = "\n\n".join(parts)
    if not result:
        raise ValueError(
            "OCR : aucun texte détecté. "
            "Vérifiez que le PDF est lisible et que Tesseract est bien installé."
        )
    return result


# ---------------------------------------------------------------------------
# CHUNKING
# ---------------------------------------------------------------------------

def _chunk_text(text: str) -> list[str]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=cfg.CHUNK_SIZE,
        chunk_overlap=cfg.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [c for c in splitter.split_text(text) if len(c.strip()) > 50]


def _chunk_id(scope: str, org_id: Optional[str], filename: str, index: int, content: str) -> str:
    """ID stable pour upsert idempotent."""
    raw = f"{scope}|{org_id or ''}|{filename}|{index}|{content}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# INGESTION
# ---------------------------------------------------------------------------

async def ingest_document(
    *,
    filename: str,
    file_bytes: bytes,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    category: Optional[str] = None,
    scope: Optional[str] = None,
    metadata: dict[str, Any] | None = None,
) -> Tuple[str, int, int, Optional[str], datetime]:
    """
    Ingère un document dans la base appropriée.
    - organization_id fourni  → base LOCAL
    - organization_id absent  → base GLOBAL
    """
    resolved_scope = (scope or ("LOCAL" if organization_id else "GLOBAL")).strip().upper()
    collection_name = cfg.LOCAL_COLLECTION if resolved_scope == "LOCAL" else cfg.GLOBAL_COLLECTION
    created_at = datetime.now(timezone.utc)

    def _sync():
        text = _extract_text(filename, file_bytes)
        if not text.strip():
            raise ValueError("Aucun texte extrait du document.")

        chunks = _chunk_text(text)
        if not chunks:
            raise ValueError("Aucun chunk généré après découpage.")

        vectors = get_embeddings().embed_documents(chunks)

        col = get_collection(collection_name)
        from pymongo import ReplaceOne

        ops = []
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            cid = _chunk_id(scope, organization_id, filename, i, chunk)
            doc = {
                "_id": cid,
                "scope": scope,
                "organization_id": organization_id,
                "category": category,
                "filename": filename,
                "chunk_index": i,
                "content": chunk,
                "embedding": vec,
                "metadata": metadata or {},
                "created_at": created_at,
            }
            ops.append(ReplaceOne({"_id": cid}, doc, upsert=True))

        result = col.bulk_write(ops, ordered=False)
        # matched_count inclus pour ne pas retourner 0 si les chunks n'ont pas changé
        written = result.upserted_count + result.modified_count + result.matched_count

        return (collection_name, int(written), int(len(chunks)), user_id, created_at)

    return await asyncio.to_thread(_sync)


async def ingest_text_document(
    *,
    filename: str,
    text: str,
    organization_id: Optional[str] = None,
    category: Optional[str] = None,
    scope: str,
    metadata: Dict[str, Any],
) -> Tuple[str, int, int, datetime]:
    resolved_scope = (scope or "").strip().upper()
    if resolved_scope not in {"LOCAL", "GLOBAL"}:
        raise ValueError("scope invalide (attendu: LOCAL ou GLOBAL)")

    if resolved_scope == "LOCAL" and not organization_id:
        raise ValueError("organization_id requis pour scope=LOCAL")

    collection_name = cfg.LOCAL_COLLECTION if resolved_scope == "LOCAL" else cfg.GLOBAL_COLLECTION
    created_at = datetime.now(timezone.utc)

    def _sync():
        if not (text or "").strip():
            raise ValueError("Aucun texte fourni pour ingestion.")

        chunks = _chunk_text(text)
        if not chunks:
            raise ValueError("Aucun chunk généré après découpage.")

        vectors = get_embeddings().embed_documents(chunks)

        col = get_collection(collection_name)
        from pymongo import ReplaceOne

        ops = []
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            cid = _chunk_id(resolved_scope, organization_id, filename, i, chunk)
            doc = {
                "_id": cid,
                "scope": resolved_scope,
                "organization_id": organization_id,
                "category": category,
                "filename": filename,
                "chunk_index": i,
                "content": chunk,
                "embedding": vec,
                "metadata": metadata or {},
                "created_at": created_at,
            }
            ops.append(ReplaceOne({"_id": cid}, doc, upsert=True))

        result = col.bulk_write(ops, ordered=False)
        written = result.upserted_count + result.modified_count + result.matched_count
        return (collection_name, int(written), int(len(chunks)), created_at)

    return await asyncio.to_thread(_sync)


def _build_sources_used_compat(sources: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    used: List[Dict[str, Any]] = []
    seen = set()
    for s in list(sources or [])[:20]:
        meta = s.get("metadata") or {}
        scope = (s.get("scope") or meta.get("scope") or "").strip().upper()

        # Sources web : utiliser l'URL comme nom de document
        if scope == "WEB":
            url = meta.get("url") or ""
            title = meta.get("title") or url
            if not url or url in seen:
                continue
            seen.add(url)
            used.append({"documentName": title, "category": None, "scope": "WEB", "page": None, "url": url})
            continue

        fn = (meta.get("filename") or s.get("filename") or "").strip()
        if not fn:
            continue
        key = (scope, fn)
        if key in seen:
            continue
        seen.add(key)
        used.append({"documentName": fn, "category": meta.get("category"), "scope": scope, "page": None})
    return used


async def answer_question(
    *,
    question: str,
    organization_id: Optional[str],
    category: Optional[str],
    allow_global: bool,
    skip_rag: bool = False,
) -> Tuple[str, str, List[Dict[str, Any]], Dict[str, Any]]:
    if not (question or "").strip():
        raise ValueError("La question ne peut pas être vide.")

    # ── Génération via Perplexity (RAG désactivé) ───────────────────────────
    from app.services.perplexity_service import answer_with_perplexity, _is_configured

    sites: list[str] = []
    if organization_id:
        try:
            from app.models.organization import get_web_search_config
            web_cfg = await get_web_search_config(organization_id)
            if web_cfg.get("web_search_enabled") and web_cfg.get("web_search_sites"):
                sites = web_cfg["web_search_sites"]
        except Exception:
            pass

    if _is_configured():
        result = await answer_with_perplexity(question, sites=sites or None)
        raw_answer = result.get("answer") or ""
        strategy = "PERPLEXITY"
    else:
        # Fallback OpenAI si Perplexity non configuré
        def _generate() -> str:
            return get_llm().invoke(_prompt_no_sources(question)).content
        raw_answer = await asyncio.to_thread(_generate)
        strategy = "LLM_ONLY"

    sources: List[Dict[str, Any]] = []
    debug: Dict[str, Any] = {
        "used_retrieval": False,
        "usedRetrieval": False,
        "mode": strategy,
        "sources_used": [],
        "structured_answer": {"answer": raw_answer, "direct_answer": "", "grounded_summary": [],
                               "expert_explanation": "", "operational_impact": [], "limitations": "",
                               "reference": {"textName": "", "textNumber": "", "article": "", "section": "", "scope": ""}},
    }

    return (raw_answer or "").strip(), strategy, sources, debug


async def list_knowledge_documents(
    *,
    scope: Optional[str],
    organization_id: Optional[str],
    category: Optional[str],
    offset: int,
    limit: int,
) -> Tuple[int, List[Dict[str, Any]]]:
    scope_norm = (scope or "").strip().upper() or None
    docs = await list_documents(scope=scope_norm, organization_id=organization_id, category=category)
    total = int(len(docs))
    sliced = list(docs)[max(0, int(offset)) : max(0, int(offset)) + max(1, int(limit))]
    for d in sliced:
        d.setdefault("organization_id", organization_id)
        d.setdefault("updated_at", None)
    return total, sliced


# ---------------------------------------------------------------------------
# RETRIEVAL
# ---------------------------------------------------------------------------

def _vector_search(
    *,
    collection_name: str,
    index_name: str,
    query: str,
    filter_query: dict[str, Any],
    k: int,
) -> list[dict[str, Any]]:
    from langchain_mongodb import MongoDBAtlasVectorSearch

    col = get_collection(collection_name)
    vs = MongoDBAtlasVectorSearch(
        collection=col,
        embedding=get_embeddings(),
        index_name=index_name,
        text_key="content",
        embedding_key="embedding",
    )

    results = vs.similarity_search_with_score(query=query, k=k, pre_filter=filter_query)

    return [
        {
            "id": doc.metadata.get("_id", ""),
            "content": doc.page_content,
            "score": float(score),
            "scope": filter_query.get("scope", ""),
            "metadata": doc.metadata,
        }
        for doc, score in results
    ]


def _filter_relevant(results: list[dict], threshold: float, min_docs: int) -> list[dict]:
    """
    Garde les résultats au-dessus du seuil.
    Si moins de min_docs passent, garde quand même les top min_docs pour ne pas rester sans réponse.
    """
    above = [r for r in results if r["score"] >= threshold]
    if len(above) >= min_docs:
        return above
    return sorted(results, key=lambda r: r["score"], reverse=True)[:min_docs]


async def retrieve(
    *,
    question: str,
    organization_id: Optional[str],
    category: Optional[str],
) -> tuple[str, list[dict[str, Any]]]:
    """
    Stratégie de retrieval selon le contexte:
    - User connecté (organization_id) → LOCAL en priorité, GLOBAL en fallback
    - User anonyme                    → GLOBAL uniquement
    """
    k = cfg.RETRIEVAL_K
    threshold = cfg.SCORE_THRESHOLD
    min_docs = cfg.MIN_DOCS

    def _filter(scope: str) -> dict:
        f: dict = {"scope": scope}
        if scope == "LOCAL" and organization_id:
            f["organization_id"] = organization_id
        if category:
            f["category"] = category
        return f

    # User connecté → LOCAL d'abord
    if organization_id:
        local_raw = await asyncio.to_thread(
            _vector_search,
            collection_name=cfg.LOCAL_COLLECTION,
            index_name=cfg.LOCAL_INDEX,
            query=question,
            filter_query=_filter("LOCAL"),
            k=k,
        )
        local_results = _filter_relevant(local_raw, threshold, min_docs)
        if local_results and local_results[0]["score"] >= threshold:
            return "LOCAL", local_results

        # Fallback GLOBAL si LOCAL insuffisant
        global_raw = await asyncio.to_thread(
            _vector_search,
            collection_name=cfg.GLOBAL_COLLECTION,
            index_name=cfg.GLOBAL_INDEX,
            query=question,
            filter_query=_filter("GLOBAL"),
            k=k,
        )
        global_results = _filter_relevant(global_raw, threshold, min_docs)
        if global_results and global_results[0]["score"] >= threshold:
            return "GLOBAL", global_results

        # Merge LOCAL + GLOBAL si les deux sont faibles mais présents
        merged = sorted(local_raw + global_raw, key=lambda r: r["score"], reverse=True)
        if merged:
            return "MERGED", merged[:k]

        return "NONE", []

    # User anonyme → GLOBAL uniquement
    global_raw = await asyncio.to_thread(
        _vector_search,
        collection_name=cfg.GLOBAL_COLLECTION,
        index_name=cfg.GLOBAL_INDEX,
        query=question,
        filter_query=_filter("GLOBAL"),
        k=k,
    )
    results = _filter_relevant(global_raw, threshold, min_docs)
    if results:
        return "GLOBAL", results

    return "NONE", []


# ---------------------------------------------------------------------------
# GENERATION
# ---------------------------------------------------------------------------

def _clean_filename(filename: str) -> str:
    return re.sub(r"^[a-f0-9]{24}_", "", filename or "")

def _build_context(sources: list[dict]) -> str:
    parts = []
    for i, s in enumerate(sources, 1):
        meta  = s.get("metadata") or {}
        scope = s.get("scope", "")
        score = s.get("score", 0.0)
        content = (s.get("content") or "").strip()

        if scope == "WEB":
            url   = meta.get("url") or ""
            title = meta.get("title") or meta.get("site") or "Source web"
            label = f"[Web {i} | {title} | URL: {url} | score={score:.3f}]"
        else:
            filename = _clean_filename(meta.get("filename") or s.get("filename") or "Document")
            label = f"[Extrait {i} | {filename} | {scope} | score={score:.3f}]"

        parts.append(f"{label}\n{content}")
    return "\n\n---\n\n".join(parts)


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    t = (text or "").strip()
    if not t:
        return None
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
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


def _coerce_list_str(x: Any) -> list[str]:
    if not x:
        return []
    if isinstance(x, list):
        out: list[str] = []
        for it in x:
            s = ("" if it is None else str(it)).strip()
            if s:
                out.append(s)
        return out
    s = ("" if x is None else str(x)).strip()
    return [s] if s else []


def _coerce_structured_answer(payload: Optional[Dict[str, Any]], *, fallback_answer: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "answer": (fallback_answer or "").strip(),
            "direct_answer": "",
            "reference": {"textName": "", "textNumber": "", "article": "", "section": "", "scope": ""},
            "grounded_summary": [],
            "helpful_explanation": "",
            "expert_explanation": "",
            "operational_impact": [],
            "limitations": "",
        }

    ref = payload.get("reference") if isinstance(payload.get("reference"), dict) else {}
    return {
        "answer": (str(payload.get("answer") or "") or (fallback_answer or "")).strip(),
        "direct_answer": str(payload.get("direct_answer") or "").strip(),
        "reference": {
            "textName": str(ref.get("textName") or "").strip(),
            "textNumber": str(ref.get("textNumber") or "").strip(),
            "article": str(ref.get("article") or "").strip(),
            "section": str(ref.get("section") or "").strip(),
            "scope": str(ref.get("scope") or "").strip(),
        },
        "grounded_summary": _coerce_list_str(payload.get("grounded_summary")),
        "helpful_explanation": str(payload.get("helpful_explanation") or "").strip(),
        "expert_explanation": str(payload.get("expert_explanation") or "").strip(),
        "operational_impact": _coerce_list_str(payload.get("operational_impact")),
        "limitations": str(payload.get("limitations") or "").strip(),
    }


def _prompt_with_sources(question: str, context: str) -> str:
    return (
        "Tu es un **assistant bancaire expert de l'UMOA/UEMOA**. Tu maîtrises parfaitement : "
        "la réglementation bancaire communautaire, le Plan Comptable Bancaire (PCB UEMOA), "
        "la réglementation prudentielle BCEAO/Commission Bancaire (Bâle II/III adapté UEMOA), "
        "la lutte contre le blanchiment de capitaux et le financement du terrorisme (LBC/FT), "
        "le contrôle interne, la conformité et la gouvernance bancaire, le droit bancaire UMOA et OHADA, "
        "l'analyse des risques de crédit (particuliers, PME/PMI, grandes entreprises), "
        "les états financiers réglementaires et le reporting à la Commission Bancaire, "
        "la microfinance et le cadre des SFD, les marchés financiers régionaux (BRVM/CREPMF), "
        "la réglementation des changes UEMOA, les systèmes de paiement (GIM-UEMOA, mobile money, interbancaire), "
        "la fiscalité bancaire UEMOA, la gestion actif-passif (ALM), les risques opérationnels, "
        "ainsi que le cadre applicable à la **finance islamique** dans l'UMOA.\n"
        "Tu as lu et analysé les extraits ci-dessous. Tu dois maintenant répondre à la question en te comportant "
        "comme un vrai expert qui conseille un client : complet, concret, utile, pédagogique.\n\n"

        "RÈGLES D'EXPERT (obligatoires) :\n"
        "1. Exploite TOUT ce que contiennent les extraits — ne résume pas, ne raccourcis pas, cite les détails.\n"
        "2. Quand les extraits couvrent un point, cite le nom du fichier source en italique (*source*).\n"
        "3. Quand les extraits ne couvrent pas un point mais que tu peux apporter ta connaissance experte, "
        "   fais-le en le signalant: **[Expertise]** avant le paragraphe concerné.\n"
        "4. Ne jamais écrire 'Non précisé dans les extraits' comme réponse finale — complète toujours avec ton expertise.\n"
        "5. Donne des exemples chiffrés et concrets ancrés dans le contexte UEMOA/BCEAO quand c'est utile.\n"
        "6. Anticipe les questions pratiques : 'que faire concrètement', 'quels impacts', 'comment s'y conformer'.\n"
        "7. Si les extraits sont hors sujet (mauvais pays, mauvaise année), le dire clairement "
        "   ET apporter quand même ta meilleure réponse experte avec les données que tu possèdes.\n\n"

        "ANTI-HALLUCINATION :\n"
        "- Ne jamais inventer de chiffres, articles, taux ou règles absents des sources ET de tes connaissances réelles.\n"
        "- Si tu n'as pas l'information précise, dis-le et oriente vers la source officielle exacte à consulter.\n\n"

        "FORMAT DE RÉPONSE — JSON valide uniquement (aucun texte hors JSON) :\n"
        "{\n"
        "  \"answer\": \"Réponse complète en Markdown. Structure libre adaptée à la question : titres ##, listes, tableaux si utile. "
        "Commence directement par la réponse, sans intro générique. "
        "Si des sources web sont présentes, ajoute une section ## Sources consultées avec liens cliquables en fin de réponse.\",\n"
        "  \"direct_answer\": \"Réponse courte et directe à la question (1-2 phrases max)\",\n"
        "  \"reference\": {\n"
        "    \"textName\": \"Nom du texte de référence principal, vide si absent\",\n"
        "    \"textNumber\": \"Numéro/référence si présent\",\n"
        "    \"article\": \"Article si présent\",\n"
        "    \"section\": \"Section/chapitre si présent\",\n"
        "    \"scope\": \"GLOBAL ou LOCAL\"\n"
        "  },\n"
        "  \"grounded_summary\": [\"Point factuel 1 tiré des sources (avec citation fichier)\", \"Point factuel 2...\"],\n"
        "  \"expert_explanation\": \"Analyse experte : implications, contexte réglementaire, enjeux pratiques — va au fond du sujet\",\n"
        "  \"operational_impact\": [\"Action concrète 1 pour le client\", \"Action concrète 2\", \"Exemple chiffré ou cas pratique réel\"],\n"
        "  \"limitations\": \"Ce que tu ne peux pas confirmer avec certitude et pourquoi\"\n"
        "}\n\n"

        f"EXTRAITS DISPONIBLES :\n{context}\n\n"
        f"QUESTION : {question}\n"
    )


def _prompt_no_sources(question: str) -> str:
    return (
        "Tu es **Miznas AI**, assistant bancaire expert de l'UMOA/UEMOA, de rang professeur agrégé en droit bancaire "
        "et finance. Tu maîtrises parfaitement : "
        "la réglementation bancaire communautaire UMOA/UEMOA, le Plan Comptable Bancaire (PCB UEMOA), "
        "le dispositif prudentiel BCEAO et les instructions de la Commission Bancaire, "
        "les normes Bâle II/III adaptées à l'UEMOA, la lutte contre le blanchiment de capitaux et le financement "
        "du terrorisme (LBC/FT), le contrôle interne, la conformité et la gouvernance bancaire, "
        "le droit bancaire UMOA, le droit des sociétés OHADA, l'analyse des risques de crédit "
        "(particuliers, PME/PMI, grandes entreprises), les états financiers réglementaires et le reporting "
        "à la Commission Bancaire, la microfinance et le cadre des SFD, les marchés financiers régionaux "
        "(BRVM/CREPMF), la réglementation des changes UEMOA, les systèmes de paiement "
        "(GIM-UEMOA, mobile money, interbancaire), la fiscalité bancaire UEMOA, la gestion actif-passif (ALM), "
        "les risques opérationnels, ainsi que le cadre applicable à la **finance islamique** dans l'UMOA, "
        "et toute la pratique bancaire en Afrique de l'Ouest.\n\n"

        "COMPORTEMENT D'EXPERT ABSOLU :\n"
        "- Réponds comme un professeur qui maîtrise son sujet sur le bout des doigts — exhaustif, précis, structuré.\n"
        "- Cite les textes réglementaires exacts : numéro d'instruction BCEAO, article de loi, circulaire, directive UEMOA.\n"
        "- Donne des chiffres précis : ratios, seuils, délais, montants en FCFA quand tu les connais.\n"
        "- Explique les mécanismes en profondeur, pas en surface — compare, nuance, contextualise.\n"
        "- Anticipe les questions pratiques du professionnel bancaire : impacts opérationnels, risques, bonnes pratiques.\n"
        "- Si tu mentionnes une règle ou un texte, donne sa référence précise (ex: Instruction BCEAO n°026-11-2016, "
        "  Article 23 de la Loi Bancaire UEMOA, Règlement UEMOA n°15/2002/CM/UEMOA).\n"
        "- Ne sois JAMAIS vague. Un expert ne dit pas 'il faut respecter les règles' — il dit QUELLES règles, "
        "  QUELS articles, QUELS seuils, QUELLES sanctions en cas de non-conformité.\n"
        "- Si la question touche un domaine où la réglementation est récente ou a évolué, le signaler et donner "
        "  la version la plus récente que tu connais.\n\n"

        "FORMAT DE RÉPONSE — JSON valide uniquement (aucun texte hors JSON) :\n"
        "{\n"
        "  \"answer\": \"Réponse complète et approfondie en Markdown. "
        "Structure claire avec ## titres, listes détaillées, tableaux si pertinent. "
        "Commence directement par le fond — pas d'introduction générique. "
        "Inclus : contexte réglementaire précis, mécanismes détaillés, chiffres clés, implications pratiques, exemples concrets UEMOA.\",\n"
        "  \"direct_answer\": \"Réponse directe en 1-2 phrases précises\",\n"
        "  \"reference\": {\n"
        "    \"textName\": \"Nom du texte principal cité\",\n"
        "    \"textNumber\": \"Numéro/référence exacte\",\n"
        "    \"article\": \"Article(s) concerné(s)\",\n"
        "    \"section\": \"Section/chapitre\",\n"
        "    \"scope\": \"UEMOA ou pays concerné\"\n"
        "  },\n"
        "  \"grounded_summary\": [\"Point réglementaire précis 1 avec référence\", \"Point précis 2...\", \"...\"],\n"
        "  \"expert_explanation\": \"Analyse experte approfondie : mécanismes, enjeux, jurisprudence, évolutions récentes\",\n"
        "  \"operational_impact\": [\"Impact opérationnel concret 1\", \"Obligation pratique 2\", \"Sanction en cas de non-respect : ...\"],\n"
        "  \"limitations\": \"Points nécessitant vérification auprès des textes officiels les plus récents\"\n"
        "}\n\n"

        f"QUESTION : {question}\n"
    )


async def answer(
    *,
    question: str,
    organization_id: Optional[str] = None,
    category: Optional[str] = None,
) -> dict[str, Any]:
    """
    Point d'entrée principal.
    Retourne la réponse, les sources utilisées et les métadonnées.
    """
    if not (question or "").strip():
        raise ValueError("La question ne peut pas être vide.")

    strategy, sources = await retrieve(
        question=question,
        organization_id=organization_id,
        category=category,
    )

    def _generate() -> str:
        llm = get_llm()
        if sources:
            context = _build_context(sources)
            prompt = _prompt_with_sources(question, context)
        else:
            prompt = _prompt_no_sources(question)
        return llm.invoke(prompt).content

    response_text = await asyncio.to_thread(_generate)

    # Sources dédupliquées par fichier pour l'affichage
    seen: set[str] = set()
    sources_summary = []
    for s in sources:
        meta = s.get("metadata") or {}
        fn = meta.get("filename") or s.get("filename") or ""
        if fn and fn not in seen:
            seen.add(fn)
            sources_summary.append({
                "filename": fn,
                "scope": s.get("scope", ""),
                "category": meta.get("category"),
                "best_score": round(s.get("score", 0.0), 4),
            })

    return {
        "answer": response_text,
        "strategy": strategy,
        "sources_used": sources_summary,
        "chunks_retrieved": len(sources),
        "has_sources": bool(sources),
        "organization_id": organization_id,
        "category": category,
    }


# ---------------------------------------------------------------------------
# UTILITAIRES
# ---------------------------------------------------------------------------

async def list_documents(
    *,
    scope: Optional[str] = None,
    organization_id: Optional[str] = None,
    category: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Liste les documents indexés, groupés par fichier."""

    def _sync():
        to_query = []
        if scope == "LOCAL" or (scope is None and organization_id):
            to_query.append((cfg.LOCAL_COLLECTION, "LOCAL"))
        if scope == "GLOBAL" or scope is None:
            to_query.append((cfg.GLOBAL_COLLECTION, "GLOBAL"))

        results = []
        for coll_name, coll_scope in to_query:
            col = get_collection(coll_name)
            match: dict = {"scope": coll_scope}
            if coll_scope == "LOCAL" and organization_id:
                match["organization_id"] = organization_id
            if category:
                match["category"] = category

            pipeline = [
                {"$match": match},
                {"$group": {
                    "_id": {"filename": "$filename", "category": "$category", "scope": "$scope"},
                    "chunk_count": {"$sum": 1},
                    "created_at": {"$min": "$created_at"},
                }},
                {"$project": {
                    "_id": 0,
                    "filename": "$_id.filename",
                    "category": "$_id.category",
                    "scope": "$_id.scope",
                    "chunk_count": 1,
                    "created_at": 1,
                }},
                {"$sort": {"filename": 1}},
            ]
            results.extend(list(col.aggregate(pipeline)))
        return results

    return await asyncio.to_thread(_sync)


async def delete_document(
    *,
    filename: str,
    organization_id: Optional[str] = None,
    scope: Optional[str] = None,
) -> dict[str, Any]:
    """Supprime tous les chunks d'un document."""
    resolved_scope = scope or ("LOCAL" if organization_id else "GLOBAL")
    coll_name = cfg.LOCAL_COLLECTION if resolved_scope == "LOCAL" else cfg.GLOBAL_COLLECTION

    def _sync():
        col = get_collection(coll_name)
        filt: dict = {"scope": resolved_scope, "filename": filename}
        if resolved_scope == "LOCAL" and organization_id:
            filt["organization_id"] = organization_id
        result = col.delete_many(filt)
        return {
            "deleted_chunks": result.deleted_count,
            "filename": filename,
            "scope": resolved_scope,
        }

    return await asyncio.to_thread(_sync)
