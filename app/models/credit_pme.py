from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from app.core.db import get_database
from app.schemas.credit_pme import CreditPMERequest, PMECalculatedMetrics

CREDIT_PME_REQUESTS_COLLECTION = "credit_pme_requests"


# ===================== Demandes de crédit PME =====================

def _request_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "user_id": str(doc["user_id"]),
        "organization_id": str(doc["organization_id"]),
        "request_data": doc.get("request_data", {}),
        "calculated_metrics": doc.get("calculated_metrics", {}),
        "ai_analysis": doc.get("ai_analysis", ""),
        "ai_decision": doc.get("ai_decision", "CONDITIONNEL"),
        "ai_recommendations": doc.get("ai_recommendations"),
        "created_at": doc.get("created_at"),
    }


async def create_credit_pme_request(
    user_id: str,
    organization_id: str,
    request_data: CreditPMERequest,
    calculated_metrics: PMECalculatedMetrics,
    ai_analysis: str,
    ai_decision: str,
    ai_recommendations: Optional[str] = None,
) -> dict:
    """Crée une demande de crédit PME avec analyse"""
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
        org_oid = ObjectId(organization_id)
    except Exception:
        raise ValueError("IDs invalides")
    
    doc = {
        "user_id": user_oid,
        "organization_id": org_oid,
        "request_data": request_data.model_dump(),
        "calculated_metrics": calculated_metrics.model_dump(),
        "ai_analysis": ai_analysis,
        "ai_decision": ai_decision,
        "ai_recommendations": ai_recommendations,
        "created_at": datetime.utcnow(),
    }
    
    result = await db[CREDIT_PME_REQUESTS_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _request_doc_to_public(doc)


async def get_user_credit_pme_requests(
    user_id: str,
    limit: int = 50
) -> List[dict]:
    """Récupère les demandes de crédit PME d'un utilisateur"""
    import logging
    logging.info(f"🔍 Recherche demandes PME pour user_id: {user_id}")
    
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        logging.error(f"❌ user_id invalide: {user_id}")
        return []
    
    # Vérifier si la collection existe
    collections = await db.list_collection_names()
    logging.info(f"📂 Collections disponibles: {collections}")
    
    if CREDIT_PME_REQUESTS_COLLECTION not in collections:
        logging.warning(f"⚠️ Collection {CREDIT_PME_REQUESTS_COLLECTION} n'existe pas")
        return []
    
    cursor = db[CREDIT_PME_REQUESTS_COLLECTION].find(
        {"user_id": user_oid}
    ).sort("created_at", -1).limit(limit)
    
    requests = []
    async for doc in cursor:
        requests.append(_request_doc_to_public(doc))
    
    logging.info(f"✅ Trouvé {len(requests)} demandes PME")
    return requests


async def get_org_credit_pme_requests(
    organization_id: str,
    limit: int = 100
) -> List[dict]:
    """Récupère les demandes de crédit PME d'une organisation"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    cursor = db[CREDIT_PME_REQUESTS_COLLECTION].find(
        {"organization_id": org_oid}
    ).sort("created_at", -1).limit(limit)
    
    requests = []
    async for doc in cursor:
        requests.append(_request_doc_to_public(doc))
    
    return requests

