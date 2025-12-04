"""
Modèles pour gérer les interactions avec l'IA et leur historique.
"""
from datetime import datetime, date
from typing import List, Optional, Dict
from bson import ObjectId

from app.core.db import get_database

AI_INTERACTIONS_COLLECTION = "ai_interactions"
AI_PROMPTS_COLLECTION = "ai_prompts"
AI_LIMITS_COLLECTION = "ai_limits"


def _interaction_doc_to_public(doc) -> dict:
    """Convertit un document d'interaction en dict public."""
    return {
        "id": str(doc["_id"]),
        "user_id": str(doc["user_id"]),
        "organization_id": str(doc["organization_id"]),
        "type": doc["type"],
        "input_data": doc.get("input_data", {}),
        "output_data": doc.get("output_data", ""),
        "created_at": doc.get("created_at"),
    }


async def save_ai_interaction(
    user_id: str,
    organization_id: str,
    interaction_type: str,
    input_data: Dict,
    output_data: str,
) -> str:
    """Sauvegarde une interaction avec l'IA."""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id) if isinstance(organization_id, str) else organization_id
        user_oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
    except Exception:
        raise ValueError("IDs invalides")
    
    doc = {
        "user_id": user_oid,
        "organization_id": org_oid,
        "type": interaction_type,
        "input_data": input_data,
        "output_data": output_data,
        "created_at": datetime.utcnow(),
    }
    
    result = await db[AI_INTERACTIONS_COLLECTION].insert_one(doc)
    return str(result.inserted_id)


async def get_user_interactions(
    user_id: str,
    organization_id: Optional[str] = None,
    interaction_type: Optional[str] = None,
    limit: int = 50,
) -> List[dict]:
    """Récupère l'historique des interactions d'un utilisateur."""
    db = get_database()
    
    query = {}
    
    try:
        user_oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
        query["user_id"] = user_oid
    except Exception:
        return []
    
    if organization_id:
        try:
            org_oid = ObjectId(organization_id) if isinstance(organization_id, str) else organization_id
            query["organization_id"] = org_oid
        except Exception:
            pass
    
    if interaction_type:
        query["type"] = interaction_type
    
    cursor = (
        db[AI_INTERACTIONS_COLLECTION]
        .find(query)
        .sort("created_at", -1)
        .limit(limit)
    )
    
    interactions = []
    async for doc in cursor:
        interactions.append(_interaction_doc_to_public(doc))
    
    return interactions


async def get_org_interactions_count_today(organization_id: str) -> int:
    """Compte le nombre d'interactions IA d'une organisation aujourd'hui."""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id) if isinstance(organization_id, str) else organization_id
    except Exception:
        return 0
    
    today_start = datetime.combine(date.today(), datetime.min.time())
    
    count = await db[AI_INTERACTIONS_COLLECTION].count_documents({
        "organization_id": org_oid,
        "created_at": {"$gte": today_start},
    })
    
    return count


async def get_ai_prompts() -> dict:
    """Récupère les prompts système configurés."""
    db = get_database()
    
    doc = await db[AI_PROMPTS_COLLECTION].find_one({})
    if doc:
        return {
            "question_prompt": doc.get("question_prompt", ""),
            "letter_prompt": doc.get("letter_prompt", ""),
            "training_prompt": doc.get("training_prompt", ""),
        }
    
    # Retourner les valeurs par défaut si aucune config n'existe
    return {
        "question_prompt": (
            "Tu es un formateur senior en banque et finance. "
            "Tu expliques en français simple, de façon pédagogique, "
            "avec : (1) une définition claire, (2) un exemple concret, "
            "(3) si possible un lien avec la pratique en Afrique. "
            "N'utilis pas de LaTeX, écris les formules de façon simple."
        ),
        "letter_prompt": (
            "Tu es un rédacteur administratif dans une banque. "
            "Tu rédiges des lettres claires, structurées, en bon français, "
            "avec les formules de politesse adaptées. "
            "La lettre doit être prête à être imprimée sur papier à en-tête de la banque."
        ),
        "training_prompt": (
            "Tu es un expert en pédagogie bancaire. "
            "Tu conçois des modules de formation structurés, avec des objectifs clairs et un plan cohérent."
        ),
    }


async def update_ai_prompts(prompts: dict) -> dict:
    """Met à jour les prompts système."""
    db = get_database()
    
    # Utiliser upsert pour créer ou mettre à jour
    await db[AI_PROMPTS_COLLECTION].update_one(
        {},
        {
            "$set": {
                "question_prompt": prompts.get("question_prompt", ""),
                "letter_prompt": prompts.get("letter_prompt", ""),
                "training_prompt": prompts.get("training_prompt", ""),
                "updated_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )
    
    return await get_ai_prompts()


async def get_org_ai_limit(organization_id: str) -> int:
    """Récupère la limite d'utilisation IA d'une organisation."""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id) if isinstance(organization_id, str) else organization_id
    except Exception:
        return 0
    
    doc = await db[AI_LIMITS_COLLECTION].find_one({"organization_id": org_oid})
    if doc:
        return doc.get("daily_limit", 50)
    
    # Retourner la limite par défaut
    from app.core.config import settings
    return settings.AI_DAILY_LIMIT_PER_ORG


async def set_org_ai_limit(organization_id: str, daily_limit: int) -> dict:
    """Définit la limite d'utilisation IA d'une organisation."""
    db = get_database()
    
    try:
        org_oid = ObjectId(organization_id) if isinstance(organization_id, str) else organization_id
    except Exception:
        raise ValueError("ID d'organisation invalide")
    
    await db[AI_LIMITS_COLLECTION].update_one(
        {"organization_id": org_oid},
        {
            "$set": {
                "daily_limit": daily_limit,
                "updated_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )
    
    return {"organization_id": organization_id, "daily_limit": daily_limit}

