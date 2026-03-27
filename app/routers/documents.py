import os
import shutil
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse

from app.core.deps import get_current_user, get_org_admin
from app.models.documents import (
    create_document,
    get_document_by_id,
    list_documents,
    list_org_document_categories,
    create_org_document_category,
    rename_org_document_category,
    delete_org_document_category,
    update_document_metadata,
    delete_document,
    update_document_status,
    update_document_chunks_count,
    get_document_stats,
)
from app.schemas.documents import (
    DocumentPublic,
    DocumentListResponse,
    DocumentUpdate,
    DocumentStats,
    DocumentDepartmentAssignment,
)
from app.models.document_assignment import (
    assign_document_to_departments,
    get_departments_for_document,
    get_documents_for_department,
)
from app.services.document_extractor import extract_document_content
from app.services.rag_new_service import ingest_text_document, delete_document as rag_delete_document

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)

# Configuration
UPLOAD_DIR = Path("uploads/documents")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.get("/categories")
async def list_org_categories(current_user: dict = Depends(get_org_admin)):
    organization_id = str(current_user["organization_id"])
    return await list_org_document_categories(organization_id)


@router.post("/categories")
async def create_org_category(payload: dict, current_user: dict = Depends(get_org_admin)):
    organization_id = str(current_user["organization_id"])
    name = (payload or {}).get("name")
    try:
        return await create_org_document_category(organization_id, str(name or "").strip())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.put("/categories/{name}")
async def update_org_category(name: str, payload: dict, current_user: dict = Depends(get_org_admin)):
    organization_id = str(current_user["organization_id"])
    new_name = (payload or {}).get("name")
    try:
        return await rename_org_document_category(organization_id, name, str(new_name or "").strip())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.delete("/categories/{name}")
async def delete_org_category(name: str, current_user: dict = Depends(get_org_admin)):
    organization_id = str(current_user["organization_id"])
    try:
        return await delete_org_document_category(organization_id, name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/upload", response_model=DocumentPublic)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(...),
    subcategory: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # JSON string ou comma-separated
    description: Optional[str] = Form(None),
    current_user: dict = Depends(get_org_admin),
):
    """
    Upload et indexe un document (PDF, Word, Excel).
    """
    organization_id = str(current_user["organization_id"])
    user_id = str(current_user["id"])

    existing_categories = await list_org_document_categories(organization_id)
    if not any((c.get("name") or "").strip() == (category or "").strip() for c in existing_categories):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Catégorie invalide. Crée la catégorie avant d'uploader le document.",
        )

    # Valider le type de fichier
    file_ext = Path(file.filename).suffix.lower()
    file_type_map = {
        ".pdf": "pdf",
        ".docx": "word",
        ".doc": "word",
        ".xlsx": "excel",
        ".xls": "excel",
        ".jpg": "image",
        ".jpeg": "image",
        ".png": "image",
        ".gif": "image",
        ".bmp": "image",
        ".tiff": "image",
        ".tif": "image",
    }
    
    if file_ext not in file_type_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type de fichier non supporté. Formats acceptés: PDF, Word (.docx), Excel (.xlsx, .xls), Images (.jpg, .jpeg, .png, .gif, .bmp, .tiff)",
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
    org_dir = UPLOAD_DIR / organization_id
    org_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{user_id}_{file.filename}"
    file_path = org_dir / filename
    
    with open(file_path, "wb") as f:
        f.write(content)

    # Parser les tags
    tags_list = []
    if tags:
        if tags.startswith("["):
            import json
            tags_list = json.loads(tags)
        else:
            tags_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Créer le document dans MongoDB
    document_id = await create_document(
        organization_id=organization_id,
        uploaded_by=user_id,
        filename=filename,
        original_filename=file.filename,
        file_type=file_type,
        file_path=str(file_path),
        file_size=file_size,
        category=category,
        subcategory=subcategory,
        tags=tags_list,
        description=description,
    )

    # Traitement asynchrone (pour l'instant synchrone)
    try:
        await process_document(document_id, str(file_path), file_type, category, organization_id)
    except HTTPException:
        # Re-lancer les HTTPException telles quelles
        raise
    except ValueError as ve:
        # Erreurs de validation (PDF vide, protégé, scanné, etc.)
        error_msg = str(ve)
        logger.error(f"Erreur de validation lors du traitement du document {document_id}: {error_msg}")
        try:
            await update_document_status(document_id, "error")
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )
    except FileNotFoundError as fe:
        # Fichier introuvable
        error_msg = str(fe)
        logger.error(f"Fichier introuvable lors du traitement du document {document_id}: {error_msg}")
        try:
            await update_document_status(document_id, "error")
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_msg,
        )
    except Exception as e:
        # Autres erreurs
        error_msg = f"Erreur lors du traitement du document: {str(e)}"
        logger.error(f"Erreur lors du traitement du document {document_id}: {error_msg}", exc_info=True)
        try:
            await update_document_status(document_id, "error")
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )

    # Récupérer le document créé
    doc = await get_document_by_id(document_id, organization_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document non trouvé après création",
        )

    from app.models.documents import _document_doc_to_public
    return _document_doc_to_public(doc)


