from datetime import datetime, date
from typing import Optional, List
from bson import ObjectId

from app.core.db import get_database
from app.models.user import get_user_by_id
from app.models.department import get_department_by_id, get_service_by_id

import logging

QUESTIONS_COLLECTION = "questions"
QUOTA_LIMIT = 60  # quota par défaut (60 questions/mois)


async def get_quota_limit_for_user(user_id: str) -> int:
    """Retourne le quota mensuel applicable à l'utilisateur.
    Si son organisation a un quota personnalisé (question_quota), on l'utilise.
    Sinon, on retourne le quota par défaut (60).
    """
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
        user = await db["users"].find_one({"_id": user_oid})
        if user and user.get("organization_id"):
            org = await db["organizations"].find_one({"_id": ObjectId(str(user["organization_id"]))})
            if org and org.get("question_quota") is not None:
                return int(org["question_quota"])
    except Exception:
        pass
    return QUOTA_LIMIT


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
    quota = await get_quota_limit_for_user(user_id)
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        return {
            "user_id": user_id,
            "current_month": datetime.now().strftime("%Y-%m"),
            "questions_asked": 0,
            "quota_limit": quota,
            "remaining_quota": quota,
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

    remaining = max(0, quota - count)
    is_exceeded = count >= quota

    return {
        "user_id": user_id,
        "current_month": now.strftime("%Y-%m"),
        "questions_asked": count,
        "quota_limit": quota,
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
    
    # Générer la réponse via Perplexity (recherche web temps réel + expertise UEMOA)
    try:
        from app.services.perplexity_service import answer_with_perplexity, _is_configured

        # Récupérer les sites configurés pour l'organisation
        sites: list[str] = []
        if organization_id:
            try:
                from app.models.organization import get_web_search_config
                web_cfg = await get_web_search_config(organization_id)
                if web_cfg.get("web_search_enabled") and web_cfg.get("web_search_sites"):
                    sites = web_cfg["web_search_sites"]
            except Exception:
                pass

        if _is_configured():
            result = await answer_with_perplexity(question_text, sites=sites or None)
            answer = result.get("answer") or ""
        else:
            # Fallback OpenAI si Perplexity non configuré
            from app.services.rag_new_service import answer_question
            answer, _s, _src, _d = await answer_question(
                question=question_text,
                organization_id=organization_id,
                category=None,
                allow_global=False,
                skip_rag=True,
            )

        if not answer:
            raise ValueError("Réponse vide")

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error("Erreur génération réponse IA: %s", e)
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

