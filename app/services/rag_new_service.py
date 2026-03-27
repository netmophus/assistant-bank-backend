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
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

load_dotenv()


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
        kwargs: dict[str, Any] = {}
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
) -> Tuple[str, str, List[Dict[str, Any]], Dict[str, Any]]:
    if not (question or "").strip():
        raise ValueError("La question ne peut pas être vide.")

    # Compat: respect de allow_global (le router calcule ce bool via licence)
    if organization_id and not allow_global:
        strategy, sources = await asyncio.to_thread(lambda: ("LOCAL", []))  # placeholder
        strategy, sources = await retrieve(question=question, organization_id=organization_id, category=category)
        if strategy in {"GLOBAL", "MERGED"}:
            strategy, sources = ("LOCAL", [])
    else:
        strategy, sources = await retrieve(question=question, organization_id=organization_id, category=category)

    def _generate() -> str:
        llm = get_llm()
        if sources:
            context = _build_context(sources)
            prompt = _prompt_with_sources(question, context)
        else:
            prompt = _prompt_no_sources(question)
        return llm.invoke(prompt).content

    raw_answer = await asyncio.to_thread(_generate)

    debug: Dict[str, Any] = {
        "used_retrieval": bool(sources) and str(strategy).upper() in {"GLOBAL", "LOCAL", "MERGED"},
        "usedRetrieval": bool(sources) and str(strategy).upper() in {"GLOBAL", "LOCAL", "MERGED"},
        "mode": str(strategy).upper() if sources else "LLM_ONLY",
        "sources_used": _build_sources_used_compat(sources),
    }

    structured_payload = _extract_json_object(raw_answer)
    structured = _coerce_structured_answer(structured_payload, fallback_answer=(raw_answer or ""))
    debug["structured_answer"] = structured

    return str(structured.get("answer") or raw_answer or "").strip(), str(strategy).upper(), list(sources or []), debug


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
        meta = s.get("metadata") or {}
        filename = _clean_filename(meta.get("filename") or s.get("filename") or "Document")
        scope = s.get("scope", "")
        score = s.get("score", 0.0)
        content = (s.get("content") or "").strip()
        parts.append(
            f"[Extrait {i} | {filename} | {scope} | score={score:.3f}]\n{content}"
        )
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
        "Tu es un assistant expert, précis et rigoureux.\n"
        "Tu dois produire une réponse structurée en 3 parties obligatoires, dans cet ordre, tout en respectant strictement la différence entre ce qui vient des sources et ce qui vient du modèle.\n\n"
        "Règles strictes (obligatoires):\n"
        "- Toujours indiquer clairement ce qui provient des extraits vs ce qui est une explication générale.\n"
        "- Si la question demande une comparaison entre deux concepts (ex: 'A vs B', 'différence entre A et B', 'compare A et B'), la Partie 1 doit obligatoirement être structurée en DEUX sous-sections séparées et clairement titrées (une par concept), et tu dois associer chaque point sourcé à la bonne sous-section.\n"
        "- Partie 1 est PRIORITAIRE: elle doit être aussi détaillée que possible, et ne doit JAMAIS être raccourcie si les extraits contiennent de nombreux points précis.\n"
        "- Ne JAMAIS résumer ni généraliser ce que les extraits disent en détail dans la Partie 1. Si les extraits donnent une liste de conditions/étapes/critères, tu dois toutes les lister.\n"
        "- Ne jamais inventer des règles absentes des extraits dans la Partie 1.\n"
        "- Si un aspect n'est pas couvert par les extraits, le dire explicitement en Partie 1 (ex: 'Non précisé dans les extraits retrouvés.'), puis seulement compléter en Partie 2/3.\n"
        "- Partie 2/3 ne doivent jamais contredire la Partie 1.\n"
        "- Les conseils de la Partie 3 doivent être cohérents avec les extraits et ne jamais les contredire.\n"
        "- Tu dois répondre UNIQUEMENT en JSON valide (aucun texte hors JSON).\n"
        "- Le champ 'answer' doit être du Markdown (mais toujours à l'intérieur de la valeur string JSON).\n\n"
        "Mapping obligatoire des 3 parties vers le JSON:\n"
        "- Partie 1 — Réponse détaillée ancrée dans les sources -> grounded_summary (liste numérotée de points factuels, exhaustive, avec citations de fichier)\n"
        "- Partie 2 — Interprétation et mise en contexte -> expert_explanation (peut inclure des connaissances générales, mais le signaler explicitement: 'D'un point de vue général...')\n"
        "- Partie 3 — Conseils pratiques et exemples concrets -> operational_impact (2 à 4 conseils actionnables + au moins 1 exemple concret)\n\n"
        "Schéma JSON attendu:\n"
        "{\n"
        "  \"answer\": \"TEXTE EN 3 PARTIES OBLIGATOIRES (dans cet ordre): Partie 1 / Partie 2 / Partie 3\",\n"
        "  \"direct_answer\": \"réponse directe si possible (courte, ancrée)\",\n"
        "  \"reference\": {\n"
        "    \"textName\": \"nom exact si présent\",\n"
        "    \"textNumber\": \"numéro/référence si présent\",\n"
        "    \"article\": \"article si présent\",\n"
        "    \"section\": \"section/chapitre si présent\",\n"
        "    \"scope\": \"GLOBAL|LOCAL\"\n"
        "  },\n"
        "  \"grounded_summary\": [\"Partie 1: (liste numérotée) points factuels détaillés issus des extraits, avec nom de fichier pour chaque point\"],\n"
        "  \"expert_explanation\": \"Partie 2: interprétation + mise en contexte (si général: commencer par D'un point de vue général...)\",\n"
        "  \"operational_impact\": [\"Partie 3: conseil actionnable 1\", \"conseil actionnable 2\", \"EXEMPLE: ...\"],\n"
        "  \"limitations\": \"ce que les extraits ne permettent pas d'affirmer / ce qui manque\"\n"
        "}\n\n"
        "Exigences de contenu: \n"
        "- answer: doit contenir les 3 parties dans cet ordre, au format Markdown.\n"
        "  - Utilise '##' pour le titre de chaque partie.\n"
        "  - Utilise '###' pour les sous-sections (notamment en cas de comparaison).\n"
        "  - Mets '---' entre chaque partie.\n"
        "  - Pour les listes de conditions/critères, utilise des tableaux Markdown (| Col | Col |).\n"
        "  - Les citations (nom de fichier / source) doivent être en italique.\n"
        "  - Les conseils doivent être une liste numérotée, avec un titre en gras dans chaque item.\n"
        "  - L'exemple doit être dans un bloc '>' et précédé de '💡'.\n"
        "- Partie 1 (grounded_summary ET aussi recopiée dans la Partie 1 de answer):\n"
        "  - Utilise une liste numérotée (1., 2., 3., ...).\n"
        "  - Chaque item doit citer le nom du fichier source (tel qu'affiché dans les extraits).\n"
        "  - Chaque item doit reprendre les conditions/critères/étapes en détail; si une condition est exprimée textuellement, recopie sa formulation entre guillemets.\n"
        "  - Interdiction de remplacer une liste précise par une paraphrase vague.\n"
        "- Partie 2 (expert_explanation): expliquer le sens + implications; si tu ajoutes du général, commence par 'D'un point de vue général...'.\n"
        "- Partie 3 (operational_impact): 2 à 4 conseils actionnables + au moins 1 exemple concret (préfixe 'EXEMPLE:').\n"
        "- limitations: explicite et factuel.\n\n"
        f"Extraits retrouvés:\n{context}\n\n"
        f"Question utilisateur:\n{question}\n"
    )


