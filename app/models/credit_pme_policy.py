"""
Modèles MongoDB pour la politique de crédit PME et les applications PME.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.core.db import get_database
from app.schemas.credit_pme_policy import PMEPolicyConfig, PMEApplicationInput, PMEDecisionResult


# ── Policy CRUD ────────────────────────────────────────────────────────────────

async def get_pme_policy(organization_id: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    doc = await db["credit_pme_policy"].find_one({"organization_id": organization_id})
    if doc:
        doc["id"] = str(doc["_id"])
        doc.pop("_id", None)
    return doc


async def save_pme_policy(organization_id: str, config: PMEPolicyConfig) -> Dict[str, Any]:
    db = get_database()
    data = config.model_dump()
    data["organization_id"] = organization_id
    data["updated_at"] = datetime.utcnow()

    existing = await db["credit_pme_policy"].find_one({"organization_id": organization_id})
    if existing:
        await db["credit_pme_policy"].update_one({"organization_id": organization_id}, {"$set": data})
        doc = await db["credit_pme_policy"].find_one({"organization_id": organization_id})
    else:
        data["created_at"] = datetime.utcnow()
        result = await db["credit_pme_policy"].insert_one(data)
        doc = await db["credit_pme_policy"].find_one({"_id": result.inserted_id})

    doc["id"] = str(doc["_id"])
    doc.pop("_id", None)
    return doc


# ── Application CRUD ───────────────────────────────────────────────────────────

async def save_pme_application(
    user_id: str,
    organization_id: str,
    application: PMEApplicationInput,
    result: PMEDecisionResult,
) -> Dict[str, Any]:
    db = get_database()
    doc = {
        "user_id": user_id,
        "organization_id": organization_id,
        "application": application.model_dump(),
        "result": result.model_dump(),
        "created_at": datetime.utcnow(),
    }
    res = await db["credit_pme_applications"].insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    return doc


async def get_user_pme_applications(user_id: str) -> List[Dict[str, Any]]:
    db = get_database()
    cursor = db["credit_pme_applications"].find(
        {"user_id": user_id},
        sort=[("created_at", -1)]
    )
    records = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        doc.pop("_id", None)
        records.append(doc)
    return records


async def get_org_pme_applications(organization_id: str) -> List[Dict[str, Any]]:
    db = get_database()
    cursor = db["credit_pme_applications"].find(
        {"organization_id": organization_id},
        sort=[("created_at", -1)]
    )
    records = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        doc.pop("_id", None)
        records.append(doc)
    return records
