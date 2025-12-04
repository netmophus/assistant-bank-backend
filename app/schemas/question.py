from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class QuestionCreate(BaseModel):
    question: str = Field(..., min_length=1, description="La question à poser à l'IA")
    context: Optional[str] = Field(None, description="Contexte supplémentaire (optionnel)")
    formation_id: Optional[str] = Field(None, description="ID de la formation (pour questions contextuelles)")
    module_id: Optional[str] = Field(None, description="ID du module (pour questions contextuelles)")
    chapitre_id: Optional[str] = Field(None, description="ID du chapitre (pour questions contextuelles)")


class QuestionPublic(BaseModel):
    id: str
    user_id: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    service_id: Optional[str] = None
    service_name: Optional[str] = None
    question: str
    answer: Optional[str] = None
    status: str = "pending"  # pending, answered, error
    created_at: str
    answered_at: Optional[str] = None


class QuestionStats(BaseModel):
    user_id: str
    current_month: str  # Format: YYYY-MM
    questions_asked: int
    quota_limit: int = 60
    remaining_quota: int
    is_quota_exceeded: bool = False

