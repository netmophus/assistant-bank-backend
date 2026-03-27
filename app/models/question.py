from datetime import datetime, date
from typing import Optional, List
from bson import ObjectId

from app.core.db import get_database
from app.models.user import get_user_by_id
from app.models.department import get_department_by_id, get_service_by_id

import logging

QUESTIONS_COLLECTION = "questions"
QUOTA_LIMIT = 60  # 60 questions par mois


def _question_doc_to_public(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "user_id": str(doc["user_id"]),
        "question": doc["question"],
        "answer": doc.get("answer"),
        "status": doc.get("status", "pending"),
        "created_at": doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else str(doc["created_at"]),
        "answered_at": doc.get("answered_at").isoformat() if doc.get("answered_at") and isinstance(doc["answered_at"], datetime) else (str(doc["answered_at"]) if doc.get("answered_at") else None),
    }


async def get_user_quota_stats(user_id: str) -> dict:
    """
    Récupère les statistiques de quota pour un utilisateur pour le mois en cours.
    """
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        return {
            "user_id": user_id,
            "current_month": datetime.now().strftime("%Y-%m"),
            "questions_asked": 0,
            "quota_limit": QUOTA_LIMIT,
            "remaining_quota": QUOTA_LIMIT,
            "is_quota_exceeded": False,
        }
    
    # Calculer le début et la fin du mois en cours
    now = datetime.utcnow()
    start_of_month = datetime(now.year, now.month, 1)
    end_of_month = datetime(now.year, now.month + 1, 1) if now.month < 12 else datetime(now.year + 1, 1, 1)
    
    # Compter les questions du mois en cours
    count = await db[QUESTIONS_COLLECTION].count_documents({
        "user_id": user_oid,
        "created_at": {
            "$gte": start_of_month,
            "$lt": end_of_month
        }
    })
    
    remaining = max(0, QUOTA_LIMIT - count)
    is_exceeded = count >= QUOTA_LIMIT
    
    return {
        "user_id": user_id,
        "current_month": now.strftime("%Y-%m"),
        "questions_asked": count,
        "quota_limit": QUOTA_LIMIT,
        "remaining_quota": remaining,
        "is_quota_exceeded": is_exceeded,
    }


async def check_user_quota(user_id: str) -> tuple[bool, dict]:
    """
    Vérifie si l'utilisateur peut poser une question (quota non dépassé).
    Retourne (can_ask, stats).
    """
    stats = await get_user_quota_stats(user_id)
    can_ask = not stats["is_quota_exceeded"]
    return can_ask, stats


