"""
Schémas Pydantic pour la discussion vocale avec OpenAI Realtime API.
"""
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field


class VoiceSessionRequest(BaseModel):
    """Requête pour créer une session vocale"""
    request_data: Any = Field(..., description="Données du formulaire de crédit")
    calculated_metrics: Any = Field(..., description="Métriques calculées")
    ai_decision: Optional[str] = Field(None, description="Décision IA précédente")
    ai_analysis: Optional[str] = Field(None, description="Analyse IA précédente")


class VoiceSessionResponse(BaseModel):
    """Réponse avec les informations pour établir la connexion WebRTC"""
    session_id: str = Field(..., description="ID de la session OpenAI")
    client_secret: str = Field(..., description="Secret client pour l'authentification")
    ephemeral_key: str = Field(..., description="Clé éphémère OpenAI")
    websocket_url: str = Field(..., description="URL WebSocket pour la connexion")
    system_prompt: str = Field(..., description="Prompt système injecté dans la session")
    dossier_context: str = Field(..., description="Contexte du dossier de crédit")


class VoiceTranscript(BaseModel):
    """Transcription d'un message vocal"""
    role: str = Field(..., description="user ou assistant")
    content: str = Field(..., description="Contenu transcrit")
    timestamp: float = Field(..., description="Timestamp du message")


class VoiceSessionStatus(BaseModel):
    """Statut d'une session vocale"""
    session_id: str
    status: str  # "active", "ended", "error"
    duration_seconds: Optional[float] = None
    transcript_count: int = 0
