from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from datetime import datetime
from pathlib import Path
from typing import List
import os
import shutil

from app.schemas.ressource import RessourcePublic, RessourceUpdate, RessourceDepartmentAssignment
from app.models.ressource import (
    create_ressource,
    list_ressources_by_org,
    get_ressource_by_id,
    update_ressource,
    delete_ressource,
    assign_ressource_to_departments,
    get_departments_for_ressource,
    get_ressources_for_department,
    UPLOAD_DIR,
)
from app.core.deps import get_current_user
from app.core.db import get_database
from bson import ObjectId

router = APIRouter(
    prefix="/ressources",
    tags=["ressources"],
)


@router.post("", response_model=RessourcePublic)
async def create_ressource_endpoint(
    titre: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Crée une ressource avec un fichier uploadé pour l'organisation de l'admin connecté.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    # Vérifier que l'utilisateur est un admin d'organisation
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent créer des ressources.",
        )
    
    # Vérifier le type de fichier
    allowed_extensions = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".rtf"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type de fichier non autorisé. Formats acceptés: {', '.join(allowed_extensions)}",
        )
    
    try:
        # Sauvegarder le fichier
        org_upload_dir = UPLOAD_DIR / str(user_org_id)
        org_upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Générer un nom de fichier unique
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{file.filename}"
        file_path = org_upload_dir / safe_filename
        
        # Sauvegarder le fichier
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = file_path.stat().st_size
        
        # Créer la ressource
        ressource_data = {
            "titre": titre,
            "description": description,
        }
        
        ressource = await create_ressource(
            ressource_data,
            str(user_org_id),
            str(file_path),
            file.filename,
            file_size,
            file_ext
        )
        
        return ressource
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création de la ressource: {str(e)}",
        )


@router.get("", response_model=List[RessourcePublic])
async def list_ressources_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Liste toutes les ressources de l'organisation de l'admin connecté.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir toutes les ressources.",
        )
    
    try:
        ressources = await list_ressources_by_org(str(user_org_id))
        # Ajouter les départements assignés pour chaque ressource
        for ressource in ressources:
            departments = await get_departments_for_ressource(ressource["id"])
            ressource["departments"] = departments
        return ressources
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des ressources: {str(e)}",
        )


@router.get("/user/my-ressources", response_model=List[RessourcePublic])
async def get_user_ressources_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Récupère les ressources assignées au département de l'utilisateur connecté.
    """
    user_dept_id = current_user.get("department_id")
    
    if not user_dept_id:
        return []
    
    try:
        ressources = await get_ressources_for_department(str(user_dept_id))
        return ressources
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des ressources: {str(e)}",
        )


@router.get("/{ressource_id}", response_model=RessourcePublic)
async def get_ressource_endpoint(
    ressource_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Récupère une ressource par son ID.
    """
    try:
        ressource = await get_ressource_by_id(ressource_id)
        if not ressource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ressource introuvable.",
            )
        
        # Vérifier les permissions
        user_role = current_user.get("role", "user")
        user_org_id = current_user.get("organization_id")
        user_dept_id = current_user.get("department_id")
        
        # Admin peut voir toutes les ressources de son org
        if user_role == "admin" and ressource["organization_id"] == str(user_org_id):
            departments = await get_departments_for_ressource(ressource_id)
            ressource["departments"] = departments
            return ressource
        
        # User peut voir seulement les ressources de son département
        if user_dept_id:
            departments = await get_departments_for_ressource(ressource_id)
            dept_ids = [d["id"] for d in departments]
            if str(user_dept_id) in dept_ids:
                ressource["departments"] = departments
                return ressource
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'avez pas accès à cette ressource.",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération de la ressource: {str(e)}",
        )


