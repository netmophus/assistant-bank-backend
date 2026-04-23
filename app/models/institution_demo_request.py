"""
Demandes de demonstration B2B soumises via le formulaire public de
www.miznas.co/tarifs (section "Solutions pour institutions").

Distinct des subscription_requests (B2C individuel) car :
- Pipeline de vente different (cycle long, devis sur-mesure)
- Champs differents (institution_name, type, modules, effectif)
- Statuts differents (pending -> contacted -> meeting_scheduled ->
  proposal_sent -> won/lost)
- Reserve au superadmin
"""
from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from app.core.db import get_database

INSTITUTION_DEMO_COLLECTION = "institution_demo_requests"

_indexes_created = False


async def ensure_institution_demo_indexes() -> None:
    """Idempotent — appele au startup."""
    global _indexes_created
    if _indexes_created:
        return
    db = get_database()
    try:
        await db[INSTITUTION_DEMO_COLLECTION].create_index([("email", 1)])
        await db[INSTITUTION_DEMO_COLLECTION].create_index(
            [("status", 1), ("created_at", -1)]
        )
        await db[INSTITUTION_DEMO_COLLECTION].create_index([("institution_type", 1)])
        _indexes_created = True
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"[institution_demo_requests] Erreur creation index: {e}"
        )


def _doc_to_public(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "first_name": doc.get("first_name", ""),
        "last_name": doc.get("last_name", ""),
        "function": doc.get("function", ""),
        "email": doc.get("email", ""),
        "phone_country_code": doc.get("phone_country_code", ""),
        "phone_number": doc.get("phone_number", ""),
        "country": doc.get("country", ""),
        "institution_name": doc.get("institution_name", ""),
        "institution_type": doc.get("institution_type", ""),
        "modules_interest": doc.get("modules_interest", []),
        "estimated_users": doc.get("estimated_users", ""),
        "message": doc.get("message"),
        "status": doc.get("status", "pending"),
        "admin_notes": doc.get("admin_notes"),
        "created_at": doc.get("created_at"),
        "contacted_at": doc.get("contacted_at"),
        "meeting_scheduled_at": doc.get("meeting_scheduled_at"),
        "proposal_sent_at": doc.get("proposal_sent_at"),
        "closed_at": doc.get("closed_at"),
    }


async def create_institution_demo_request(data: dict) -> dict:
    """Cree une nouvelle demande institution avec status='pending'."""
    db = get_database()
    await ensure_institution_demo_indexes()

    email = (data.get("email") or "").strip().lower()

    doc = {
        "first_name": (data.get("first_name") or "").strip(),
        "last_name": (data.get("last_name") or "").strip(),
        "function": (data.get("function") or "").strip(),
        "email": email,
        "phone_country_code": (data.get("phone_country_code") or "").strip(),
        "phone_number": (data.get("phone_number") or "").strip(),
        "country": data.get("country"),
        "institution_name": (data.get("institution_name") or "").strip(),
        "institution_type": data.get("institution_type"),
        "modules_interest": data.get("modules_interest") or [],
        "estimated_users": data.get("estimated_users"),
        "message": (data.get("message") or "").strip() or None,
        "status": "pending",
        "admin_notes": None,
        "created_at": datetime.utcnow(),
        "contacted_at": None,
        "meeting_scheduled_at": None,
        "proposal_sent_at": None,
        "closed_at": None,
    }
    result = await db[INSTITUTION_DEMO_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_public(doc)


async def get_institution_demo_request_by_id(req_id: str) -> Optional[dict]:
    db = get_database()
    try:
        oid = ObjectId(req_id)
    except Exception:
        return None
    doc = await db[INSTITUTION_DEMO_COLLECTION].find_one({"_id": oid})
    return _doc_to_public(doc) if doc else None


async def list_institution_demo_requests(
    status: Optional[str] = None,
    institution_type: Optional[str] = None,
) -> List[dict]:
    """Liste les demandes triees par date decroissante."""
    db = get_database()
    query: dict = {}
    if status:
        query["status"] = status
    if institution_type:
        query["institution_type"] = institution_type

    cursor = db[INSTITUTION_DEMO_COLLECTION].find(query).sort("created_at", -1)
    return [_doc_to_public(doc) async for doc in cursor]


async def update_institution_demo_status(
    req_id: str,
    new_status: str,
    admin_notes: Optional[str] = None,
) -> dict:
    """Change le statut + notes. Horodate automatiquement les transitions."""
    db = get_database()
    try:
        oid = ObjectId(req_id)
    except Exception:
        raise ValueError("req_id invalide.")

    update: dict = {"status": new_status}
    if admin_notes is not None:
        update["admin_notes"] = admin_notes

    now = datetime.utcnow()
    if new_status == "contacted":
        update["contacted_at"] = now
    elif new_status == "meeting_scheduled":
        update["meeting_scheduled_at"] = now
    elif new_status == "proposal_sent":
        update["proposal_sent_at"] = now
    elif new_status in ("won", "lost"):
        update["closed_at"] = now

    result = await db[INSTITUTION_DEMO_COLLECTION].update_one(
        {"_id": oid},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise ValueError("Demande introuvable.")

    updated = await db[INSTITUTION_DEMO_COLLECTION].find_one({"_id": oid})
    return _doc_to_public(updated)