async def process_document(
    document_id: str,
    file_path: str,
    file_type: str,
    category: str,
    organization_id: str,
):
    """Traite un document: extraction, découpage, embeddings, sauvegarde."""
    try:
        await update_document_status(document_id, "processing")
    except Exception as e:
        logger.warning(f"Impossible de mettre à jour le statut en 'processing': {e}")

    try:
        # 1. Extraire le contenu
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Le fichier n'existe pas: {file_path}")

        try:
            full_text, chunks_raw = await extract_document_content(file_path, file_type)
        except ValueError as ve:
            msg = str(ve)
            msg_l = msg.lower()
            if (
                "aucun texte n'a pu être extrait" in msg_l
                or "aucun texte n'a pu etre extrait" in msg_l
                or "ocr" in msg_l and "aucun texte" in msg_l
            ):
                if file_type == "pdf":
                    try:
                        from app.services.document_extractor import _ocr_pdf_with_tesseract
                        full_text, chunks_raw = _ocr_pdf_with_tesseract(file_path)
                    except Exception:
                        await update_document_status(document_id, "ocr_required")
                        return
                else:
                    await update_document_status(document_id, "ocr_required")
                    return
            raise

        if not chunks_raw:
            raise ValueError("Aucun contenu extrait du document")

        # 2. Indexer via le nouveau pipeline RAG (chunking + embeddings Atlas)
        _, _, chunk_count, _ = await ingest_text_document(
            filename=os.path.basename(file_path),
            text=full_text,
            organization_id=organization_id,
            category=category,
            scope="LOCAL",
            metadata={
                "source": "ORG_DOCUMENT",
                "document_id": document_id,
                "file_type": file_type,
                "category": category,
                "organization_id": organization_id,
            },
        )

        await update_document_chunks_count(document_id, chunk_count)
        await update_document_status(document_id, "indexed", full_text)

    except ValueError as ve:
        # Erreurs de validation (PDF vide, protégé, etc.)
        error_msg = str(ve)
        logger.error(f"Erreur de validation lors du traitement: {error_msg}")
        await update_document_status(document_id, "error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    except FileNotFoundError as fe:
        # Fichier introuvable
        error_msg = str(fe)
        logger.error(f"Fichier introuvable: {error_msg}")
        await update_document_status(document_id, "error")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_msg
        )
    except Exception as e:
        # Autres erreurs
        error_msg = f"Erreur lors du traitement du document: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await update_document_status(document_id, "error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )


@router.get("", response_model=DocumentListResponse)
async def get_documents(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_org_admin),
):
    """Liste les documents ORG de l'organisation (admin uniquement)."""
    organization_id = str(current_user["organization_id"])
    documents, total = await list_documents(
        organization_id=organization_id,
        category=category,
        status=status,
        search=search,
        skip=skip,
        limit=limit,
    )
    # Ajouter les départements assignés pour chaque document
    for document in documents:
        departments = await get_departments_for_document(document["id"])
        document["departments"] = departments
    return DocumentListResponse(documents=documents, total=total)


