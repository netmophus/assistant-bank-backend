from datetime import datetime
from typing import List, Optional
from bson import ObjectId
import logging

from app.core.db import get_database

logger = logging.getLogger(__name__)

DOCUMENTS_COLLECTION = "documents"
ORG_DOCUMENT_CATEGORIES_COLLECTION = "org_document_categories"


def _document_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB en dict public."""
    org_id = doc.get("organization_id")
    return {
        "id": str(doc["_id"]),
        "filename": doc["filename"],
        "original_filename": doc.get("original_filename", doc["filename"]),
        "file_type": doc["file_type"],
        "file_size": doc["file_size"],
        "category": doc["category"],
        "subcategory": doc.get("subcategory"),
        "tags": doc.get("tags", []),
        "description": doc.get("description"),
        "upload_date": doc["upload_date"],
        "uploaded_by": str(doc["uploaded_by"]),
        "status": doc.get("status", "pending"),
        "total_chunks": doc.get("total_chunks", 0),
        "organization_id": str(org_id) if org_id else None,
        "scope": doc.get("scope", "ORG"),
        "titre": doc.get("titre"),
        "authority": doc.get("authority"),
        "reference": doc.get("reference"),
        "version": doc.get("version"),
        "effective_date": doc.get("effective_date"),
        "published_date": doc.get("published_date"),
    }


async def create_document(
    organization_id: Optional[str],
    uploaded_by: str,
    filename: str,
    original_filename: str,
    file_type: str,
    file_path: str,
    file_size: int,
    category: str,
    subcategory: Optional[str] = None,
    tags: List[str] = None,
    description: Optional[str] = None,
    scope: str = "ORG",
    titre: Optional[str] = None,
    authority: Optional[str] = None,
    reference: Optional[str] = None,
    version: Optional[str] = None,
    effective_date: Optional[datetime] = None,
) -> str:
    """Crée un document dans MongoDB."""
    db = get_database()
    doc = {
        "organization_id": ObjectId(organization_id) if organization_id else None,
        "uploaded_by": ObjectId(uploaded_by),
        "filename": filename,
        "original_filename": original_filename,
        "file_type": file_type,
        "file_path": file_path,
        "file_size": file_size,
        "category": category,
        "subcategory": subcategory,
        "tags": tags or [],
        "description": description,
        "upload_date": datetime.utcnow(),
        "status": "draft" if scope == "GLOBAL" else "pending",
        "total_chunks": 0,
        "extracted_text": "",
        "scope": scope,
    }
    
    # Champs spécifiques aux documents globaux
    if scope == "GLOBAL":
        doc["titre"] = titre
        doc["authority"] = authority
        doc["reference"] = reference
        doc["version"] = version
        doc["effective_date"] = effective_date
    
    result = await db[DOCUMENTS_COLLECTION].insert_one(doc)
    return str(result.inserted_id)


async def get_document_by_id(document_id: str, organization_id: Optional[str] = None) -> Optional[dict]:
    """Récupère un document par son ID."""
    db = get_database()
    try:
        oid = ObjectId(document_id)
    except Exception:
        return None
    
    query = {"_id": oid}
    if organization_id:
        query["organization_id"] = ObjectId(organization_id)
    
    doc = await db[DOCUMENTS_COLLECTION].find_one(query)
    return doc


async def get_global_document_by_id(document_id: str) -> Optional[dict]:
    """Récupère un document global par son ID."""
    db = get_database()
    try:
        oid = ObjectId(document_id)
    except Exception:
        return None
    doc = await db[DOCUMENTS_COLLECTION].find_one({
        "_id": oid,
        "scope": "GLOBAL"
    })
    return doc


async def list_global_documents(
    category: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[List[dict], int]:
    """Liste les documents globaux avec filtres."""
    db = get_database()
    query = {
        "scope": "GLOBAL"
    }

    if category:
        query["category"] = category
    if status:
        query["status"] = status

    total = await db[DOCUMENTS_COLLECTION].count_documents(query)
    cursor = db[DOCUMENTS_COLLECTION].find(query).sort("upload_date", -1).skip(skip).limit(limit)
    documents = await cursor.to_list(length=limit)
    return [_document_doc_to_public(doc) for doc in documents], total


async def list_org_document_categories(organization_id: str) -> List[dict]:
    db = get_database()
    cursor = db[ORG_DOCUMENT_CATEGORIES_COLLECTION].find(
        {"organization_id": ObjectId(organization_id)}
    ).sort("name", 1)
    docs = await cursor.to_list(length=None)
    return [{"name": d.get("name", "")} for d in docs if d.get("name")]


async def create_org_document_category(organization_id: str, name: str) -> dict:
    db = get_database()
    n = (name or "").strip()
    if not n:
        raise ValueError("Nom de catégorie manquant")

    existing = await db[ORG_DOCUMENT_CATEGORIES_COLLECTION].find_one(
        {"organization_id": ObjectId(organization_id), "name": n}
    )
    if existing:
        return {"name": existing.get("name", n)}

    doc = {
        "organization_id": ObjectId(organization_id),
        "name": n,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    await db[ORG_DOCUMENT_CATEGORIES_COLLECTION].insert_one(doc)
    return {"name": n}


async def rename_org_document_category(organization_id: str, old_name: str, new_name: str) -> dict:
    db = get_database()
    old = (old_name or "").strip()
    new = (new_name or "").strip()
    if not old or not new:
        raise ValueError("Nom de catégorie invalide")

    # Vérifier que l'ancienne catégorie existe
    existing = await db[ORG_DOCUMENT_CATEGORIES_COLLECTION].find_one(
        {"organization_id": ObjectId(organization_id), "name": old}
    )
    if not existing:
        raise ValueError("Catégorie introuvable")

    # Mettre à jour la catégorie
    await db[ORG_DOCUMENT_CATEGORIES_COLLECTION].update_one(
        {"organization_id": ObjectId(organization_id), "name": old},
        {"$set": {"name": new, "updated_at": datetime.utcnow()}},
    )
    # Mettre à jour tous les documents de cette catégorie
    await db[DOCUMENTS_COLLECTION].update_many(
        {"organization_id": ObjectId(organization_id), "category": old},
        {"$set": {"category": new}},
    )
    return {"name": new}


async def delete_org_document_category(organization_id: str, name: str) -> dict:
    db = get_database()
    n = (name or "").strip()
    if not n:
        raise ValueError("Nom de catégorie invalide")

    # Vérifier qu'aucun document n'utilise cette catégorie
    count = await db[DOCUMENTS_COLLECTION].count_documents(
        {"organization_id": ObjectId(organization_id), "category": n}
    )
    if count > 0:
        raise ValueError(f"Impossible de supprimer : {count} document(s) utilisent cette catégorie")

    result = await db[ORG_DOCUMENT_CATEGORIES_COLLECTION].delete_one(
        {"organization_id": ObjectId(organization_id), "name": n}
    )
    if result.deleted_count == 0:
        raise ValueError("Catégorie introuvable")
    return {"deleted": True, "name": n}


async def update_global_document_status(document_id: str, status: str, published_date: Optional[datetime] = None):
    """Met à jour le statut d'un document global."""
    import logging
    logger = logging.getLogger(__name__)
    
    db = get_database()
    update_data = {"status": status}
    if published_date:
        update_data["published_date"] = published_date
    
    logger.info(f"Mise à jour statut document {document_id} en {status}")
    
    # Mettre à jour le document parent
    result = await db[DOCUMENTS_COLLECTION].update_one(
        {"_id": ObjectId(document_id), "scope": "GLOBAL"},
        {"$set": update_data}
    )
    logger.info(f"Résultat mise à jour document: modified={result.modified_count}, matched={result.matched_count}")
    
    # Mettre à jour le status des chunks associés
    chunks_result = await db[DOCUMENT_CHUNKS_COLLECTION].update_many(
        {"document_id": ObjectId(document_id), "scope": "GLOBAL"},
        {"$set": {"status": status}}
    )
    logger.info(f"Résultat mise à jour chunks: modified={chunks_result.modified_count}, matched={chunks_result.matched_count}")


