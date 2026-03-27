from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.core.deps import get_current_user
from app.models.conversation import (
    create_conversation,
    add_message_to_conversation,
    get_conversation_by_id,
    list_user_conversations,
    get_conversation_history,
    close_conversation,
    delete_conversation,
)
from app.models.question import (
    check_user_quota,
    create_question_without_answer,
)
from app.models.user import get_user_by_id
from app.models.department import get_department_by_id, get_service_by_id
from app.services.ai_service import generate_question_answer
from app.schemas.conversation import (
    ConversationAskRequest,
    ConversationAskResponse,
    ConversationPublic,
    ConversationDetail,
    ConversationCloseResponse,
    ConversationDeleteResponse,
    ConversationMessage,
)

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
)


@router.post("/ask", response_model=ConversationAskResponse)
async def ask_conversation_question(
    request: ConversationAskRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Pose une question dans une conversation.
    Si conversation_id est absent, crée une nouvelle conversation.
    Si présent, ajoute la question à la conversation existante.
    """
    user_id = str(current_user.get("id"))
    organization_id = str(current_user.get("organization_id")) if current_user.get("organization_id") else None
    
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utilisateur non associé à une organisation",
        )
    
    # Vérifier le quota avant de créer la question
    can_ask, stats = await check_user_quota(user_id)
    if not can_ask:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Quota mensuel dépassé. Vous avez utilisé {stats['questions_asked']}/{stats['quota_limit']} questions ce mois-ci.",
        )
    
    # Récupérer les informations de l'utilisateur
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur introuvable",
        )
    
    # Récupérer les noms du département et service
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
    
    # Récupérer l'historique si conversation_id fourni
    conversation_history = None
    conversation_id = request.conversation_id
    
    if conversation_id:
        # Vérifier que la conversation existe et appartient à l'utilisateur
        conversation = await get_conversation_by_id(conversation_id, user_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation introuvable ou vous n'êtes pas autorisé à y accéder",
            )
        
        # Vérifier que la conversation n'est pas fermée ou archivée
        if conversation.get("status") in ["closed", "archived"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Impossible d'ajouter un message à une conversation {conversation.get('status')}",
            )
        
        # Récupérer l'historique (10 dernières paires Q/R = 20 messages)
        conversation_history = await get_conversation_history(conversation_id, user_id, max_pairs=10)
    
    # Créer une entrée dans questions (pour quota unifié) SANS générer de réponse
    # La réponse sera générée avec l'historique ci-dessous
    try:
        question_entry = await create_question_without_answer(
            user_id=user_id,
            question_text=request.question,
            context=request.context,
        )
        question_id = question_entry["id"]
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Générer la réponse avec l'historique
    try:
        answer = await generate_question_answer(
            question=request.question,
            context=request.context,
            user_department=department_name,
            user_service=service_name,
            organization_id=organization_id,
            conversation_history=conversation_history,
        )
    except Exception as e:
        # En cas d'erreur, utiliser une réponse par défaut
        import logging
        logger = logging.getLogger(__name__)
        msg = str(e)
        if "SearchNotEnabled" in msg or "31082" in msg or "requires additional configuration" in msg:
            logger.warning(f"Erreur lors de la génération de la réponse IA: {e}")
        else:
            logger.error(f"Erreur lors de la génération de la réponse IA: {e}")
        answer = "Désolé, une erreur est survenue lors de la génération de la réponse. Veuillez réessayer plus tard."
    
    # Mettre à jour la question avec la réponse
    from app.core.db import get_database
    from datetime import datetime
    from bson import ObjectId
    
    db = get_database()
    await db["questions"].update_one(
        {"_id": ObjectId(question_id)},
        {"$set": {
            "answer": answer,
            "status": "answered",
            "answered_at": datetime.utcnow(),
        }}
    )
    
    # Créer ou mettre à jour la conversation
    if not conversation_id:
        # Créer une nouvelle conversation
        conversation = await create_conversation(
            user_id=user_id,
            organization_id=organization_id,
            first_question=request.question,
            first_answer=answer,
            question_id=question_id,
            context=request.context,
        )
        conversation_id = conversation["id"]
    else:
        # Ajouter les messages à la conversation existante
        await add_message_to_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=request.question,
            question_id=question_id,
        )
        await add_message_to_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=answer,
            question_id=None,
        )
    
    # Construire la réponse
    from datetime import datetime
    message = ConversationMessage(
        role="assistant",
        content=answer,
        timestamp=datetime.utcnow().isoformat(),
        question_id=None,
    )
    
    return ConversationAskResponse(
        conversation_id=conversation_id,
        answer=answer,
        message=message,
    )


@router.get("", response_model=List[ConversationPublic])
async def get_conversations(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """
    Liste les conversations de l'utilisateur connecté.
    """
    user_id = str(current_user.get("id"))
    conversations = await list_user_conversations(user_id, limit)
    return conversations


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Récupère les détails d'une conversation (avec tous les messages).
    """
    user_id = str(current_user.get("id"))
    conversation = await get_conversation_by_id(conversation_id, user_id)
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation introuvable ou vous n'êtes pas autorisé à y accéder",
        )
    
    return ConversationDetail(**conversation)


@router.patch("/{conversation_id}/close", response_model=ConversationCloseResponse)
async def close_conversation_endpoint(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Ferme une conversation (status="closed", read-only).
    """
    user_id = str(current_user.get("id"))
    
    try:
        conversation = await close_conversation(conversation_id, user_id)
        return ConversationCloseResponse(
            success=True,
            message="Conversation fermée avec succès",
            conversation=conversation,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{conversation_id}", response_model=ConversationDeleteResponse)
async def delete_conversation_endpoint(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Supprime une conversation.
    """
    user_id = str(current_user.get("id"))
    
    success = await delete_conversation(conversation_id, user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation introuvable ou vous n'êtes pas autorisé à la supprimer",
        )
    
    return ConversationDeleteResponse(
        success=True,
        message="Conversation supprimée avec succès",
    )

