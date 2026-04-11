from datetime import datetime
from typing import Optional, List

from bson import ObjectId

from app.core.db import get_database
from app.schemas.organization import OrganizationCreate

ORGANIZATIONS_COLLECTION = "organizations"


def _org_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "code": doc["code"],
        "country": doc.get("country"),
        "status": doc.get("status", "active"),
    }


async def get_web_search_config(org_id: str) -> dict:
    db = get_database()
    try:
        oid = ObjectId(org_id)
    except Exception:
        raise ValueError("organization_id invalide.")
    org = await db[ORGANIZATIONS_COLLECTION].find_one({"_id": oid})
    if not org:
        raise ValueError("Organisation introuvable.")
    return {
        "web_search_enabled": org.get("web_search_enabled", False),
        "web_search_sites": org.get("web_search_sites", []),
    }


async def update_web_search_config(org_id: str, enabled: Optional[bool], sites: Optional[List[str]]) -> dict:
    db = get_database()
    try:
        oid = ObjectId(org_id)
    except Exception:
        raise ValueError("organization_id invalide.")
    org = await db[ORGANIZATIONS_COLLECTION].find_one({"_id": oid})
    if not org:
        raise ValueError("Organisation introuvable.")

    update_doc: dict = {"updated_at": datetime.utcnow()}
    if enabled is not None:
        update_doc["web_search_enabled"] = enabled
    if sites is not None:
        # Nettoyer les URLs : strip whitespace, retirer les entrées vides
        update_doc["web_search_sites"] = [s.strip() for s in sites if s.strip()]

    await db[ORGANIZATIONS_COLLECTION].update_one({"_id": oid}, {"$set": update_doc})

    updated = await db[ORGANIZATIONS_COLLECTION].find_one({"_id": oid})
    return {
        "web_search_enabled": updated.get("web_search_enabled", False),
        "web_search_sites": updated.get("web_search_sites", []),
    }


async def get_organization_by_id(org_id: str) -> Optional[dict]:
    db = get_database()
    try:
        oid = ObjectId(org_id)
    except Exception:
        return None
    org = await db[ORGANIZATIONS_COLLECTION].find_one({"_id": oid})
    return org


async def get_organization_by_code(code: str) -> Optional[dict]:
    db = get_database()
    org = await db[ORGANIZATIONS_COLLECTION].find_one({"code": code})
    return org


async def create_organization(org_in: OrganizationCreate) -> dict:
    db = get_database()

    existing = await get_organization_by_code(org_in.code)
    if existing:
        raise ValueError("Une organisation avec ce code existe déjà.")

    doc = {
        "name": org_in.name,
        "code": org_in.code,
        "country": org_in.country,
        "status": "active",
        "created_at": datetime.utcnow(),
    }

    result = await db[ORGANIZATIONS_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _org_doc_to_public(doc)


async def list_organizations() -> List[dict]:
    db = get_database()
    cursor = db[ORGANIZATIONS_COLLECTION].find({})
    orgs = []
    async for doc in cursor:
        if "name" not in doc or "code" not in doc:
            continue
        orgs.append(_org_doc_to_public(doc))
    return orgs


async def update_organization(org_id: str, update_data: dict) -> dict:
    """
    Met à jour une organisation.
    """
    db = get_database()
    try:
        oid = ObjectId(org_id)
    except Exception:
        raise ValueError("organization_id invalide.")
    
    # Vérifier que l'organisation existe
    existing = await db[ORGANIZATIONS_COLLECTION].find_one({"_id": oid})
    if not existing:
        raise ValueError("Organisation introuvable.")
    
    # Si le code change, vérifier qu'il n'existe pas déjà
    if "code" in update_data and update_data["code"] != existing.get("code"):
        existing_code = await get_organization_by_code(update_data["code"])
        if existing_code and str(existing_code["_id"]) != org_id:
            raise ValueError("Une organisation avec ce code existe déjà.")
    
    # Préparer les données de mise à jour
    update_doc = {}
    if "name" in update_data:
        update_doc["name"] = update_data["name"]
    if "code" in update_data:
        update_doc["code"] = update_data["code"]
    if "country" in update_data:
        update_doc["country"] = update_data["country"]
    if "status" in update_data:
        update_doc["status"] = update_data["status"]
    
    update_doc["updated_at"] = datetime.utcnow()
    
    await db[ORGANIZATIONS_COLLECTION].update_one(
        {"_id": oid},
        {"$set": update_doc}
    )
    
    # Récupérer l'organisation mise à jour
    updated = await db[ORGANIZATIONS_COLLECTION].find_one({"_id": oid})
    return _org_doc_to_public(updated)