async def update_document_status(document_id: str, status: str, extracted_text: str = ""):
    """Met à jour le statut d'un document."""
    db = get_database()
    await db[DOCUMENTS_COLLECTION].update_one(
        {"_id": ObjectId(document_id)},
        {"$set": {"status": status, "extracted_text": extracted_text}}
    )


async def update_document_chunks_count(document_id: str, total_chunks: int):
    """Met à jour le nombre de chunks d'un document."""
    db = get_database()
    await db[DOCUMENTS_COLLECTION].update_one(
        {"_id": ObjectId(document_id)},
        {"$set": {"total_chunks": total_chunks}}
        # Note: Ne pas écraser le status ici, il sera mis à jour séparément
    )


async def delete_document_chunks(document_id: str):
    """Supprime tous les chunks d'un document."""
    db = get_database()
    result = await db[DOCUMENT_CHUNKS_COLLECTION].delete_many({
        "document_id": ObjectId(document_id)
    })
    return result.deleted_count


async def update_document_metadata(
    document_id: str,
    organization_id: str,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    tags: Optional[List[str]] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
):
    """Met à jour les métadonnées d'un document."""
    db = get_database()
    update_data = {}
    if category is not None:
        update_data["category"] = category
    if subcategory is not None:
        update_data["subcategory"] = subcategory
    if tags is not None:
        update_data["tags"] = tags
    if description is not None:
        update_data["description"] = description
    if status is not None:
        update_data["status"] = status

    if update_data:
        await db[DOCUMENTS_COLLECTION].update_one(
            {"_id": ObjectId(document_id), "organization_id": ObjectId(organization_id)},
            {"$set": update_data}
        )


