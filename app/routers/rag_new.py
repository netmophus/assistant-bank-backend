from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.deps import get_current_user
from app.models.rag_new_schemas import (
    RagNewDocumentListItem,
    RagNewDocumentListResponse,
    RagNewQueryRequest,
    RagNewQueryResponse,
    RagNewSource,
    RagNewSourceUsed,
    RagNewUploadResponse,
)
from app.models.global_knowledge_category import get_category_by_slug, list_categories
from app.services.rag_new_service import (
    answer_question,
    ingest_document,
    list_knowledge_documents,
    parse_metadata_json,
)


router = APIRouter(prefix="/api/rag-new", tags=["rag-new"])


async def _validate_category_slug(category: str) -> None:
    cat = await get_category_by_slug(category)
    if not cat or not cat.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Catégorie invalide ou inactive",
        )


@router.get("/categories")
async def list_rag_new_categories(current_user: dict = Depends(get_current_user)):
    """Expose les catégories (réutilise global_knowledge_categories).

    - Superadmin: peut inclure les inactives
    - Admin org: catégories actives uniquement
    """

    role = current_user.get("role", "user")
    if role not in {"admin", "superadmin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès interdit")

    include_inactive = role == "superadmin"
    return await list_categories(include_inactive=include_inactive)


@router.get("/documents", response_model=RagNewDocumentListResponse)
async def list_rag_new_documents(
    scope: Optional[str] = None,
    category: Optional[str] = None,
    organization_id: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    role = current_user.get("role", "user")
    if role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès interdit")

    scope_norm = (scope or "").strip().upper() or None
    if scope_norm not in {None, "GLOBAL", "LOCAL"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope invalide")

    if category:
        await _validate_category_slug(category)

    total, docs = await list_knowledge_documents(
        scope=scope_norm,
        organization_id=organization_id,
        category=category,
        offset=offset,
        limit=limit,
    )

    items = [
        RagNewDocumentListItem(
            scope=d.get("scope") or "",
            filename=d.get("filename") or "",
            category=d.get("category"),
            organization_id=d.get("organization_id"),
            chunk_count=int(d.get("chunk_count") or 0),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
        )
        for d in docs
    ]

    return RagNewDocumentListResponse(total=total, offset=offset, limit=limit, items=items)


@router.post("/upload", response_model=RagNewUploadResponse)
async def upload_rag_new_document(
    file: UploadFile = File(...),
    category: str = Form(...),
    metadata_json: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """Upload un document pour la nouvelle approche RAG.

    Règles:
    - Superadmin => stockage GLOBAL (knowledge_global)
    - Admin d'organisation => stockage LOCAL (knowledge_local) isolé par organization_id

    Le document est:
    - extrait en texte
    - découpé en chunks (1000 / overlap 200)
    - vectorisé (OpenAI text-embedding-3-large)
    - upsert dans MongoDB (collections distinctes)
    """

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nom de fichier manquant")

    await _validate_category_slug(category)

    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fichier vide")

        metadata: Dict[str, Any] = parse_metadata_json(metadata_json)
        metadata.setdefault("original_filename", file.filename)
        metadata.setdefault("uploaded_at", datetime.utcnow().isoformat())

        role = current_user.get("role", "user")
        organization_id = current_user.get("organization_id")

        scope: str
        local_org_id: Optional[str] = None
        if role == "superadmin":
            scope = "GLOBAL"
        elif role == "admin" and organization_id:
            scope = "LOCAL"
            local_org_id = str(organization_id)
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès interdit")

        metadata.setdefault("category", category)
        if scope == "LOCAL":
            metadata.setdefault("organization_id", local_org_id)

        collection, document_count, chunk_count, uid, created_at = await ingest_document(
            filename=file.filename,
            file_bytes=file_bytes,
            user_id=None,
            organization_id=local_org_id,
            category=category,
            scope=scope,
            metadata=metadata,
        )

        return RagNewUploadResponse(
            collection=collection,
            document_count=document_count,
            chunk_count=chunk_count,
            user_id=uid,
            created_at=created_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur serveur lors de l'upload RAG: {str(e)}",
        ) from e


@router.post("/query", response_model=RagNewQueryResponse)
async def query_rag_new(payload: RagNewQueryRequest, current_user: dict = Depends(get_current_user)):
    """Question/Réponse via la nouvelle chaîne RAG (priorisation stricte).

    Stratégie:
    1) GLOBAL (threshold > 0.82)
    2) Si pas assez pertinent (<3 docs OU score max < 0.75) => LOCAL (filtré par user_id)
    3) Sinon => LLM sans contexte

    Retourne:
    - réponse
    - stratégie utilisée
    - sources (chunks)
    """

    try:
        role = current_user.get("role", "user")
        organization_id = current_user.get("organization_id")
        org_id: Optional[str] = str(organization_id) if organization_id else None

        allow_global = False
        if role == "superadmin":
            allow_global = True
        elif role in {"admin", "user"}:
            # Les utilisateurs d'une organisation peuvent interroger GLOBAL uniquement si la licence est active.
            # (LOCAL reste isolé par organization_id côté service)
            if org_id:
                from app.models.license import org_has_active_license

                allow_global = await org_has_active_license(org_id)
            elif role == "admin":
                # Un admin sans organisation n'est pas autorisé
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès interdit")

        if payload.category:
            await _validate_category_slug(payload.category)

        answer, strategy, sources, debug = await answer_question(
            question=payload.question,
            organization_id=org_id,
            category=payload.category,
            allow_global=allow_global,
        )

        src_models = [
            RagNewSource(
                id=s.get("id") or "",
                scope=s.get("scope") or ("GLOBAL" if strategy == "GLOBAL" else "LOCAL"),
                score=float(s.get("score") or 0.0),
                content=s.get("content") or "",
                metadata=s.get("metadata") or {},
            )
            for s in sources
        ]

        structured = debug.get("structured_answer") if isinstance(debug, dict) else None
        grounded_summary = []
        helpful_explanation = ""
        direct_answer = ""
        reference = {"textName": "", "textNumber": "", "article": "", "section": "", "scope": ""}
        expert_explanation = ""
        operational_impact: list[str] = []
        limitations = ""
        if isinstance(structured, dict):
            gs = structured.get("grounded_summary")
            if isinstance(gs, list):
                grounded_summary = [str(x) for x in gs if str(x).strip()]
            helpful_explanation = str(structured.get("helpful_explanation") or "")
            direct_answer = str(structured.get("direct_answer") or "")
            ref = structured.get("reference")
            if isinstance(ref, dict):
                reference = {
                    "textName": str(ref.get("textName") or ""),
                    "textNumber": str(ref.get("textNumber") or ""),
                    "article": str(ref.get("article") or ""),
                    "section": str(ref.get("section") or ""),
                    "scope": str(ref.get("scope") or ""),
                }
            expert_explanation = str(structured.get("expert_explanation") or "")
            op = structured.get("operational_impact")
            if isinstance(op, list):
                operational_impact = [str(x) for x in op if str(x).strip()]
            limitations = str(structured.get("limitations") or "")

        used_retrieval = bool((debug or {}).get("used_retrieval")) if isinstance(debug, dict) else False
        usedRetrieval = bool((debug or {}).get("usedRetrieval")) if isinstance(debug, dict) else used_retrieval
        mode = str((debug or {}).get("mode") or strategy)

        sources_used_raw = (debug or {}).get("sources_used") if isinstance(debug, dict) else None
        sources_used: list[RagNewSourceUsed] = []
        if isinstance(sources_used_raw, list):
            for it in sources_used_raw:
                if not isinstance(it, dict):
                    continue
                sources_used.append(
                    RagNewSourceUsed(
                        documentName=str(it.get("documentName") or ""),
                        category=(str(it.get("category")) if it.get("category") is not None else None),
                        scope=str(it.get("scope") or ""),
                        page=(int(it.get("page")) if it.get("page") is not None else None),
                    )
                )

        return RagNewQueryResponse(
            answer=answer,
            direct_answer=direct_answer,
            reference=reference,
            grounded_summary=grounded_summary,
            helpful_explanation=helpful_explanation,
            expert_explanation=expert_explanation,
            operational_impact=operational_impact,
            limitations=limitations,
            used_retrieval=used_retrieval,
            usedRetrieval=usedRetrieval,
            mode=mode,
            sources_used=sources_used,
            strategy=strategy,
            sources=src_models,
            debug=debug,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur serveur lors de la requête RAG: {str(e)}",
        ) from e