def _prompt_no_sources(question: str) -> str:
    return (
        "Aucun document pertinent n'a été trouvé dans les bases de connaissances pour cette question.\n\n"
        "Tu dois répondre UNIQUEMENT en JSON valide (aucun texte hors JSON).\n"
        "Le champ 'answer' doit être du Markdown (mais à l'intérieur de la valeur string JSON).\n"
        "Règle: grounded_summary doit indiquer explicitement qu'aucune source n'a été trouvée.\n\n"
        "Schéma JSON attendu:\n"
        "{\n"
        "  \"answer\": \"réponse utile (générale)\",\n"
        "  \"direct_answer\": \"\",\n"
        "  \"reference\": {\"textName\":\"\",\"textNumber\":\"\",\"article\":\"\",\"section\":\"\",\"scope\":\"\"},\n"
        "  \"grounded_summary\": [\"Aucune source pertinente trouvée dans la base\"],\n"
        "  \"expert_explanation\": \"D'un point de vue général...\",\n"
        "  \"operational_impact\": [\"Conseil 1\", \"Conseil 2\", \"EXEMPLE: ...\"],\n"
        "  \"limitations\": \"Impossible de confirmer des règles spécifiques faute de sources.\"\n"
        "}\n\n"
        f"Question utilisateur:\n{question}\n"
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