async def list_documents(
    organization_id: str,
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[List[dict], int]:
    """Liste les documents avec filtres."""
    db = get_database()
    query = {"organization_id": ObjectId(organization_id)}

    if category:
        query["category"] = category
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"filename": {"$regex": search, "$options": "i"}},
            {"original_filename": {"$regex": search, "$options": "i"}},
            {"tags": {"$in": [search]}},
            {"extracted_text": {"$regex": search, "$options": "i"}},
        ]

    total = await db[DOCUMENTS_COLLECTION].count_documents(query)
    cursor = db[DOCUMENTS_COLLECTION].find(query).sort("upload_date", -1).skip(skip).limit(limit)
    documents = await cursor.to_list(length=limit)
    return [_document_doc_to_public(doc) for doc in documents], total


async def delete_document(document_id: str, organization_id: Optional[str] = None) -> bool:
    """Supprime un document et ses chunks."""
    db = get_database()
    try:
        doc_oid = ObjectId(document_id)
        # Supprimer les chunks
        await db[DOCUMENT_CHUNKS_COLLECTION].delete_many({
            "document_id": doc_oid
        })
        # Supprimer les affectations aux départements (si document ORG)
        try:
            await db["document_department_assignments"].delete_many({"document_id": doc_oid})
        except Exception:
            pass
        # Supprimer le document
        query = {"_id": doc_oid}
        if organization_id:
            query["organization_id"] = ObjectId(organization_id)
        result = await db[DOCUMENTS_COLLECTION].delete_one(query)
        return result.deleted_count > 0
    except Exception:
        return False




async def get_document_stats(organization_id: str) -> dict:
    """Récupère les statistiques des documents."""
    db = get_database()
    pipeline = [
        {"$match": {"organization_id": ObjectId(organization_id)}},
        {
            "$group": {
                "_id": None,
                "total_documents": {"$sum": 1},
                "total_size": {"$sum": "$file_size"},
                "by_category": {
                    "$push": "$category"
                },
                "by_status": {
                    "$push": "$status"
                }
            }
        }
    ]
    result = await db[DOCUMENTS_COLLECTION].aggregate(pipeline).to_list(length=1)
    
    if result:
        stats = result[0]
        # Compter par catégorie
        categories = {}
        for cat in stats.get("by_category", []):
            categories[cat] = categories.get(cat, 0) + 1
        
        # Compter par statut
        statuses = {}
        for st in stats.get("by_status", []):
            statuses[st] = statuses.get(st, 0) + 1
        
        # Compter les chunks
        total_chunks = await db[DOCUMENT_CHUNKS_COLLECTION].count_documents({
            "organization_id": ObjectId(organization_id)
        })
        
        return {
            "total_documents": stats.get("total_documents", 0),
            "total_chunks": total_chunks,
            "total_size": stats.get("total_size", 0),
            "by_category": categories,
            "by_status": statuses,
        }
    return {
        "total_documents": 0,
        "total_chunks": 0,
        "total_size": 0,
        "by_category": {},
        "by_status": {},
    }

