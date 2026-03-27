import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse

from app.core.deps import get_superadmin, get_current_user
from app.models.documents import (
    create_document,
    get_global_document_by_id,
    list_global_documents,
    update_document_metadata,
    delete_document,
    update_document_status,
    update_document_chunks_count,
    update_global_document_status,
    _document_doc_to_public,
)
from app.models.global_knowledge_category import (
    create_category,
    get_category_by_id,
    list_categories,
    update_category,
    delete_category,
    toggle_category_active,
)
from app.schemas.global_knowledge import (
    GlobalDocumentPublic,
    GlobalDocumentListResponse,
    GlobalDocumentUpdate,
)
from app.schemas.global_knowledge_category import (
    GlobalKnowledgeCategoryCreate,
    GlobalKnowledgeCategoryUpdate,
    GlobalKnowledgeCategoryPublic,
)
from app.services.document_extractor import extract_document_content
from app.services.rag_new_service import ingest_text_document, delete_document as rag_delete_document

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/global-knowledge",
    tags=["global-knowledge"],
)

# Configuration
UPLOAD_DIR = Path("uploads/global_knowledge")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


async def process_global_document(
    document_id: str,
    file_path: str,
    file_type: str,
    category: str,
    status: str = "published",
):
    """Traite un document global: extraction, découpage, embeddings, sauvegarde."""
    try:
        await update_document_status(document_id, "processing")
    except Exception as e:
        logger.warning(f"Impossible de mettre à jour le statut en 'processing': {e}")

    try:
        # 1. Extraire le contenu
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier n'existe pas: {file_path}")

        full_text, chunks_raw = await extract_document_content(file_path, file_type)

        if not chunks_raw:
            raise ValueError("Aucun contenu extrait du document")

        # 2. Indexer via le nouveau pipeline RAG (chunking + embeddings Atlas)
        _, _, chunk_count, _ = await ingest_text_document(
            filename=os.path.basename(file_path),
            text=full_text,
            organization_id=None,
            category=category,
            scope="GLOBAL",
            metadata={
                "source": "GLOBAL_DOCUMENT",
                "document_id": document_id,
                "file_type": file_type,
                "category": category,
            },
        )

        # 3. Mettre à jour le document
        from app.core.db import get_database
        db = get_database()
        await db["documents"].update_one(
            {"_id": ObjectId(document_id), "scope": "GLOBAL"},
            {"$set": {
                "total_chunks": chunk_count,
                "status": status,
                "extracted_text": full_text,
            }}
        )

    except Exception as e:
        logger.error(f"Erreur lors du traitement: {e}")
        await update_document_status(document_id, "error")
        raise


@router.post("/upload", response_model=GlobalDocumentPublic)
async def upload_global_document(
    file: UploadFile = File(...),
    titre: str = Form(...),
    description: str = Form(""),
    category: str = Form(...),  # Slug de la catégorie
    subcategory: Optional[str] = Form(None),
    authority: str = Form(""),
    reference: str = Form(""),
    version: str = Form("1.0"),
    effective_date: Optional[str] = Form(None),
    current_user: dict = Depends(get_superadmin),
):
    """
    Upload un document global (statut: draft).
    Seul le superadmin peut uploader des documents globaux.
    """
    user_id = str(current_user["id"])

    # Valider le type de fichier
    file_ext = Path(file.filename).suffix.lower()
    file_type_map = {
        ".pdf": "pdf",
        ".docx": "word",
        ".doc": "word",
        ".xlsx": "excel",
        ".xls": "excel",
    }
    
    if file_ext not in file_type_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type de fichier non supporté. Formats acceptés: PDF, Word (.docx), Excel (.xlsx, .xls)",
        )

    file_type = file_type_map[file_ext]

    # Lire le fichier
    content = await file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fichier trop volumineux. Taille max: {MAX_FILE_SIZE / 1024 / 1024}MB",
        )

    # Sauvegarder le fichier
    filename = f"{user_id}_{file.filename}"
    file_path = UPLOAD_DIR / filename
    
    with open(file_path, "wb") as f:
        f.write(content)

    # Parser effective_date si fournie
    effective_date_obj = None
    if effective_date:
        try:
            effective_date_obj = datetime.fromisoformat(effective_date.replace("Z", "+00:00"))
        except Exception:
            pass

    # Créer le document dans MongoDB
    document_id = await create_document(
        organization_id=None,  # Pas d'organisation pour les documents globaux
        uploaded_by=user_id,
        filename=filename,
        original_filename=file.filename,
        file_type=file_type,
        file_path=str(file_path),
        file_size=file_size,
        category=category,
        subcategory=subcategory,
        scope="GLOBAL",
        titre=titre,
        authority=authority,
        reference=reference,
        version=version,
        effective_date=effective_date_obj,
    )

    # Récupérer le document créé
    doc = await get_global_document_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document non trouvé après création",
        )

    # Lancer le traitement en arrière-plan (chunking + embeddings)
    # On ne bloque pas la réponse pour éviter les timeouts
    try:
        import asyncio
        # Créer une tâche en arrière-plan pour le traitement
        asyncio.create_task(
            process_global_document(
                document_id=document_id,
                file_path=str(file_path),
                file_type=file_type,
                category=category,
                status="published",  # Publier automatiquement après traitement
            )
        )
        logger.info(f"Traitement en arrière-plan lancé pour le document {document_id}")
    except Exception as e:
        logger.error(f"Erreur lors du lancement du traitement en arrière-plan: {e}")
        # On ne lève pas d'exception pour ne pas bloquer l'upload

    return _document_doc_to_public(doc)


