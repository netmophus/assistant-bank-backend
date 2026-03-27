"""
Modèles MongoDB pour les ratios de gestion (lignes personnalisées)
"""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from app.core.db import get_database


RATIO_GESTION_LINE_COLLECTION = "ratio_gestion_line"


def _doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "code": doc.get("code", ""),
        "libelle": doc.get("libelle", ""),
        "description": doc.get("description"),
        "formule": doc.get("formule", ""),
        "unite": doc.get("unite", "%"),
        "is_active": doc.get("is_active", True),
        "ordre_affichage": doc.get("ordre_affichage", 1),
        "organization_id": str(doc["organization_id"]) if doc.get("organization_id") else None,
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


async def list_ratio_gestion_lines(organization_id: str, filters: Optional[dict] = None) -> List[dict]:
    db = get_database()
    query = {"organization_id": ObjectId(organization_id)}

    if filters:
        if filters.get("is_active") is not None:
            query["is_active"] = filters["is_active"]

    items = []
    async for doc in db[RATIO_GESTION_LINE_COLLECTION].find(query).sort("ordre_affichage", 1):
        items.append(_doc_to_public(doc))
    return items


async def get_ratio_gestion_line_by_code(code: str, organization_id: str) -> Optional[dict]:
    db = get_database()
    doc = await db[RATIO_GESTION_LINE_COLLECTION].find_one(
        {"code": code, "organization_id": ObjectId(organization_id)}
    )
    return _doc_to_public(doc) if doc else None


async def create_ratio_gestion_line(data: dict, organization_id: str) -> dict:
    db = get_database()

    existing = await db[RATIO_GESTION_LINE_COLLECTION].find_one(
        {"code": data["code"], "organization_id": ObjectId(organization_id)}
    )
    if existing:
        raise ValueError(f"Un ratio de gestion avec le code '{data['code']}' existe déjà")

    now = datetime.utcnow()
    doc = {
        **data,
        "organization_id": ObjectId(organization_id),
        "created_at": now,
        "updated_at": now,
    }

    result = await db[RATIO_GESTION_LINE_COLLECTION].insert_one(doc)
    new_doc = await db[RATIO_GESTION_LINE_COLLECTION].find_one({"_id": result.inserted_id})
    return _doc_to_public(new_doc)


async def update_ratio_gestion_line(ratio_id: str, update_data: dict, organization_id: str) -> dict:
    db = get_database()

    update_doc = {k: v for k, v in update_data.items() if v is not None}
    update_doc["updated_at"] = datetime.utcnow()

    await db[RATIO_GESTION_LINE_COLLECTION].update_one(
        {"_id": ObjectId(ratio_id), "organization_id": ObjectId(organization_id)},
        {"$set": update_doc},
    )

    updated = await db[RATIO_GESTION_LINE_COLLECTION].find_one(
        {"_id": ObjectId(ratio_id), "organization_id": ObjectId(organization_id)}
    )
    if not updated:
        raise ValueError("Ratio de gestion introuvable")

    return _doc_to_public(updated)


async def delete_ratio_gestion_line(ratio_id: str, organization_id: str) -> bool:
    db = get_database()
    result = await db[RATIO_GESTION_LINE_COLLECTION].delete_one(
        {"_id": ObjectId(ratio_id), "organization_id": ObjectId(organization_id)}
    )
    return result.deleted_count > 0


async def toggle_ratio_gestion_line_active(ratio_id: str, organization_id: str, is_active: bool) -> dict:
    return await update_ratio_gestion_line(ratio_id, {"is_active": is_active}, organization_id)
