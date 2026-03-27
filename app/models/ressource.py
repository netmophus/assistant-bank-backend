from datetime import datetime
from typing import Optional, List
from bson import ObjectId
import os
import shutil
from pathlib import Path

from app.core.db import get_database
from app.models.organization import get_organization_by_id

RESSOURCES_COLLECTION = "ressources"
RESSOURCES_ASSIGNMENT_COLLECTION = "ressource_department_assignments"

# Dossier pour stocker les fichiers uploadés
UPLOAD_DIR = Path("uploads/ressources")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _ressource_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB en dictionnaire public"""
    return {
        "id": str(doc["_id"]),
        "titre": doc["titre"],
        "description": doc.get("description"),
        "filename": doc.get("filename"),
        "file_name": doc.get("filename"),  # Alias pour compatibilité
        "file_path": doc.get("file_path"),
        "file_size": doc.get("file_size"),
        "file_type": doc.get("file_type"),
        "organization_id": str(doc["organization_id"]),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") and isinstance(doc.get("created_at"), datetime) else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") and isinstance(doc.get("updated_at"), datetime) else None,
    }


async def create_ressource(ressource_data: dict, org_id: str, file_path: str, filename: str, file_size: int, file_type: str) -> dict:
    """
    Crée une ressource avec un fichier uploadé.
    """
    db = get_database()
    
    # Vérifier que l'organisation existe
    org = await get_organization_by_id(org_id)
    if not org:
        raise ValueError("Organisation introuvable.")
    
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        raise ValueError("organization_id invalide.")
    
    ressource_doc = {
        "titre": ressource_data.get("titre"),
        "description": ressource_data.get("description", ""),
        "filename": filename,
        "file_path": file_path,
        "file_size": file_size,
        "file_type": file_type,
        "organization_id": org_oid,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    result = await db[RESSOURCES_COLLECTION].insert_one(ressource_doc)
    ressource_doc["_id"] = result.inserted_id
    
    return _ressource_doc_to_public(ressource_doc)


async def get_ressource_by_id(ressource_id: str) -> Optional[dict]:
    """Récupère une ressource par son ID"""
    db = get_database()
    try:
        doc = await db[RESSOURCES_COLLECTION].find_one({"_id": ObjectId(ressource_id)})
        if doc:
            return _ressource_doc_to_public(doc)
        return None
    except Exception:
        return None


async def list_ressources_by_org(org_id: str) -> List[dict]:
    """Liste toutes les ressources d'une organisation"""
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []
    
    cursor = db[RESSOURCES_COLLECTION].find({"organization_id": org_oid}).sort("created_at", -1)
    ressources = []
    async for doc in cursor:
        ressources.append(_ressource_doc_to_public(doc))
    return ressources


async def update_ressource(ressource_id: str, ressource_data: dict, file_path: Optional[str] = None, filename: Optional[str] = None, file_size: Optional[int] = None, file_type: Optional[str] = None) -> Optional[dict]:
    """Met à jour une ressource"""
    db = get_database()
    try:
        ressource_oid = ObjectId(ressource_id)
    except Exception:
        return None
    
    update_data = {
        "updated_at": datetime.utcnow(),
    }
    
    if "titre" in ressource_data:
        update_data["titre"] = ressource_data["titre"]
    if "description" in ressource_data:
        update_data["description"] = ressource_data.get("description", "")
    
    # Si un nouveau fichier est uploadé
    if file_path and filename:
        # Supprimer l'ancien fichier si il existe
        old_doc = await db[RESSOURCES_COLLECTION].find_one({"_id": ressource_oid})
        if old_doc and old_doc.get("file_path"):
            old_file_path = Path(old_doc["file_path"])
            if old_file_path.exists():
                try:
                    old_file_path.unlink()
                except Exception:
                    pass
        
        update_data["file_path"] = file_path
        update_data["filename"] = filename
        if file_size:
            update_data["file_size"] = file_size
        if file_type:
            update_data["file_type"] = file_type
    
    result = await db[RESSOURCES_COLLECTION].update_one(
        {"_id": ressource_oid},
        {"$set": update_data}
    )
    
    if result.modified_count > 0:
        updated_doc = await db[RESSOURCES_COLLECTION].find_one({"_id": ressource_oid})
        if updated_doc:
            return _ressource_doc_to_public(updated_doc)
    
    return None


