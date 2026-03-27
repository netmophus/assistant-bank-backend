"""
Modèles MongoDB pour la configuration des ratios bancaires
"""
from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from app.core.db import get_database
from app.schemas.pcb_ratios import RATIOS_DEFAUT_UEMOA

PCB_RATIOS_COLLECTION = "pcb_ratios_config"


def _ratio_doc_to_public(doc) -> dict:
    """Convertit un document ratio en dict public"""
    return {
        "id": str(doc["_id"]),
        "code": doc.get("code", ""),
        "libelle": doc.get("libelle", ""),
        "description": doc.get("description"),
        "formule": doc.get("formule", ""),
        "type_rapport": doc.get("type_rapport", ""),
        "categorie": doc.get("categorie", ""),
        "seuil_min": doc.get("seuil_min"),
        "seuil_max": doc.get("seuil_max"),
        "unite": doc.get("unite", "%"),
        "is_reglementaire": doc.get("is_reglementaire", True),
        "is_active": doc.get("is_active", True),
        "postes_requis": doc.get("postes_requis", []),
        "ordre_affichage": doc.get("ordre_affichage", 1),
        "organization_id": str(doc["organization_id"]) if doc.get("organization_id") else None,
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


async def init_default_ratios(organization_id: str) -> List[dict]:
    """
    Initialise les ratios par défaut pour une organisation
    """
    db = get_database()
    
    # Vérifier si des ratios existent déjà
    existing = await db[PCB_RATIOS_COLLECTION].find_one({
        "organization_id": ObjectId(organization_id)
    })
    
    if existing:
        # Retourner les ratios existants
        ratios = []
        async for doc in db[PCB_RATIOS_COLLECTION].find({
            "organization_id": ObjectId(organization_id)
        }).sort("ordre_affichage", 1):
            ratios.append(_ratio_doc_to_public(doc))
        return ratios
    
    # Créer les ratios par défaut
    ratios_crees = []
    for ratio_data in RATIOS_DEFAUT_UEMOA:
        doc = {
            **ratio_data,
            "organization_id": ObjectId(organization_id),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db[PCB_RATIOS_COLLECTION].insert_one(doc)
        new_doc = await db[PCB_RATIOS_COLLECTION].find_one({"_id": result.inserted_id})
        ratios_crees.append(_ratio_doc_to_public(new_doc))
    
    return ratios_crees


async def list_ratios_config(organization_id: str, filters: Optional[dict] = None) -> List[dict]:
    """Liste les ratios configurés pour une organisation"""
    db = get_database()
    query = {"organization_id": ObjectId(organization_id)}
    
    if filters:
        if filters.get("categorie"):
            query["categorie"] = filters["categorie"]
        if filters.get("type_rapport"):
            query["type_rapport"] = filters["type_rapport"]
        if filters.get("is_active") is not None:
            query["is_active"] = filters["is_active"]
        if filters.get("is_reglementaire") is not None:
            query["is_reglementaire"] = filters["is_reglementaire"]
    
    ratios = []
    async for doc in db[PCB_RATIOS_COLLECTION].find(query).sort("ordre_affichage", 1):
        ratios.append(_ratio_doc_to_public(doc))
    return ratios


async def get_ratio_config_by_code(code: str, organization_id: str) -> Optional[dict]:
    """Récupère un ratio par son code"""
    db = get_database()
    doc = await db[PCB_RATIOS_COLLECTION].find_one({
        "code": code,
        "organization_id": ObjectId(organization_id)
    })
    if doc:
        return _ratio_doc_to_public(doc)
    return None


async def create_ratio_config(ratio_data: dict, organization_id: str) -> dict:
    """Crée une configuration de ratio"""
    db = get_database()
    
    # Vérifier si le code existe déjà
    existing = await db[PCB_RATIOS_COLLECTION].find_one({
        "code": ratio_data["code"],
        "organization_id": ObjectId(organization_id)
    })
    
    if existing:
        raise ValueError(f"Un ratio avec le code '{ratio_data['code']}' existe déjà")
    
    doc = {
        **ratio_data,
        "organization_id": ObjectId(organization_id),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    result = await db[PCB_RATIOS_COLLECTION].insert_one(doc)
    new_doc = await db[PCB_RATIOS_COLLECTION].find_one({"_id": result.inserted_id})
    return _ratio_doc_to_public(new_doc)


async def update_ratio_config(ratio_id: str, update_data: dict, organization_id: str) -> dict:
    """Met à jour une configuration de ratio"""
    db = get_database()
    
    update_doc = {k: v for k, v in update_data.items() if v is not None}
    update_doc["updated_at"] = datetime.utcnow()
    
    await db[PCB_RATIOS_COLLECTION].update_one(
        {"_id": ObjectId(ratio_id), "organization_id": ObjectId(organization_id)},
        {"$set": update_doc}
    )
    
    updated = await db[PCB_RATIOS_COLLECTION].find_one({
        "_id": ObjectId(ratio_id),
        "organization_id": ObjectId(organization_id)
    })
    
    if not updated:
        raise ValueError("Ratio introuvable")
    
    return _ratio_doc_to_public(updated)


async def delete_ratio_config(ratio_id: str, organization_id: str) -> bool:
    """Supprime une configuration de ratio"""
    db = get_database()
    result = await db[PCB_RATIOS_COLLECTION].delete_one({
        "_id": ObjectId(ratio_id),
        "organization_id": ObjectId(organization_id)
    })
    return result.deleted_count > 0


async def toggle_ratio_active(ratio_id: str, organization_id: str, is_active: bool) -> dict:
    """Active ou désactive un ratio"""
    return await update_ratio_config(ratio_id, {"is_active": is_active}, organization_id)
