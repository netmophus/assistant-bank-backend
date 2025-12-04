from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class QCMResponseCreate(BaseModel):
    """Schéma pour créer une réponse QCM."""
    formation_id: str
    module_id: str
    question_index: int = Field(..., ge=0, description="Index de la question dans le module (0-based)")
    selected_answer: int = Field(..., ge=0, le=3, description="Index de la réponse sélectionnée (0-3)")


class QCMResponsePublic(BaseModel):
    """Schéma pour retourner une réponse QCM."""
    id: str
    user_id: str
    formation_id: str
    module_id: str
    question_index: int
    selected_answer: int
    is_correct: bool
    correct_answer: int
    explication: Optional[str] = None
    answered_at: datetime
    question_text: Optional[str] = None
    options: Optional[list] = None


class QCMModuleStats(BaseModel):
    """Statistiques pour un module QCM."""
    module_id: str
    total_questions: int
    answered_questions: int
    correct_answers: int
    score_percentage: float
    responses: list[QCMResponsePublic] = []

