from datetime import datetime, date
from typing import Optional, List, Dict
from bson import ObjectId
import logging

from app.core.db import get_database

logger = logging.getLogger(__name__)

CONVERSATIONS_COLLECTION = "conversations"


def _conversation_doc_to_public(doc) -> dict:
    """Convertit un document MongoDB conversation en dict public."""
    return {
        "id": str(doc["_id"]),
        "user_id": str(doc["user_id"]),
        "organization_id": str(doc["organization_id"]),
        "title": doc.get("title", "Conversation"),
        "status": doc.get("status", "open"),
        "message_count": doc.get("message_count", 0),
        "created_at": doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else str(doc["created_at"]),
        "updated_at": doc["updated_at"].isoformat() if isinstance(doc["updated_at"], datetime) else str(doc["updated_at"]),
        "closed_at": doc.get("closed_at").isoformat() if doc.get("closed_at") and isinstance(doc.get("closed_at"), datetime) else None,
        "archived_at": doc.get("archived_at").isoformat() if doc.get("archived_at") and isinstance(doc.get("archived_at"), datetime) else None,
        "month_key": doc.get("month_key"),
        "last_message": doc.get("last_message"),
    }


def _conversation_message_to_dict(msg) -> dict:
    """Convertit un message de conversation en dict."""
    return {
        "role": msg.get("role"),
        "content": msg.get("content"),
        "timestamp": msg.get("timestamp").isoformat() if isinstance(msg.get("timestamp"), datetime) else str(msg.get("timestamp", "")),
        "question_id": str(msg["question_id"]) if msg.get("question_id") else None,
    }