# ==================== CATEGORIES ENDPOINTS (DOIT ÊTRE AVANT /{document_id}) ====================

from app.models.global_knowledge_category import (
    create_category,
    get_category_by_id,
    list_categories,
    update_category,
    delete_category,
    toggle_category_active,
)
from app.schemas.global_knowledge_category import (
    GlobalKnowledgeCategoryCreate,
    GlobalKnowledgeCategoryUpdate,
    GlobalKnowledgeCategoryPublic,
)


@router.get("/categories", response_model=List[GlobalKnowledgeCategoryPublic])
async def list_global_knowledge_categories(
    include_inactive: bool = False,
    current_user: dict = Depends(get_superadmin),
):
    """Liste toutes les catégories de la base de connaissances globale."""
    categories = await list_categories(include_inactive=include_inactive)
    return categories


@router.post("/categories", response_model=GlobalKnowledgeCategoryPublic)
async def create_global_knowledge_category(
    category_data: GlobalKnowledgeCategoryCreate,
    current_user: dict = Depends(get_superadmin),
):
    """Crée une nouvelle catégorie."""
    try:
        logger.info(f"Création catégorie: name={category_data.name}, slug={category_data.slug}, description={category_data.description}")
        category = await create_category(
            name=category_data.name,
            slug=category_data.slug,
            description=category_data.description,
        )
        return category
    except ValueError as e:
        logger.warning(f"Erreur validation catégorie: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la création de la catégorie: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur serveur: {str(e)}",
        )


