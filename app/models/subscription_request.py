"""
Demandes d'abonnement soumises via le formulaire public de www.miznas.co.

Workflow : pending -> contacted -> paid -> activated (ou rejected).
Traite manuellement par le superadmin.
"""
from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from app.core.db import get_database

SUBSCRIPTION_REQUESTS_COLLECTION = "subscription_requests"

_indexes_created = False


async def ensure_subscription_request_indexes() -> None:
    """Idempotent — appele au startup de l'app."""
    global _indexes_created
    if _indexes_created:
        return
    db = get_database()
    try:
        # Recherche admin par email
        await db[SUBSCRIPTION_REQUESTS_COLLECTION].create_index([("email", 1)])
        # Filtrage liste admin (status + date desc)
        await db[SUBSCRIPTION_REQUESTS_COLLECTION].create_index(
            [("status", 1), ("created_at", -1)]
        )
        # Stats par offre
        await db[SUBSCRIPTION_REQUESTS_COLLECTION].create_index(
            [("plan_requested", 1)]
        )
        _indexes_created = True
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"[subscription_requests] Erreur creation index: {e}"
        )


def _doc_to_public(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "first_name": doc.get("first_name", ""),
        "last_name": doc.get("last_name", ""),
        "email": doc.get("email", ""),
        "phone_country_code": doc.get("phone_country_code", ""),
        "phone_number": doc.get("phone_number", ""),
        "country": doc.get("country", ""),
        "city": doc.get("city", ""),
        "professional_status": doc.get("professional_status", ""),
        "institution": doc.get("institution"),
        "plan_requested": doc.get("plan_requested", ""),
        "status": doc.get("status", "pending"),
        "admin_notes": doc.get("admin_notes"),
        "created_at": doc.get("created_at"),
        "contacted_at": doc.get("contacted_at"),
        "activated_at": doc.get("activated_at"),
    }


async def create_subscription_request(data: dict) -> dict:
    """Cree une nouvelle demande avec status='pending'."""
    db = get_database()
    await ensure_subscription_request_indexes()

    # Normalisation email (evite les doublons "X@y" vs "x@y")
    email = (data.get("email") or "").strip().lower()

    doc = {
        "first_name": (data.get("first_name") or "").strip(),
        "last_name": (data.get("last_name") or "").strip(),
        "email": email,
        "phone_country_code": (data.get("phone_country_code") or "").strip(),
        "phone_number": (data.get("phone_number") or "").strip(),
        "country": data.get("country"),
        "city": (data.get("city") or "").strip(),
        "professional_status": data.get("professional_status"),
        "institution": (data.get("institution") or "").strip() or None,
        "plan_requested": data.get("plan_requested"),
        "status": "pending",
        "admin_notes": None,
        "created_at": datetime.utcnow(),
        "contacted_at": None,
        "activated_at": None,
        "linked_user_id": None,
        "linked_subscription_id": None,
    }
    result = await db[SUBSCRIPTION_REQUESTS_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_public(doc)


async def get_subscription_request_by_id(req_id: str) -> Optional[dict]:
    db = get_database()
    try:
        oid = ObjectId(req_id)
    except Exception:
        return None
    doc = await db[SUBSCRIPTION_REQUESTS_COLLECTION].find_one({"_id": oid})
    return _doc_to_public(doc) if doc else None


async def list_subscription_requests(
    status: Optional[str] = None,
    plan: Optional[str] = None,
) -> List[dict]:
    """Liste les demandes, trie par date decroissante."""
    db = get_database()
    query: dict = {}
    if status:
        query["status"] = status
    if plan:
        query["plan_requested"] = plan

    cursor = db[SUBSCRIPTION_REQUESTS_COLLECTION].find(query).sort("created_at", -1)
    return [_doc_to_public(doc) async for doc in cursor]


async def update_subscription_request_status(
    req_id: str,
    new_status: str,
    admin_notes: Optional[str] = None,
) -> dict:
    """Met a jour le statut d'une demande + horodatages automatiques."""
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
    elif new_status == "activated":
        update["activated_at"] = now

    result = await db[SUBSCRIPTION_REQUESTS_COLLECTION].update_one(
        {"_id": oid},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise ValueError("Demande introuvable.")

    updated = await db[SUBSCRIPTION_REQUESTS_COLLECTION].find_one({"_id": oid})
    return _doc_to_public(updated)
