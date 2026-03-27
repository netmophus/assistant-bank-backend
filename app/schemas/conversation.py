from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class ConversationMessage(BaseModel):
    """Message dans une conversation."""
    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    question_id: Optional[str] = None


class ConversationAskRequest(BaseModel):
    """Requête pour poser une question dans une conversation."""
    question: str = Field(..., min_length=1, description="La question à poser")
    context: Optional[str] = Field(None, description="Contexte supplémentaire (optionnel)")
    conversation_id: Optional[str] = Field(None, description="ID de la conversation (si None, crée une nouvelle conversation)")


class ConversationPublic(BaseModel):
    """Représentation publique d'une conversation (liste)."""
    id: str
    user_id: str
    organization_id: str
    title: str
    status: Literal["open", "closed", "archived"]
    message_count: int
    created_at: str
    updated_at: str
    closed_at: Optional[str] = None
    archived_at: Optional[str] = None
    month_key: Optional[str] = None
    last_message: Optional[str] = None


class ConversationDetail(ConversationPublic):
    """Détails d'une conversation avec tous les messages."""
    messages: List[ConversationMessage]


class ConversationAskResponse(BaseModel):
    """Réponse après avoir posé une question dans une conversation."""
    conversation_id: str
    answer: str
    message: ConversationMessage


class ConversationCloseResponse(BaseModel):
    """Réponse après fermeture d'une conversation."""
    success: bool
    message: str
    conversation: ConversationPublic


class ConversationDeleteResponse(BaseModel):
    """Réponse après suppression d'une conversation."""
    success: bool
    message: str

