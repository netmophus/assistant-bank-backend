from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ConsommableModificationRequestBase(BaseModel):
    """Schéma de base pour une demande de modification/création de consommable"""
    action: str = Field(..., example="create", description="Action: 'create' ou 'update'")
    consommable_id: Optional[str] = Field(None, example="507f1f77bcf86cd799439011", description="ID du consommable (pour update)")
    consommable_data: Dict[str, Any] = Field(..., description="Données du consommable à créer/modifier")
    motif: Optional[str] = Field(None, example="Mise à jour des informations")


class ConsommableModificationRequestCreate(ConsommableModificationRequestBase):
    pass


class ConsommableModificationRequestPublic(ConsommableModificationRequestBase):
    id: str
    gestionnaire_id: str
    organization_id: str
    statut: str = Field(..., example="en_attente")
    validation_drh: dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ValidationConsommableDRH(BaseModel):
    commentaire: Optional[str] = Field(None, example="Modification validée par la DRH")