@router.get("/user/my-documents", response_model=DocumentListResponse)
async def get_user_documents(
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère les documents ORG assignés au département de l'utilisateur connecté.
    Filtre uniquement avec current_user.organization_id + current_user.department_id (sans paramètre).
    """
    user_org_id = current_user.get("organization_id")
    user_dept_id = current_user.get("department_id")
    
    # Si pas d'organisation ou pas de département, retourner liste vide
    if not user_org_id or not user_dept_id:
        return DocumentListResponse(documents=[], total=0)
    
    try:
        # Récupérer uniquement les documents assignés au département de l'utilisateur
        documents = await get_documents_for_department(str(user_dept_id), str(user_org_id))
        
        return DocumentListResponse(documents=documents, total=len(documents))
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des documents: {str(e)}",
        )


@router.get("/stats", response_model=DocumentStats)
async def get_stats(current_user: dict = Depends(get_org_admin)):
    """Récupère les statistiques des documents."""
    organization_id = str(current_user["organization_id"])
    stats = await get_document_stats(organization_id)
    return DocumentStats(**stats)


# Routes avec sous-chemins doivent être définies AVANT les routes simples avec {document_id}
@router.post("/{document_id}/reindex")
async def reindex_document(
    document_id: str,
    current_user: dict = Depends(get_org_admin),
):
    """Re-indexe un document."""
    logger.info(f"Tentative de re-indexation du document {document_id}")
    organization_id = str(current_user["organization_id"])
    logger.info(f"Organization ID: {organization_id}")
    
    try:
        doc = await get_document_by_id(document_id, organization_id)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du document {document_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération du document: {str(e)}",
        )
    
    if not doc:
        logger.warning(f"Document {document_id} non trouvé pour l'organisation {organization_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document non trouvé",
        )
    
    logger.info(f"Document trouvé: {doc.get('filename', 'N/A')}")

    file_path = doc.get("file_path")
    file_type = doc.get("file_type")
    category = doc.get("category")

    # Vérifier que le fichier existe
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier n'existe pas: {file_path}",
        )

    try:
        # Supprimer les anciens chunks du nouveau RAG
        await rag_delete_document(
            filename=os.path.basename(file_path),
            organization_id=organization_id,
            scope="LOCAL",
        )
        logger.info(f"Anciens chunks supprimés pour le document {document_id}")

        # Réinitialiser le compteur de chunks
        await update_document_chunks_count(document_id, 0)

        # Re-indexer le document
        await process_document(document_id, file_path, file_type, category, organization_id)
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


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Télécharge un document ORG.
    Admin : peut télécharger tous les documents de son organisation.
    User : peut télécharger uniquement les documents assignés à son département.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    user_dept_id = current_user.get("department_id")
    
    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être associé à une organisation pour télécharger des documents.",
        )
    
    doc = await get_document_by_id(document_id, str(user_org_id))
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document non trouvé",
        )
    
    # Vérifier que c'est un document ORG
    if doc.get("scope") != "ORG":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ce document n'est pas un document organisationnel.",
        )
    
    has_access = False
    
    # Admin peut télécharger toutes les ressources de son org
    if user_role == "admin":
        has_access = True
    
    # User peut télécharger seulement les documents assignés à son département ET de son organisation
    if not has_access and user_dept_id:
        # Vérifier d'abord que le document appartient à l'organisation de l'utilisateur
        if doc.get("organization_id") == str(user_org_id):
            departments = await get_departments_for_document(document_id)
            dept_ids = [d["id"] for d in departments]
            if str(user_dept_id) in dept_ids:
                has_access = True
    
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'avez pas accès à ce document.",
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


@router.get("/{document_id}", response_model=DocumentPublic)
async def get_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère un document ORG par son ID.
    Admin : peut voir tous les documents de son organisation.
    User : peut voir uniquement les documents assignés à son département.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    user_dept_id = current_user.get("department_id")
    
    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être associé à une organisation pour accéder aux documents.",
        )
    
    doc = await get_document_by_id(document_id, str(user_org_id))
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document non trouvé",
        )
    
    # Vérifier que c'est un document ORG (pas GLOBAL)
    if doc.get("scope") != "ORG":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ce document n'est pas un document organisationnel.",
        )
    
    # Admin peut voir toutes les ressources de son org
    if user_role == "admin":
        departments = await get_departments_for_document(document_id)
        doc["departments"] = departments
        from app.models.documents import _document_doc_to_public
        return _document_doc_to_public(doc)
    
    # User peut voir seulement les documents assignés à son département ET de son organisation
    if user_dept_id:
        # Vérifier que le document appartient à l'organisation de l'utilisateur
        if doc.get("organization_id") != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas accès à ce document.",
            )
        
        # Vérifier que le document est assigné au département de l'utilisateur
        departments = await get_departments_for_document(document_id)
        dept_ids = [d["id"] for d in departments]
        if str(user_dept_id) in dept_ids:
            doc["departments"] = departments
            from app.models.documents import _document_doc_to_public
            return _document_doc_to_public(doc)
    
    # Si pas de département ou document non assigné au département
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Vous n'avez pas accès à ce document. Il n'est pas assigné à votre département.",
    )


@router.put("/{document_id}", response_model=DocumentPublic)
async def update_document(
    document_id: str,
    update_data: DocumentUpdate,
    current_user: dict = Depends(get_org_admin),
):
    """Met à jour les métadonnées d'un document."""
    organization_id = str(current_user["organization_id"])
    
    await update_document_metadata(
        document_id=document_id,
        organization_id=organization_id,
        category=update_data.category,
        subcategory=update_data.subcategory,
        tags=update_data.tags,
        description=update_data.description,
        status=update_data.status,
    )

    doc = await get_document_by_id(document_id, organization_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document non trouvé",
        )
    from app.models.documents import _document_doc_to_public
    return _document_doc_to_public(doc)


@router.delete("/{document_id}")
async def delete_document_endpoint(
    document_id: str,
    current_user: dict = Depends(get_org_admin),
):
    """Supprime un document et ses chunks."""
    organization_id = str(current_user["organization_id"])
    
    # Récupérer le document pour supprimer le fichier
    doc = await get_document_by_id(document_id, organization_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document non trouvé",
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
            organization_id=organization_id,
            scope="LOCAL",
        )
    except Exception as e:
        logger.warning(f"Impossible de supprimer les chunks RAG: {e}")

    # Supprimer de MongoDB
    success = await delete_document(document_id, organization_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document non trouvé",
        )

    # Supprimer les affectations aux départements (si document ORG)
    from app.core.db import get_database
    from bson import ObjectId
    db = get_database()
    try:
        doc_oid = ObjectId(document_id)
        await db["document_department_assignments"].delete_many({"document_id": doc_oid})
    except Exception:
        pass
    
    return {"message": "Document supprimé avec succès"}


@router.post("/{document_id}/assign-departments")
async def assign_document_to_departments_endpoint(
    document_id: str,
    assignment: DocumentDepartmentAssignment,
    current_user: dict = Depends(get_org_admin),
):
    """
    Affecte un document ORG à plusieurs départements.
    Admin-only. Valide que le document et tous les départements appartiennent à la même organisation.
    """
    user_org_id = str(current_user["organization_id"])
    
    try:
        doc = await get_document_by_id(document_id, user_org_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document introuvable.",
            )
        
        # Vérifier que c'est un document ORG
        if doc.get("scope") != "ORG":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Seuls les documents organisationnels peuvent être affectés aux départements.",
            )
        
        try:
            success = await assign_document_to_departments(document_id, assignment.department_ids, user_org_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de l'affectation du document.",
            )
        
        return {"message": "Document affecté aux départements avec succès."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de l'affectation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'affectation: {str(e)}",
        )