@router.get("/categories/{category_id}", response_model=GlobalKnowledgeCategoryPublic)
async def get_global_knowledge_category(
    category_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Récupère une catégorie par son ID."""
    category = await get_category_by_id(category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Catégorie non trouvée",
        )
    return category


@router.put("/categories/{category_id}", response_model=GlobalKnowledgeCategoryPublic)
async def update_global_knowledge_category(
    category_id: str,
    category_data: GlobalKnowledgeCategoryUpdate,
    current_user: dict = Depends(get_superadmin),
):
    """Met à jour une catégorie."""
    try:
        category = await update_category(
            category_id=category_id,
            name=category_data.name,
            slug=category_data.slug,
            description=category_data.description,
            is_active=category_data.is_active,
        )
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Catégorie non trouvée",
            )
        return category
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/categories/{category_id}")
async def delete_global_knowledge_category(
    category_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Supprime une catégorie."""
    try:
        success = await delete_category(category_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Catégorie non trouvée",
            )
        return {"message": "Catégorie supprimée avec succès"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/categories/{category_id}/toggle")
async def toggle_global_knowledge_category(
    category_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Active ou désactive une catégorie."""
    category = await toggle_category_active(category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Catégorie non trouvée",
        )
    return category


# ==================== DOCUMENTS ENDPOINTS ====================

@router.get("", response_model=GlobalDocumentListResponse)
async def list_global_documents_endpoint(
    category: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_superadmin),
):
    """Liste les documents globaux (superadmin uniquement pour gestion complète)."""
    documents, total = await list_global_documents(
        category=category,
        status=status,
        skip=skip,
        limit=limit,
    )
    return GlobalDocumentListResponse(documents=documents, total=total)


@router.get("/published", response_model=GlobalDocumentListResponse)
async def list_published_global_documents_endpoint(
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les documents globaux PUBLIÉS uniquement.
    Accessible aux admins d'organisation avec licence active et aux users.
    Utilisé pour la consultation (pas la gestion).
    """
    # Filtrer uniquement les documents publiés
    documents, total = await list_global_documents(
        category=category,
        status="published",  # Forcer status=published
        skip=skip,
        limit=limit,
    )
    return GlobalDocumentListResponse(documents=documents, total=total)


@router.get("/{document_id}", response_model=GlobalDocumentPublic)
async def get_global_document(
    document_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Récupère les détails d'un document global."""
    doc = await get_global_document_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document global non trouvé",
        )
    return _document_doc_to_public(doc)


@router.put("/{document_id}", response_model=GlobalDocumentPublic)
async def update_global_document(
    document_id: str,
    update_data: GlobalDocumentUpdate,
    current_user: dict = Depends(get_superadmin),
):
    """Met à jour les métadonnées d'un document global."""
    doc = await get_global_document_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document global non trouvé",
        )
    
    # Mettre à jour les métadonnées
    update_dict = {}
    if update_data.titre is not None:
        update_dict["titre"] = update_data.titre
    if update_data.description is not None:
        update_dict["description"] = update_data.description
    if update_data.category is not None:
        update_dict["category"] = update_data.category
    if update_data.authority is not None:
        update_dict["authority"] = update_data.authority
    if update_data.reference is not None:
        update_dict["reference"] = update_data.reference
    if update_data.version is not None:
        update_dict["version"] = update_data.version
    if update_data.effective_date is not None:
        update_dict["effective_date"] = update_data.effective_date
    if update_data.status is not None:
        update_dict["status"] = update_data.status
    
    if update_dict:
        from app.core.db import get_database
        db = get_database()
        await db["documents"].update_one(
            {"_id": doc["_id"]},
            {"$set": update_dict}
        )
    
    # Si le statut change, mettre à jour les chunks
    if update_data.status:
        await update_global_document_status(document_id, update_data.status)

    # Récupérer le document mis à jour
    updated_doc = await get_global_document_by_id(document_id)
    return _document_doc_to_public(updated_doc)


@router.post("/{document_id}/publish")
async def publish_global_document(
    document_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Publie un document global (indexe automatiquement si pas encore fait)."""
    doc = await get_global_document_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document global non trouvé",
        )
    
    logger.info(f"Publication document {document_id}, statut actuel: {doc.get('status')}, chunks: {doc.get('total_chunks', 0)}")
    
    # Vérifier si déjà indexé
    if doc.get("total_chunks", 0) == 0:
        # Indexer le document
        try:
            logger.info(f"Indexation du document {document_id} avec statut published")
            await process_global_document(
                document_id=document_id,
                file_path=doc["file_path"],
                file_type=doc["file_type"],
                category=doc["category"],
                status="published",
            )
        except Exception as e:
            logger.error(f"Erreur lors de l'indexation: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erreur lors de l'indexation: {str(e)}",
            )
    else:
        # Mettre à jour le statut seulement
        logger.info(f"Mise à jour du statut du document {document_id} en published")
        await update_global_document_status(document_id, "published", datetime.utcnow())
        
        # Vérifier que la mise à jour a bien fonctionné
        updated_doc = await get_global_document_by_id(document_id)
        if updated_doc:
            logger.info(f"Statut après mise à jour: {updated_doc.get('status')}")
        else:
            logger.warning(f"Document {document_id} non trouvé après mise à jour")
    
    return {"message": "Document publié avec succès"}


@router.post("/{document_id}/archive")
async def archive_global_document(
    document_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Archive un document global."""
    doc = await get_global_document_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document global non trouvé",
        )
    
    await update_global_document_status(document_id, "archived")
    return {"message": "Document archivé avec succès"}


@router.post("/{document_id}/reindex")
async def reindex_global_document(
    document_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Re-indexe un document global."""
    doc = await get_global_document_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document global non trouvé",
        )

    file_path = doc.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier n'existe pas: {file_path}",
        )

    try:
        # Supprimer les anciens chunks du nouveau RAG
        await rag_delete_document(
            filename=os.path.basename(file_path),
            scope="GLOBAL",
        )
        logger.info(f"Anciens chunks supprimés pour le document {document_id}")

        # Réinitialiser le compteur de chunks
        await update_document_chunks_count(document_id, 0)

        # Re-indexer le document avec le statut actuel
        current_status = doc.get("status", "published")
        await process_global_document(
            document_id=document_id,
            file_path=file_path,
            file_type=doc["file_type"],
            category=doc["category"],
            status=current_status,
        )
        return {"message": "Document re-indexé avec succès"}
    except Exception as e:
        logger.error(f"Erreur lors de la re-indexation du document {document_id}: {e}", exc_info=True)
        try:
            await update_document_status(document_id, "error")
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la re-indexation: {str(e)}",
        )


@router.delete("/{document_id}")
async def delete_global_document(
    document_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Supprime un document global et ses chunks."""
    doc = await get_global_document_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document global non trouvé",
        )

    # Supprimer le fichier
    file_path = doc.get("file_path")
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logger.warning(f"Impossible de supprimer le fichier {file_path}: {e}")

    # Supprimer les chunks du nouveau RAG
    try:
        await rag_delete_document(
            filename=os.path.basename(file_path) if file_path else doc.get("filename", ""),
            scope="GLOBAL",
        )
    except Exception as e:
        logger.warning(f"Impossible de supprimer les chunks RAG: {e}")

    # Supprimer de MongoDB (document)
    success = await delete_document(document_id, None)  # organization_id=None pour GLOBAL
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document non trouvé",
        )

    return {"message": "Document global supprimé avec succès"}


@router.get("/{document_id}/download")
async def download_global_document(
    document_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Télécharge le fichier original d'un document global."""
    doc = await get_global_document_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document global non trouvé",
        )

    file_path = doc.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fichier non trouvé",
        )

    return FileResponse(
        path=file_path,
        filename=doc.get("original_filename", doc.get("filename")),
        media_type="application/octet-stream",
    )

