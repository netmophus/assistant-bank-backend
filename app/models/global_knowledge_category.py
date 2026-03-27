from datetime import datetime
from typing import List, Optional
from bson import ObjectId

from app.core.db import get_database

GLOBAL_KNOWLEDGE_CATEGORIES_COLLECTION = "global_knowledge_categories"


def _category_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB en dict public."""
    created_at = doc.get("created_at")
    updated_at = doc.get("updated_at")
    
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "slug": doc["slug"],
        "description": doc.get("description"),
        "is_active": doc.get("is_active", True),
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


async def create_category(name: str, slug: str, description: Optional[str] = None) -> dict:
    """Crée une nouvelle catégorie."""
    db = get_database()
    
    # Vérifier que le slug est unique
    existing = await db[GLOBAL_KNOWLEDGE_CATEGORIES_COLLECTION].find_one({"slug": slug})
    if existing:
        raise ValueError(f"Une catégorie avec le slug '{slug}' existe déjà")
    
    doc = {
        "name": name,
        "slug": slug,
        "description": description or "",
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    result = await db[GLOBAL_KNOWLEDGE_CATEGORIES_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _category_doc_to_public(doc)


async def get_category_by_id(category_id: str) -> Optional[dict]:
    """Récupère une catégorie par son ID."""
    db = get_database()
    try:
        doc = await db[GLOBAL_KNOWLEDGE_CATEGORIES_COLLECTION].find_one({"_id": ObjectId(category_id)})
        if doc:
            return _category_doc_to_public(doc)
        return None
    except Exception:
        return None


async def get_category_by_slug(slug: str) -> Optional[dict]:
    """Récupère une catégorie par son slug."""
    db = get_database()
    doc = await db[GLOBAL_KNOWLEDGE_CATEGORIES_COLLECTION].find_one({"slug": slug})
    if doc:
        return _category_doc_to_public(doc)
    return None


async def list_categories(include_inactive: bool = False) -> List[dict]:
    """Liste toutes les catégories."""
    db = get_database()
    query = {}
    if not include_inactive:
        query["is_active"] = True
    
    cursor = db[GLOBAL_KNOWLEDGE_CATEGORIES_COLLECTION].find(query).sort("name", 1)
    docs = await cursor.to_list(length=None)  # Récupérer tous les documents
    categories = [_category_doc_to_public(doc) for doc in docs]
    return categories


async def update_category(
    category_id: str,
    name: Optional[str] = None,
    slug: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Optional[dict]:
    """Met à jour une catégorie."""
    db = get_database()
    
    update_data = {"updated_at": datetime.utcnow()}
    
    if name is not None:
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
    if is_active is not None:
        update_data["is_active"] = is_active
    if slug is not None:
        # Vérifier que le slug est unique (sauf pour cette catégorie)
        existing = await db[GLOBAL_KNOWLEDGE_CATEGORIES_COLLECTION].find_one({
            "slug": slug,
            "_id": {"$ne": ObjectId(category_id)}
        })
        if existing:
            raise ValueError(f"Une catégorie avec le slug '{slug}' existe déjà")
        update_data["slug"] = slug
    
    result = await db[GLOBAL_KNOWLEDGE_CATEGORIES_COLLECTION].update_one(
        {"_id": ObjectId(category_id)},
        {"$set": update_data}
    )
    
    if result.modified_count > 0:
        return await get_category_by_id(category_id)
    return None


async def delete_category(category_id: str) -> bool:
    """Supprime une catégorie."""
    db = get_database()
    
    # Récupérer le slug de la catégorie pour vérifier
    category = await get_category_by_id(category_id)
    if category:
        # Vérifier si des documents utilisent cette catégorie
        from app.models.documents import DOCUMENTS_COLLECTION
        docs_count = await db[DOCUMENTS_COLLECTION].count_documents({
            "scope": "GLOBAL",
            "category": category["slug"]
        })
        if docs_count > 0:
            raise ValueError(f"Impossible de supprimer cette catégorie : {docs_count} document(s) l'utilise(nt)")
    
    result = await db[GLOBAL_KNOWLEDGE_CATEGORIES_COLLECTION].delete_one({"_id": ObjectId(category_id)})
    return result.deleted_count > 0


async def toggle_category_active(category_id: str) -> Optional[dict]:
    """Active ou désactive une catégorie."""
    category = await get_category_by_id(category_id)
    if not category:
        return None
    
    new_status = not category["is_active"]
    return await update_category(category_id, is_active=new_status)