async def delete_ressource(ressource_id: str) -> bool:
    """Supprime une ressource et son fichier"""
    db = get_database()
    try:
        ressource_oid = ObjectId(ressource_id)
    except Exception:
        return False
    
    # Récupérer le document pour supprimer le fichier
    doc = await db[RESSOURCES_COLLECTION].find_one({"_id": ressource_oid})
    if doc and doc.get("file_path"):
        file_path = Path(doc["file_path"])
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass
    
    # Supprimer les affectations
    await db[RESSOURCES_ASSIGNMENT_COLLECTION].delete_many({"ressource_id": ressource_oid})
    
    # Supprimer la ressource
    result = await db[RESSOURCES_COLLECTION].delete_one({"_id": ressource_oid})
    return result.deleted_count > 0


async def assign_ressource_to_departments(ressource_id: str, department_ids: List[str], org_id: str) -> bool:
    """
    Affecte une ressource à plusieurs départements.
    Valide que la ressource et tous les départements appartiennent à la même organisation.
    """
    db = get_database()
    try:
        ressource_oid = ObjectId(ressource_id)
        org_oid = ObjectId(org_id)
        dept_oids = [ObjectId(dept_id) for dept_id in department_ids]
    except Exception:
        return False
    
    # Vérifier que la ressource existe et appartient à l'organisation
    ressource_doc = await db[RESSOURCES_COLLECTION].find_one({
        "_id": ressource_oid,
        "organization_id": org_oid
    })
    if not ressource_doc:
        raise ValueError("Ressource introuvable ou n'appartient pas à votre organisation.")
    
    # Vérifier que tous les départements appartiennent à la même organisation
    for dept_oid in dept_oids:
        dept_doc = await db["departments"].find_one({
            "_id": dept_oid,
            "organization_id": org_oid
        })
        if not dept_doc:
            raise ValueError(f"Département {str(dept_oid)} introuvable ou n'appartient pas à votre organisation.")
    
    # Supprimer les anciennes affectations
    await db[RESSOURCES_ASSIGNMENT_COLLECTION].delete_many({"ressource_id": ressource_oid})
    
    # Créer les nouvelles affectations
    assignments = [
        {
            "ressource_id": ressource_oid,
            "department_id": dept_oid,
            "created_at": datetime.utcnow(),
        }
        for dept_oid in dept_oids
    ]
    
    if assignments:
        await db[RESSOURCES_ASSIGNMENT_COLLECTION].insert_many(assignments)
    
    return True


async def get_departments_for_ressource(ressource_id: str) -> List[dict]:
    """Récupère les départements assignés à une ressource"""
    db = get_database()
    try:
        ressource_oid = ObjectId(ressource_id)
    except Exception:
        return []
    
    cursor = db[RESSOURCES_ASSIGNMENT_COLLECTION].find({"ressource_id": ressource_oid})
    assignments = []
    async for doc in cursor:
        # Récupérer les informations du département
        dept_doc = await db["departments"].find_one({"_id": doc["department_id"]})
        if dept_doc:
            assignments.append({
                "id": str(doc["department_id"]),
                "department_id": str(doc["department_id"]),
                "name": dept_doc.get("name", ""),
                "code": dept_doc.get("code", ""),
            })
        else:
            assignments.append({
                "id": str(doc["department_id"]),
                "department_id": str(doc["department_id"]),
                "name": "",
                "code": "",
            })
    return assignments


async def get_ressources_for_department(department_id: str) -> List[dict]:
    """Récupère les ressources assignées à un département"""
    db = get_database()
    try:
        dept_oid = ObjectId(department_id)
    except Exception:
        return []
    
    # Récupérer les IDs des ressources assignées
    cursor = db[RESSOURCES_ASSIGNMENT_COLLECTION].find({"department_id": dept_oid})
    ressource_ids = []
    async for doc in cursor:
        ressource_ids.append(doc["ressource_id"])
    
    if not ressource_ids:
        return []
    
    # Récupérer les ressources
    cursor = db[RESSOURCES_COLLECTION].find({"_id": {"$in": ressource_ids}}).sort("created_at", -1)
    ressources = []
    async for doc in cursor:
        ressource = _ressource_doc_to_public(doc)
        # Ajouter les départements assignés
        dept_assignments = await get_departments_for_ressource(str(doc["_id"]))
        ressource["departments"] = dept_assignments
        ressources.append(ressource)
    
    return ressources

