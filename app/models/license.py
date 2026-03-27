from datetime import datetime, date
from typing import List, Optional
import logging

from bson import ObjectId

from app.core.db import get_database
from app.models.organization import get_organization_by_id
from app.schemas.license import LicenseCreate

logger = logging.getLogger(__name__)

LICENSES_COLLECTION = "licenses"


def _license_doc_to_public(doc) -> dict:
    # Convertir datetime en date si nécessaire pour la réponse
    start_date = doc["start_date"]
    end_date = doc["end_date"]
    
    # Si c'est un datetime, extraire la date
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    
    return {
        "id": str(doc["_id"]),
        "organization_id": str(doc["organization_id"]),
        "plan": doc["plan"],
        "max_users": doc["max_users"],
        "start_date": start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date),
        "end_date": end_date.isoformat() if hasattr(end_date, 'isoformat') else str(end_date),
        "status": doc.get("status", "active"),
        "features": doc.get("features", []),
    }


async def create_license(lic_in: LicenseCreate) -> dict:
    db = get_database()

    # Vérifier que l'organisation existe
    org = await get_organization_by_id(lic_in.organization_id)
    if not org:
        raise ValueError("Organisation introuvable pour cet organization_id.")

    try:
        org_oid = ObjectId(lic_in.organization_id)
    except Exception:
        raise ValueError("organization_id invalide.")

    # Convert date objects to datetime for MongoDB compatibility
    start_datetime = datetime.combine(lic_in.start_date, datetime.min.time()) if isinstance(lic_in.start_date, date) else lic_in.start_date
    end_datetime = datetime.combine(lic_in.end_date, datetime.min.time()) if isinstance(lic_in.end_date, date) else lic_in.end_date
    
    doc = {
        "organization_id": org_oid,
        "plan": lic_in.plan,
        "max_users": lic_in.max_users,
        "start_date": start_datetime,
        "end_date": end_datetime,
        "status": lic_in.status,
        "features": lic_in.features,
        "created_at": datetime.utcnow(),
    }

    result = await db[LICENSES_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _license_doc_to_public(doc)


async def list_licenses_by_org(org_id: str) -> List[dict]:
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        org_oid = None

    q = {"organization_id": org_id}
    if org_oid is not None:
        q = {"$or": [{"organization_id": org_oid}, {"organization_id": org_id}]}

    cursor = db[LICENSES_COLLECTION].find(q)
    items = []
    async for doc in cursor:
        items.append(_license_doc_to_public(doc))
    return items






async def get_active_license_for_org(org_id: str) -> Optional[dict]:
    """
    Récupère une licence 'active' pour une organisation,
    en vérifiant aussi que la date actuelle est dans [start_date, end_date].
    """
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        org_oid = None

    # Convert date.today() to datetime for MongoDB compatibility
    today = datetime.combine(date.today(), datetime.min.time())

    q = {
        "status": "active",
        "start_date": {"$lte": today},
        "end_date": {"$gte": today},
    }
    if org_oid is not None:
        q["$or"] = [{"organization_id": org_oid}, {"organization_id": org_id}]
    else:
        q["organization_id"] = org_id

    doc = await db[LICENSES_COLLECTION].find_one(q)
    if not doc:
        return None
    return _license_doc_to_public(doc)


async def org_has_active_license(org_id: Optional[str]) -> bool:
    """
    Vérifie si une organisation a une licence active.
    
    Args:
        org_id: ID de l'organisation (None pour superadmin)
    
    Returns:
        True si licence active, False sinon.
        Retourne True si org_id est None (superadmin).
    """
    if not org_id:
        logger.debug("org_has_active_license: org_id=None (superadmin) → True")
        return True  # Superadmins ont toujours accès
    
    license_doc = await get_active_license_for_org(org_id)
    has_license = license_doc is not None
    
    if has_license:
        logger.debug(f"org_has_active_license: org_id={org_id} → True (licence active trouvée)")
    else:
        logger.debug(f"org_has_active_license: org_id={org_id} → False (pas de licence active)")
    
    return has_license


async def update_license(license_id: str, update_data: dict) -> dict:
    """
    Met à jour une licence.
    """
    db = get_database()
    try:
        lic_oid = ObjectId(license_id)
    except Exception:
        raise ValueError("license_id invalide.")
    
    # Vérifier que la licence existe
    existing = await db[LICENSES_COLLECTION].find_one({"_id": lic_oid})
    if not existing:
        raise ValueError("Licence introuvable.")
    
    # Préparer les données de mise à jour
    update_doc = {}
    
    if "organization_id" in update_data:
        org_oid = ObjectId(update_data["organization_id"])
        # Vérifier que l'organisation existe
        org = await get_organization_by_id(update_data["organization_id"])
        if not org:
            raise ValueError("Organisation introuvable.")
        update_doc["organization_id"] = org_oid
    
    if "plan" in update_data:
        update_doc["plan"] = update_data["plan"]
    if "max_users" in update_data:
        update_doc["max_users"] = update_data["max_users"]
    if "status" in update_data:
        update_doc["status"] = update_data["status"]
    if "features" in update_data:
        update_doc["features"] = update_data["features"]
    
    if "start_date" in update_data:
        start_date = update_data["start_date"]
        if isinstance(start_date, date):
            update_doc["start_date"] = datetime.combine(start_date, datetime.min.time())
        else:
            update_doc["start_date"] = start_date
    
    if "end_date" in update_data:
        end_date = update_data["end_date"]
        if isinstance(end_date, date):
            update_doc["end_date"] = datetime.combine(end_date, datetime.min.time())
        else:
            update_doc["end_date"] = end_date
    
    update_doc["updated_at"] = datetime.utcnow()
    
    await db[LICENSES_COLLECTION].update_one(
        {"_id": lic_oid},
        {"$set": update_doc}
    )
    
    # Récupérer la licence mise à jour
    updated = await db[LICENSES_COLLECTION].find_one({"_id": lic_oid})
    return _license_doc_to_public(updated)
