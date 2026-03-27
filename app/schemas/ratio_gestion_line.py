"""Schémas Pydantic pour les ratios de gestion (lignes personnalisées)"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RatioGestionLineBase(BaseModel):
    code: str = Field(..., description="Code unique du ratio de gestion (ex: 'TX_DEGRADATION_BRUT')")
    libelle: str = Field(..., description="Libellé du ratio de gestion")
    description: Optional[str] = Field(None, description="Description")
    formule: str = Field(..., description="Formule (références via codes de postes bilan)")
    unite: str = Field("%", description="Unité d'affichage (% ou nombre)")
    is_active: bool = Field(True, description="Actif/inactif")
    ordre_affichage: int = Field(1, description="Ordre d'affichage")


class RatioGestionLineCreate(RatioGestionLineBase):
    organization_id: str


class RatioGestionLineUpdate(BaseModel):
    libelle: Optional[str] = None
    description: Optional[str] = None
    formule: Optional[str] = None
    unite: Optional[str] = None
    is_active: Optional[bool] = None
    ordre_affichage: Optional[int] = None


class RatioGestionLinePublic(RatioGestionLineBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
