from datetime import datetime
from typing import Optional, List
from bson import ObjectId

from app.core.db import get_database
from app.models.formation import get_formation_by_id

QCM_RESPONSES_COLLECTION = "qcm_responses"


def _qcm_response_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB en dictionnaire public."""
    return {
        "id": str(doc["_id"]),
        "user_id": str(doc["user_id"]),
        "formation_id": str(doc["formation_id"]),
        "module_id": str(doc["module_id"]),
        "question_index": doc["question_index"],
        "selected_answer": doc["selected_answer"],
        "is_correct": doc["is_correct"],
        "correct_answer": doc["correct_answer"],
        "explication": doc.get("explication"),
        "answered_at": doc["answered_at"].isoformat() if isinstance(doc["answered_at"], datetime) else str(doc["answered_at"]),
        "question_text": doc.get("question_text"),
        "options": doc.get("options"),
    }


async def submit_qcm_response(
    user_id: str,
    formation_id: str,
    module_id: str,
    question_index: int,
    selected_answer: int
) -> dict:
    """
    Soumet une réponse QCM et retourne le feedback.
    
    Args:
        user_id: ID de l'utilisateur
        formation_id: ID de la formation
        module_id: ID du module
        question_index: Index de la question dans le module
        selected_answer: Index de la réponse sélectionnée (0-3)
    
    Returns:
        Dictionnaire avec la réponse et le feedback
    """
    db = get_database()
    
    try:
        user_oid = ObjectId(user_id)
        formation_oid = ObjectId(formation_id)
        module_oid = ObjectId(module_id)
    except Exception:
        raise ValueError("IDs invalides.")
    
    # Récupérer la formation pour obtenir les questions QCM
    formation = await get_formation_by_id(formation_id)
    if not formation:
        raise ValueError("Formation introuvable.")
    
    # Trouver le module
    module = None
    for m in formation.get("modules", []):
        if str(m["id"]) == module_id:
            module = m
            break
    
    if not module:
        raise ValueError("Module introuvable.")
    
    # Récupérer les questions QCM du module
    questions_qcm = module.get("questions_qcm", [])
    if question_index >= len(questions_qcm):
        raise ValueError(f"Index de question invalide. Le module contient {len(questions_qcm)} questions.")
    
    question = questions_qcm[question_index]
    correct_answer = question.get("correct_answer", 0)
    is_correct = selected_answer == correct_answer
    explication = question.get("explication", "")
    
    # Vérifier si l'utilisateur a déjà répondu à cette question
    existing_response = await db[QCM_RESPONSES_COLLECTION].find_one({
        "user_id": user_oid,
        "formation_id": formation_oid,
        "module_id": module_oid,
        "question_index": question_index
    })
    
    # Créer ou mettre à jour la réponse
    response_doc = {
        "user_id": user_oid,
        "formation_id": formation_oid,
        "module_id": module_oid,
        "question_index": question_index,
        "selected_answer": selected_answer,
        "is_correct": is_correct,
        "correct_answer": correct_answer,
        "explication": explication,
        "question_text": question.get("question", ""),
        "options": question.get("options", []),
        "answered_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    if existing_response:
        # Mettre à jour la réponse existante
        await db[QCM_RESPONSES_COLLECTION].update_one(
            {"_id": existing_response["_id"]},
            {"$set": response_doc}
        )
        response_doc["_id"] = existing_response["_id"]
    else:
        # Créer une nouvelle réponse
        result = await db[QCM_RESPONSES_COLLECTION].insert_one(response_doc)
        response_doc["_id"] = result.inserted_id
    
    return _qcm_response_doc_to_public(response_doc)


async def get_user_qcm_responses(
    user_id: str,
    formation_id: str,
    module_id: str
) -> List[dict]:
    """
    Récupère toutes les réponses QCM d'un utilisateur pour un module donné.
    
    Args:
        user_id: ID de l'utilisateur
        formation_id: ID de la formation
        module_id: ID du module
    
    Returns:
        Liste des réponses QCM
    """
    db = get_database()
    
    try:
        user_oid = ObjectId(user_id)
        formation_oid = ObjectId(formation_id)
        module_oid = ObjectId(module_id)
    except Exception:
        return []
    
    cursor = db[QCM_RESPONSES_COLLECTION].find({
        "user_id": user_oid,
        "formation_id": formation_oid,
        "module_id": module_oid
    }).sort("question_index", 1)
    
    responses = []
    async for doc in cursor:
        responses.append(_qcm_response_doc_to_public(doc))
    
    return responses


async def get_user_qcm_stats(
    user_id: str,
    formation_id: str,
    module_id: str
) -> dict:
    """
    Récupère les statistiques QCM d'un utilisateur pour un module donné.
    
    Args:
        user_id: ID de l'utilisateur
        formation_id: ID de la formation
        module_id: ID du module
    
    Returns:
        Dictionnaire avec les statistiques
    """
    # Récupérer la formation pour obtenir le nombre total de questions
    formation = await get_formation_by_id(formation_id)
    if not formation:
        return {
            "module_id": module_id,
            "total_questions": 0,
            "answered_questions": 0,
            "correct_answers": 0,
            "score_percentage": 0.0,
            "responses": []
        }
    
    # Trouver le module
    module = None
    for m in formation.get("modules", []):
        if str(m["id"]) == module_id:
            module = m
            break
    
    if not module:
        return {
            "module_id": module_id,
            "total_questions": 0,
            "answered_questions": 0,
            "correct_answers": 0,
            "score_percentage": 0.0,
            "responses": []
        }
    
    questions_qcm = module.get("questions_qcm", [])
    total_questions = len(questions_qcm)
    
    # Récupérer les réponses de l'utilisateur
    responses = await get_user_qcm_responses(user_id, formation_id, module_id)
    answered_questions = len(responses)
    correct_answers = sum(1 for r in responses if r["is_correct"])
    
    score_percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0.0
    
    return {
        "module_id": module_id,
        "total_questions": total_questions,
        "answered_questions": answered_questions,
        "correct_answers": correct_answers,
        "score_percentage": round(score_percentage, 2),
        "responses": responses
    }