@router.get("/{ressource_id}/download")
async def download_ressource_endpoint(
    ressource_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Télécharge le fichier d'une ressource.
    """
    try:
        ressource = await get_ressource_by_id(ressource_id)
        if not ressource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ressource introuvable.",
            )
        
        # Vérifier les permissions
        user_role = current_user.get("role", "user")
        user_org_id = current_user.get("organization_id")
        user_dept_id = current_user.get("department_id")
        
        has_access = False
        
        # Admin peut télécharger toutes les ressources de son org
        if user_role == "admin" and ressource["organization_id"] == str(user_org_id):
            has_access = True
        
        # User peut télécharger seulement les ressources de son département
        if not has_access and user_dept_id:
            departments = await get_departments_for_ressource(ressource_id)
            dept_ids = [d["id"] for d in departments]
            if str(user_dept_id) in dept_ids:
                has_access = True
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas accès à cette ressource.",
            )
        
        file_path = Path(ressource["file_path"])
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fichier introuvable.",
            )
        
        return FileResponse(
            path=str(file_path),
            filename=ressource.get("filename") or ressource.get("file_name") or "ressource",
            media_type="application/octet-stream",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du téléchargement: {str(e)}",
        )


@router.put("/{ressource_id}", response_model=RessourcePublic)
async def update_ressource_endpoint(
    ressource_id: str,
    titre: str = Form(None),
    description: str = Form(None),
    file: UploadFile = File(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Met à jour une ressource (optionnellement avec un nouveau fichier).
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent modifier des ressources.",
        )
    
    try:
        ressource = await get_ressource_by_id(ressource_id)
        if not ressource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ressource introuvable.",
            )
        
        if ressource["organization_id"] != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez modifier que les ressources de votre organisation.",
            )
        
        ressource_data = {}
        if titre is not None:
            ressource_data["titre"] = titre
        if description is not None:
            ressource_data["description"] = description
        
        file_path = None
        filename = None
        file_size = None
        file_type = None
        
        # Si un nouveau fichier est uploadé
        if file:
            # Vérifier le type de fichier
            allowed_extensions = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".rtf"}
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in allowed_extensions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Type de fichier non autorisé. Formats acceptés: {', '.join(allowed_extensions)}",
                )
            
            # Sauvegarder le nouveau fichier
            org_upload_dir = UPLOAD_DIR / str(user_org_id)
            org_upload_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{file.filename}"
            file_path_obj = org_upload_dir / safe_filename
            
            with open(file_path_obj, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            file_path = str(file_path_obj)
            filename = file.filename
            file_size = file_path_obj.stat().st_size
            file_type = file_ext
        
        updated_ressource = await update_ressource(
            ressource_id,
            ressource_data,
            file_path,
            filename,
            file_size,
            file_type
        )
        
        if not updated_ressource:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la mise à jour de la ressource.",
            )
        
        departments = await get_departments_for_ressource(ressource_id)
        updated_ressource["departments"] = departments
        
        return updated_ressource
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la mise à jour: {str(e)}",
        )


@router.delete("/{ressource_id}")
async def delete_ressource_endpoint(
    ressource_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Supprime une ressource.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent supprimer des ressources.",
        )
    
    try:
        ressource = await get_ressource_by_id(ressource_id)
        if not ressource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ressource introuvable.",
            )
        
        if ressource["organization_id"] != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez supprimer que les ressources de votre organisation.",
            )
        
        success = await delete_ressource(ressource_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la suppression de la ressource.",
            )
        
        return {"message": "Ressource supprimée avec succès."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression: {str(e)}",
        )


@router.post("/{ressource_id}/assign-departments")
async def assign_ressource_to_departments_endpoint(
    ressource_id: str,
    assignment: RessourceDepartmentAssignment,
    current_user: dict = Depends(get_current_user)
):
    """
    Affecte une ressource à plusieurs départements.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent affecter des ressources.",
        )
    
    try:
        ressource = await get_ressource_by_id(ressource_id)
        if not ressource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ressource introuvable.",
            )
        
        if ressource["organization_id"] != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez affecter que les ressources de votre organisation.",
            )
        
        success = await assign_ressource_to_departments(ressource_id, assignment.department_ids)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de l'affectation de la ressource.",
            )
        
        return {"message": "Ressource affectée aux départements avec succès."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'affectation: {str(e)}",
        )