async def create_conversation(
    user_id: str,
    organization_id: str,
    first_question: str,
    first_answer: str,
    question_id: str,
    context: Optional[str] = None,
) -> dict:
    """
    Crée une nouvelle conversation avec le premier message.
    
    Args:
        user_id: ID de l'utilisateur
        organization_id: ID de l'organisation
        first_question: Première question
        first_answer: Première réponse
        question_id: ID de la question créée dans la collection questions
        context: Contexte optionnel
    
    Returns:
        Conversation créée
    """
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
        org_oid = ObjectId(organization_id)
        question_oid = ObjectId(question_id)
    except Exception as e:
        raise ValueError(f"ID invalide: {e}")
    
    now = datetime.utcnow()
    month_key = now.strftime("%Y-%m")
    
    # Titre = première question (tronquée à 100 caractères)
    title = first_question[:100] + ("..." if len(first_question) > 100 else "")
    
    doc = {
        "user_id": user_oid,
        "organization_id": org_oid,
        "title": title,
        "status": "open",
        "messages": [
            {
                "role": "user",
                "content": first_question,
                "timestamp": now,
                "question_id": question_oid,
            },
            {
                "role": "assistant",
                "content": first_answer,
                "timestamp": now,
                "question_id": None,
            },
        ],
        "message_count": 2,
        "month_key": month_key,
        "created_at": now,
        "updated_at": now,
        "last_message": first_answer[:200] + ("..." if len(first_answer) > 200 else ""),
    }
    
    result = await db[CONVERSATIONS_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    
    return _conversation_doc_to_public(doc)


async def add_message_to_conversation(
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
    question_id: Optional[str] = None,
) -> dict:
    """
    Ajoute un message à une conversation existante.
    
    Args:
        conversation_id: ID de la conversation
        user_id: ID de l'utilisateur (vérification propriétaire)
        role: "user" ou "assistant"
        content: Contenu du message
        question_id: ID de la question (si role="user")
    
    Returns:
        Conversation mise à jour
    """
    db = get_database()
    try:
        conv_oid = ObjectId(conversation_id)
        user_oid = ObjectId(user_id)
    except Exception as e:
        raise ValueError(f"ID invalide: {e}")
    
    # Vérifier que la conversation existe et appartient à l'utilisateur
    conversation = await db[CONVERSATIONS_COLLECTION].find_one({
        "_id": conv_oid,
        "user_id": user_oid,
    })
    
    if not conversation:
        raise ValueError("Conversation introuvable ou vous n'êtes pas autorisé à y accéder")
    
    # Vérifier que la conversation n'est pas fermée ou archivée
    status = conversation.get("status", "open")
    if status in ["closed", "archived"]:
        raise ValueError(f"Impossible d'ajouter un message à une conversation {status}")
    
    now = datetime.utcnow()
    
    # Préparer le nouveau message
    new_message = {
        "role": role,
        "content": content,
        "timestamp": now,
        "question_id": ObjectId(question_id) if question_id else None,
    }
    
    # Mettre à jour la conversation
    update_doc = {
        "$push": {"messages": new_message},
        "$inc": {"message_count": 1},
        "$set": {
            "updated_at": now,
            "last_message": content[:200] + ("..." if len(content) > 200 else ""),
        },
    }
    
    await db[CONVERSATIONS_COLLECTION].update_one(
        {"_id": conv_oid},
        update_doc
    )
    
    # Récupérer la conversation mise à jour
    updated = await db[CONVERSATIONS_COLLECTION].find_one({"_id": conv_oid})
    return _conversation_doc_to_public(updated)


async def get_conversation_by_id(conversation_id: str, user_id: str) -> Optional[dict]:
    """
    Récupère une conversation par son ID (vérifie le propriétaire).
    
    Returns:
        Conversation avec tous les messages, ou None si non trouvée
    """
    db = get_database()
    try:
        conv_oid = ObjectId(conversation_id)
        user_oid = ObjectId(user_id)
    except Exception:
        return None
    
    doc = await db[CONVERSATIONS_COLLECTION].find_one({
        "_id": conv_oid,
        "user_id": user_oid,
    })
    
    if not doc:
        return None
    
    # Convertir les messages
    messages = [_conversation_message_to_dict(msg) for msg in doc.get("messages", [])]
    
    result = _conversation_doc_to_public(doc)
    result["messages"] = messages
    
    return result


async def list_user_conversations(user_id: str, limit: int = 20) -> List[dict]:
    """
    Liste les conversations d'un utilisateur (triées par updated_at DESC).
    
    Returns:
        Liste des conversations (sans les messages détaillés)
    """
    db = get_database()
    try:
        user_oid = ObjectId(user_id)
    except Exception:
        return []
    
    cursor = db[CONVERSATIONS_COLLECTION].find(
        {"user_id": user_oid}
    ).sort("updated_at", -1).limit(limit)
    
    conversations = []
    async for doc in cursor:
        conversations.append(_conversation_doc_to_public(doc))
    
    return conversations


async def get_conversation_history(
    conversation_id: str,
    user_id: str,
    max_pairs: int = 10,
) -> List[dict]:
    """
    Récupère l'historique d'une conversation (limité pour l'IA).
    
    Args:
        conversation_id: ID de la conversation
        user_id: ID de l'utilisateur (vérification)
        max_pairs: Nombre maximum de paires Q/R à retourner (défaut: 10)
    
    Returns:
        Liste des messages (les N dernières paires Q/R)
    """
    db = get_database()
    try:
        conv_oid = ObjectId(conversation_id)
        user_oid = ObjectId(user_id)
    except Exception:
        return []
    
    conversation = await db[CONVERSATIONS_COLLECTION].find_one({
        "_id": conv_oid,
        "user_id": user_oid,
    })
    
    if not conversation:
        return []
    
    messages = conversation.get("messages", [])
    
    # Prendre les N dernières paires Q/R (2 messages par paire)
    # On prend les max_pairs * 2 derniers messages
    max_messages = max_pairs * 2
    recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages
    
    # Convertir en dict
    return [_conversation_message_to_dict(msg) for msg in recent_messages]


async def close_conversation(conversation_id: str, user_id: str) -> dict:
    """
    Ferme une conversation (status="closed", read-only).
    
    Returns:
        Conversation fermée
    """
    db = get_database()
    try:
        conv_oid = ObjectId(conversation_id)
        user_oid = ObjectId(user_id)
    except Exception as e:
        raise ValueError(f"ID invalide: {e}")
    
    now = datetime.utcnow()
    
    result = await db[CONVERSATIONS_COLLECTION].update_one(
        {
            "_id": conv_oid,
            "user_id": user_oid,
            "status": {"$ne": "archived"},  # Ne pas fermer une conversation archivée
        },
        {
            "$set": {
                "status": "closed",
                "closed_at": now,
                "updated_at": now,
            }
        }
    )
    
    if result.matched_count == 0:
        raise ValueError("Conversation introuvable, déjà fermée/archivée, ou vous n'êtes pas autorisé")
    
    # Récupérer la conversation mise à jour
    updated = await db[CONVERSATIONS_COLLECTION].find_one({"_id": conv_oid})
    return _conversation_doc_to_public(updated)


async def delete_conversation(conversation_id: str, user_id: str) -> bool:
    """
    Supprime une conversation.
    
    Returns:
        True si supprimée, False sinon
    """
    db = get_database()
    try:
        conv_oid = ObjectId(conversation_id)
        user_oid = ObjectId(user_id)
    except Exception:
        return False
    
    result = await db[CONVERSATIONS_COLLECTION].delete_one({
        "_id": conv_oid,
        "user_id": user_oid,
    })
    
    return result.deleted_count > 0


async def archive_conversations_for_month(month_key: str) -> int:
    """
    Archive toutes les conversations ouvertes/fermées d'un mois donné.
    Utile pour un job mensuel d'archivage.
    
    Args:
        month_key: Format "YYYY-MM"
    
    Returns:
        Nombre de conversations archivées
    """
    db = get_database()
    now = datetime.utcnow()
    
    result = await db[CONVERSATIONS_COLLECTION].update_many(
        {
            "month_key": month_key,
            "status": {"$in": ["open", "closed"]},
        },
        {
            "$set": {
                "status": "archived",
                "archived_at": now,
                "updated_at": now,
            }
        }
    )
    
    return result.modified_count

