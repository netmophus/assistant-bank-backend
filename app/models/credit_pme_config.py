from datetime import datetime
from typing import Optional
from bson import ObjectId
from app.core.db import get_database
from app.schemas.credit_pme_config import CreditPMEFieldConfig

CREDIT_PME_CONFIG_COLLECTION = "credit_pme_config"


def _config_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "organization_id": str(doc["organization_id"]),
        "field_config": doc.get("field_config", {}),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else datetime.utcnow().isoformat(),
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else datetime.utcnow().isoformat(),
    }


async def get_credit_pme_config(organization_id: str) -> Optional[dict]:
    """Récupère la configuration des champs PME pour une organisation"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        return None
    
    doc = await db[CREDIT_PME_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    return _config_doc_to_public(doc) if doc else None


async def create_or_update_credit_pme_config(
    organization_id: str,
    field_config: CreditPMEFieldConfig
) -> dict:
    """Crée ou met à jour la configuration des champs PME"""
    db = get_database()
    try:
        org_oid = ObjectId(organization_id)
    except Exception:
        raise ValueError("ID organisation invalide")
    
    config_data = field_config.model_dump()
    
    # Vérifier si une config existe déjà
    existing = await db[CREDIT_PME_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    
    if existing:
        # Mettre à jour
        await db[CREDIT_PME_CONFIG_COLLECTION].update_one(
            {"organization_id": org_oid},
            {
                "$set": {
                    "field_config": config_data,
                    "updated_at": datetime.utcnow(),
                }
            }
        )
        doc = await db[CREDIT_PME_CONFIG_COLLECTION].find_one({"organization_id": org_oid})
    else:
        # Créer
        doc = {
            "organization_id": org_oid,
            "field_config": config_data,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db[CREDIT_PME_CONFIG_COLLECTION].insert_one(doc)
        doc["_id"] = result.inserted_id
    
    return _config_doc_to_public(doc)

