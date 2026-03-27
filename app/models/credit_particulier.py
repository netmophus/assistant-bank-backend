from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from app.core.db import get_database
from app.schemas.credit_particulier import (
    CreditParticulierFieldConfig,
    CreditParticulierRequest,
    CalculatedMetrics,
)

CREDIT_PARTICULIER_CONFIG_COLLECTION = "credit_particulier_config"
CREDIT_PARTICULIER_REQUESTS_COLLECTION = "credit_particulier_requests"


# ===================== Configuration des champs =====================

def _config_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "organization_id": str(doc["organization_id"]),
        "field_config": doc.get("field_config", {}),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


async def get_credit_particulier_config(organization_id: str) -> Optional[dict]:
    """Récupère la configuration des champs pour une organisation"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return None
    
    doc = await db[CREDIT_PARTICULIER_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    if not doc:
        return None
    return _config_doc_to_public(doc)


async def create_or_update_credit_particulier_config(
    organization_id: str,
    field_config: CreditParticulierFieldConfig
) -> dict:
    """Crée ou met à jour la configuration des champs"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        raise ValueError("ID d'organisation invalide")
    
    existing = await db[CREDIT_PARTICULIER_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    
    config_data = field_config.model_dump()
    
    if existing:
        await db[CREDIT_PARTICULIER_CONFIG_COLLECTION].update_one(
            {"organization_id": org_oid},
            {"$set": {"field_config": config_data, "updated_at": datetime.utcnow()}}
        )
        doc = await db[CREDIT_PARTICULIER_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    else:
        doc = {
            "organization_id": org_oid,
            "field_config": config_data,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db[CREDIT_PARTICULIER_CONFIG_COLLECTION].insert_one(doc)
        doc["_id"] = result.inserted_id
    
    return _config_doc_to_public(doc)


# ===================== Demandes de crédit =====================

def _request_doc_to_public(doc) -> dict:
    calculated_metrics = doc.get("calculated_metrics", {})
    
    # Ajouter des valeurs par défaut pour les anciennes analyses
    if "annualInterestRate" not in calculated_metrics:
        calculated_metrics["annualInterestRate"] = 5.0  # 5% par défaut
    if "totalInterestPaid" not in calculated_metrics:
        # Calculer approximativement: mensualité × durée - capital
        monthly_payment = calculated_metrics.get("newLoanMonthlyPayment", 0)
        duration = doc.get("request_data", {}).get("loanDurationMonths", 0)
        capital = doc.get("request_data", {}).get("loanAmount", 0)
        calculated_metrics["totalInterestPaid"] = (monthly_payment * duration) - capital
    
    # Corriger les ai_decision vides ou invalides
    ai_decision = doc.get("ai_decision", "CONDITIONNEL")
    if not ai_decision or ai_decision not in ["APPROUVE", "REFUSE", "CONDITIONNEL"]:
        ai_decision = "CONDITIONNEL"
    
    return {
        "id": str(doc["_id"]),
        "user_id": str(doc["user_id"]),
        "organization_id": str(doc["organization_id"]),
        "request_data": doc.get("request_data", {}),
        "calculated_metrics": calculated_metrics,
        "ai_analysis": doc.get("ai_analysis", ""),
        "ai_decision": ai_decision,
        "ai_recommendations": doc.get("ai_recommendations"),
        "created_at": doc.get("created_at"),
    }


async def create_credit_particulier_request(
    user_id: str,
    organization_id: str,
    request_data: CreditParticulierRequest,
    calculated_metrics: CalculatedMetrics,
    ai_analysis: str,
    ai_decision: str,
    ai_recommendations: Optional[str] = None,
) -> dict:
    """Crée une demande de crédit particulier avec analyse"""
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
    
    result = await db[CREDIT_PARTICULIER_REQUESTS_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _request_doc_to_public(doc)


async def get_user_credit_requests(
    user_id: str,
    limit: int = 50
) -> List[dict]:
    """Récupère les demandes de crédit d'un utilisateur"""
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        return []
    
    cursor = db[CREDIT_PARTICULIER_REQUESTS_COLLECTION].find(
        {"user_id": user_oid}
    ).sort("created_at", -1).limit(limit)
    
    requests = []
    async for doc in cursor:
        requests.append(_request_doc_to_public(doc))
    
    return requests


async def get_org_credit_requests(
    organization_id: str,
    limit: int = 100
) -> List[dict]:
    """Récupère les demandes de crédit d'une organisation"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return []
    
    cursor = db[CREDIT_PARTICULIER_REQUESTS_COLLECTION].find(
        {"organization_id": org_oid}
    ).sort("created_at", -1).limit(limit)
    
    requests = []
    async for doc in cursor:
        requests.append(_request_doc_to_public(doc))
    
    return requests