async def create_question_without_answer(user_id: str, question_text: str, context: Optional[str] = None) -> dict:
    """
    Crée une question pour un utilisateur SANS générer de réponse.
    Utile pour les conversations où la réponse sera générée avec historique.
    Vérifie d'abord le quota.
    """
    # Vérifier le quota
    can_ask, stats = await check_user_quota(user_id)
    if not can_ask:
        raise ValueError(
            f"Quota mensuel dépassé. Vous avez utilisé {stats['questions_asked']}/{stats['quota_limit']} questions ce mois-ci."
        )
    
    # Récupérer les informations de l'utilisateur
    user = await get_user_by_id(user_id)
    if not user:
        raise ValueError("Utilisateur introuvable.")
    
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        raise ValueError("user_id invalide.")
    
    # Récupérer les noms du département et service si présents
    department_name = None
    service_name = None
    
    if user.get("department_id"):
        dept = await get_department_by_id(str(user["department_id"]))
        if dept:
            department_name = dept.get("name")
    
    if user.get("service_id"):
        service = await get_service_by_id(str(user["service_id"]))
        if service:
            service_name = service.get("name")
    
    doc = {
        "user_id": user_oid,
        "user_email": user.get("email"),
        "user_name": user.get("full_name"),
        "department_id": user.get("department_id"),
        "department_name": department_name,
        "service_id": user.get("service_id"),
        "service_name": service_name,
        "question": question_text,
        "context": context,
        "answer": None,
        "status": "pending",
        "created_at": datetime.utcnow(),
    }
    
    result = await db[QUESTIONS_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    
    return _question_doc_to_public(doc)


async def create_question(user_id: str, question_text: str, context: Optional[str] = None) -> dict:
    """
    Crée une question pour un utilisateur.
    Vérifie d'abord le quota.
    """
    # Vérifier le quota
    can_ask, stats = await check_user_quota(user_id)
    if not can_ask:
        raise ValueError(
            f"Quota mensuel dépassé. Vous avez utilisé {stats['questions_asked']}/{stats['quota_limit']} questions ce mois-ci."
        )
    
    # Récupérer les informations de l'utilisateur
    user = await get_user_by_id(user_id)
    if not user:
        raise ValueError("Utilisateur introuvable.")
    
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        raise ValueError("user_id invalide.")
    
    # Récupérer l'ID de l'organisation pour la recherche dans la base de connaissances
    organization_id = str(user.get("organization_id")) if user.get("organization_id") else None
    
    # Récupérer les noms du département et service si présents
    department_name = None
    service_name = None
    
    if user.get("department_id"):
        dept = await get_department_by_id(str(user["department_id"]))
        if dept:
            department_name = dept.get("name")
    
    if user.get("service_id"):
        service = await get_service_by_id(str(user["service_id"]))
        if service:
            service_name = service.get("name")
    
    doc = {
        "user_id": user_oid,
        "user_email": user.get("email"),
        "user_name": user.get("full_name"),
        "department_id": user.get("department_id"),
        "department_name": department_name,
        "service_id": user.get("service_id"),
        "service_name": service_name,
        "question": question_text,
        "context": context,
        "answer": None,
        "status": "pending",
        "created_at": datetime.utcnow(),
    }
    
    result = await db[QUESTIONS_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    
    # Générer la réponse via RAG New (GLOBAL -> LOCAL -> IA générale)
    try:
        allow_global = False
        if organization_id:
            from app.models.license import org_has_active_license

            allow_global = await org_has_active_license(organization_id)

        from app.services.rag_new_service import answer_question

        answer, _strategy, _sources, _debug = await answer_question(
            question=question_text,
            organization_id=organization_id,
            category=None,
            allow_global=allow_global,
        )
    except Exception as e:
        # En cas d'erreur, utiliser une réponse par défaut
        logger = logging.getLogger(__name__)
        msg = str(e)
        if "SearchNotEnabled" in msg or "31082" in msg or "requires additional configuration" in msg:
            logger.warning(f"Erreur lors de la génération de la réponse IA: {e}")
        else:
            logger.error(f"Erreur lors de la génération de la réponse IA: {e}")
        answer = "Désolé, une erreur est survenue lors de la génération de la réponse. Veuillez réessayer plus tard."
    
    # Mettre à jour avec la réponse
    await db[QUESTIONS_COLLECTION].update_one(
        {"_id": doc["_id"]},
        {"$set": {
            "answer": answer,
            "status": "answered",
            "answered_at": datetime.utcnow(),
        }}
    )
    
    doc["answer"] = answer
    doc["status"] = "answered"
    doc["answered_at"] = datetime.utcnow()
    
    return _question_doc_to_public(doc)


async def list_user_questions(user_id: str, limit: int = 50) -> List[dict]:
    """
    Liste les questions d'un utilisateur.
    """
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        return []
    
    cursor = db[QUESTIONS_COLLECTION].find(
        {"user_id": user_oid}
    ).sort("created_at", -1).limit(limit)
    
    questions = []
    async for doc in cursor:
        questions.append(_question_doc_to_public(doc))
    return questions


async def list_org_questions(org_id: str, limit: int = 100) -> List[dict]:
    """
    Liste toutes les questions d'une organisation (pour l'admin d'organisation).
    """
    db = get_database()
    try:
        org_oid = ObjectId(org_id)
    except Exception:
        return []
    
    # Récupérer tous les utilisateurs de l'organisation
    from app.models.user import USERS_COLLECTION
    users_cursor = db[USERS_COLLECTION].find({"organization_id": org_oid})
    user_ids = []
    async for user_doc in users_cursor:
        user_ids.append(user_doc["_id"])
    
    if not user_ids:
        return []
    
    cursor = db[QUESTIONS_COLLECTION].find(
        {"user_id": {"$in": user_ids}}
    ).sort("created_at", -1).limit(limit)
    
    questions = []
    async for doc in cursor:
        questions.append(_question_doc_to_public(doc))
    return questions

